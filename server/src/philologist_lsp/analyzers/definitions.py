"""Short word definitions via a small local LLM.

Loads Qwen/Qwen3.5-0.8B lazily on first hover. Subsequent hovers on the
same (lemma, language) hit an in-memory cache. Generation runs in the
caller's thread (the server's executor); the server is responsible for
not blocking the asyncio loop.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


# Friendly names for prompt construction. spaCy / lingua use ISO 639-1.
LANGUAGE_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "ca": "Catalan",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "la": "Latin",
    "lt": "Lithuanian",
    "mk": "Macedonian",
    "mr": "Marathi",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sl": "Slovene",
    "sv": "Swedish",
    "uk": "Ukrainian",
    "zh": "Chinese",
}


LoadHook = "callable[[str, str], None]"  # (key, message) — typing.Callable not imported here yet


class DefinitionService:
    """Eager-loaded LLM that produces one-sentence definitions on demand.

    The constructor schedules a background load so the model is ready by
    the time the user first hovers. Calls to `define()` block on the load
    if it hasn't completed yet.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3.5-0.8B",
        on_load_start=None,
        on_load_end=None,
    ) -> None:
        self._model_name = model_name
        self._model = None
        self._tokenizer = None
        self._device: str = "cpu"
        self._cache: dict[tuple[str, str], str] = {}
        self._cache_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._on_load_start = on_load_start
        self._on_load_end = on_load_end

        # Kick off the load eagerly. By the time the user lands a hover,
        # the model is usually ready; otherwise define() blocks on the
        # same lock and the hover waits.
        threading.Thread(
            target=self._ensure_loaded,
            name="philo-llm-preload",
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
                logger.exception("LLM load failed (%s)", self._model_name)
                self._load_failed = True
                return False

    def _do_load(self) -> None:
        import torch  # noqa: PLC0415  — heavy import, defer until first use
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

        if self._on_load_start:
            try:
                self._on_load_start(
                    self._model_name,
                    f"Loading definition model: {self._model_name}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("on_load_start hook failed")

        t0 = time.perf_counter()
        logger.info("loading LLM %s", self._model_name)

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)

            if torch.backends.mps.is_available():
                device = "mps"
                dtype = torch.float16
            elif torch.cuda.is_available():
                device = "cuda"
                dtype = torch.float16
            else:
                device = "cpu"
                dtype = torch.float32

            model = AutoModelForCausalLM.from_pretrained(
                self._model_name,
                torch_dtype=dtype,
            )
            model.to(device)
            model.eval()

            self._model = model
            self._device = device

            logger.info(
                "LLM loaded on %s (%s) in %.2fs",
                device,
                dtype,
                time.perf_counter() - t0,
            )
        finally:
            if self._on_load_end:
                try:
                    self._on_load_end(
                        self._model_name,
                        f"Loaded {self._model_name}",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("on_load_end hook failed")

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def define(
        self,
        lemma: str,
        language: str,
        context: str = "",  # accepted but ignored — kept for API stability
    ) -> Optional[str]:
        """Return a short definition string or None if unavailable.

        Cache key is (lemma, language). Lookups are pure dictionary mode —
        we explicitly do not feed the surrounding sentence in, because that
        causes Qwen-0.8B to paraphrase rather than define.
        """
        del context  # currently unused
        if not lemma or not language:
            return None
        key = (lemma.lower(), language)
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        if not self._ensure_loaded():
            return None

        text = self._render_prompt(lemma, language)

        try:
            response = self._generate(text)
        except Exception:  # noqa: BLE001
            logger.exception("define failed for %r (%s)", lemma, language)
            return None

        with self._cache_lock:
            self._cache[key] = response
        return response

    def _render_prompt(self, lemma: str, language: str) -> str:
        lang_name = LANGUAGE_NAMES.get(language, language)
        # Few-shot dictionary format — Qwen3-0.8B follows the pattern reliably
        # and avoids the "summarize the sentence" failure mode.
        user_message = (
            "You are a multilingual lexicographer. Give the meaning of each "
            "word in one short English sentence. Do not include the surrounding "
            "context, only the word's meaning.\n\n"
            "Word: Hund (German)\n"
            "Definition: A domesticated carnivorous mammal kept as a pet.\n\n"
            "Word: geben (German)\n"
            "Definition: To hand over or transfer something to someone.\n\n"
            "Word: tasse (French)\n"
            "Definition: A small open container used for drinking liquids.\n\n"
            f"Word: {lemma} ({lang_name})\n"
            "Definition:"
        )
        messages = [{"role": "user", "content": user_message}]

        kwargs = dict(tokenize=False, add_generation_prompt=True)
        try:
            return self._tokenizer.apply_chat_template(
                messages, enable_thinking=False, **kwargs
            )
        except TypeError:
            return self._tokenizer.apply_chat_template(messages, **kwargs)

    def _generate(self, text: str) -> str:
        import torch  # noqa: PLC0415

        inputs = self._tokenizer([text], return_tensors="pt").to(self._device)
        prompt_len = inputs.input_ids.shape[1]
        t0 = time.perf_counter()
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        elapsed = time.perf_counter() - t0
        gen_tokens = out[0][prompt_len:]
        response = self._tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
        logger.info(
            "definition generated in %.2fs (%d tokens, %.1f tok/s): %s",
            elapsed,
            len(gen_tokens),
            len(gen_tokens) / elapsed if elapsed > 0 else 0,
            response[:100].replace("\n", " "),
        )
        return response
