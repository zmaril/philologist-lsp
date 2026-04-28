"""Per-sentence orality classification using the havelock-orality model.

Splits an English paragraph into sentences and runs the subtype classifier
(71 markers) on each. Returns top-k labels with confidences. Loaded
eagerly in the background like the definition LLM.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from philologist_lsp.analyzers.orality_taxonomy import (
    category_for,
    description_for,
    examples_for,
)

logger = logging.getLogger(__name__)


# Sub-classification: keep alternatives whose probability exceeds this.
ALT_THRESHOLD = 0.10

# Maximum number of alternative markers to surface per sentence.
MAX_ALTERNATIVES = 3


@dataclass(frozen=True, slots=True)
class OralityAlternative:
    marker: str
    confidence: float


@dataclass(frozen=True, slots=True)
class OralitySpan:
    start: int  # absolute char offset in the document
    end: int
    marker: str
    category: str  # "oral" | "literate"
    confidence: float
    alternatives: tuple[OralityAlternative, ...]


class HavelockService:
    """Eager-loaded havelock-orality subtype classifier + regressor."""

    def __init__(
        self,
        model_repo: str = "thestalwart/havelock-orality",
        on_load_start=None,
        on_load_end=None,
    ) -> None:
        self._model_repo = model_repo
        self._model = None
        self._regressor = None
        self._tokenizer = None
        self._id2label: dict[int, str] = {}
        self._device: str = "cpu"
        # Cache classification results by sentence text so re-analysis on
        # didChange doesn't re-run BERT for unchanged sentences.
        self._cache: dict[str, list[tuple[str, float]]] = {}
        self._regressor_cache: dict[str, float] = {}
        self._cache_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._on_load_start = on_load_start
        self._on_load_end = on_load_end

        threading.Thread(
            target=self._ensure_loaded,
            name="philo-havelock-preload",
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        with self._load_lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False
            try:
                self._do_load()
                return True
            except Exception:  # noqa: BLE001
                logger.exception("havelock load failed")
                self._load_failed = True
                return False

    def _do_load(self) -> None:
        import torch  # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415
        from huggingface_hub import hf_hub_download  # noqa: PLC0415

        # transformers 5.x dropped BertModel/BertTokenizer from the top
        # level. Use Auto* — for bert-base-uncased they resolve to the same
        # underlying classes, and the state-dict keys still match.
        from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415

        if self._on_load_start:
            try:
                self._on_load_start(
                    self._model_repo,
                    f"Loading orality model: {self._model_repo}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("on_load_start hook failed")

        t0 = time.perf_counter()
        try:
            logger.info("loading havelock %s", self._model_repo)

            subtype_weights = hf_hub_download(
                self._model_repo, "bert_marker_subtype.pt"
            )
            regressor_weights = hf_hub_download(
                self._model_repo, "bert_orality_regressor.pt"
            )
            labels_file = hf_hub_download(
                self._model_repo, "bert_marker_subtype_labels.json"
            )
            label_to_id = json.loads(open(labels_file).read())
            self._id2label = {v: k for k, v in label_to_id.items()}
            num_classes = len(self._id2label)

            class _BertSubtype(nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.bert = AutoModel.from_pretrained("bert-base-uncased")
                    self.dropout = nn.Dropout(0.1)
                    self.classifier = nn.Linear(768, num_classes)

                def forward(self, input_ids, attention_mask):
                    out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                    return self.classifier(self.dropout(out.pooler_output))

            class _BertRegressor(nn.Module):
                """Document-level orality regressor.

                Architecture mirrors the model card: shared BERT base,
                dropout, single Linear(768→1), sigmoid → score in [0,1].
                """

                def __init__(self) -> None:
                    super().__init__()
                    self.bert = AutoModel.from_pretrained("bert-base-uncased")
                    self.dropout = nn.Dropout(0.1)
                    self.regressor = nn.Linear(768, 1)
                    self.sigmoid = nn.Sigmoid()

                def forward(self, input_ids, attention_mask):
                    out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                    pooled = self.dropout(out.pooler_output)
                    return self.sigmoid(self.regressor(pooled)).squeeze(-1)

            self._tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

            subtype_model = _BertSubtype()
            subtype_model.load_state_dict(
                torch.load(subtype_weights, map_location="cpu", weights_only=True),
                strict=False,
            )
            regressor_model = _BertRegressor()
            regressor_model.load_state_dict(
                torch.load(regressor_weights, map_location="cpu", weights_only=True),
                strict=False,
            )

            if torch.backends.mps.is_available():
                self._device = "mps"
                dtype = torch.float16
            elif torch.cuda.is_available():
                self._device = "cuda"
                dtype = torch.float16
            else:
                self._device = "cpu"
                dtype = torch.float32

            subtype_model.to(self._device, dtype=dtype)
            subtype_model.eval()
            regressor_model.to(self._device, dtype=dtype)
            regressor_model.eval()
            self._model = subtype_model
            self._regressor = regressor_model

            logger.info(
                "havelock subtype + regressor loaded on %s (%s) in %.2fs",
                self._device,
                dtype,
                time.perf_counter() - t0,
            )
        finally:
            if self._on_load_end:
                try:
                    self._on_load_end(self._model_repo, f"Loaded {self._model_repo}")
                except Exception:  # noqa: BLE001
                    logger.exception("on_load_end hook failed")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def analyze_sentences(
        self, sentences: list[tuple[str, int, int]]
    ) -> Optional[list[OralitySpan]]:
        """Classify each pre-segmented sentence.

        `sentences` is a list of `(text, abs_start, abs_end)` tuples; the
        offsets are absolute positions in the document. We classify each
        independently and return one OralitySpan per sentence.
        """
        if not self._ensure_loaded():
            return None
        if not sentences:
            return []

        spans: list[OralitySpan] = []
        try:
            for sentence_text, s_start, s_end in sentences:
                top = self._classify_cached(sentence_text)
                if not top:
                    continue
                primary = top[0]
                alts = tuple(
                    OralityAlternative(marker=label, confidence=conf)
                    for label, conf in top[1:]
                    if conf >= ALT_THRESHOLD
                )
                spans.append(
                    OralitySpan(
                        start=s_start,
                        end=s_end,
                        marker=primary[0],
                        category=category_for(primary[0]),
                        confidence=primary[1],
                        alternatives=alts,
                    )
                )
        except Exception:  # noqa: BLE001
            logger.exception("havelock paragraph analysis failed")
            return None
        return spans

    def score_text(self, text: str) -> Optional[float]:
        """Run the document regressor on `text` (truncated to 512 tokens).

        Returns a float in [0, 1]: 1.0 = highly oral, 0.0 = highly literate.
        Cached by exact text so editing other sentences doesn't re-run the
        regressor on stable ones.
        """
        if not self._ensure_loaded() or self._regressor is None:
            return None
        if not text.strip():
            return None
        with self._cache_lock:
            cached = self._regressor_cache.get(text)
        if cached is not None:
            return cached
        try:
            import torch  # noqa: PLC0415

            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=False,
            ).to(self._device)
            with torch.no_grad():
                score = self._regressor(inputs["input_ids"], inputs["attention_mask"])
            value = float(score.item())
        except Exception:  # noqa: BLE001
            logger.exception("regressor failed")
            return None
        with self._cache_lock:
            self._regressor_cache[text] = value
        return value

    def score_document(self, sentences: list[str]) -> Optional[float]:
        """Mean regressor score across input sentences (length-weighted)."""
        scores: list[tuple[float, int]] = []
        for sentence in sentences:
            score = self.score_text(sentence)
            if score is None:
                continue
            scores.append((score, len(sentence)))
        if not scores:
            return None
        total_chars = sum(length for _, length in scores)
        if total_chars == 0:
            return None
        return sum(score * length for score, length in scores) / total_chars

    def _classify_cached(self, sentence_text: str) -> list[tuple[str, float]]:
        with self._cache_lock:
            cached = self._cache.get(sentence_text)
        if cached is not None:
            return cached
        result = self._classify(sentence_text)
        with self._cache_lock:
            self._cache[sentence_text] = result
        return result

    def _classify(self, sentence: str) -> list[tuple[str, float]]:
        """Return top markers for a single sentence as (label, prob)."""
        if not sentence.strip():
            return []
        import torch  # noqa: PLC0415

        inputs = self._tokenizer(
            sentence,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=False,
        ).to(self._device)
        with torch.no_grad():
            logits = self._model(inputs["input_ids"], inputs["attention_mask"])
        probs = torch.softmax(logits.float(), dim=-1).squeeze(0)
        top = torch.topk(probs, k=min(MAX_ALTERNATIVES + 1, probs.shape[-1]))
        return [
            (self._id2label[idx.item()], val.item())
            for idx, val in zip(top.indices, top.values)
        ]


def to_payload(span: OralitySpan) -> dict:
    return {
        "start": span.start,
        "end": span.end,
        "marker": span.marker,
        "category": span.category,
        "confidence": span.confidence,
        "displayName": span.marker.replace("_", " ").upper(),
        "description": description_for(span.marker),
        "examples": examples_for(span.marker),
        "alternatives": [
            {
                "marker": a.marker,
                "confidence": a.confidence,
                "displayName": a.marker.replace("_", " ").upper(),
            }
            for a in span.alternatives
        ],
    }
