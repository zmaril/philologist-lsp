import asyncio
import logging
import re
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from philologist_lsp import __version__
from philologist_lsp.analyzers.definitions import DefinitionService
from philologist_lsp.analyzers.morph import (
    DocumentAnalysis,
    Sentence,
    TokenAnalysis,
    extract_tokens,
)
from philologist_lsp.analyzers.orality import (
    HavelockService,
    OralitySpan,
    to_payload as orality_payload,
)
from philologist_lsp.analyzers.orality_taxonomy import description_for, examples_for
from philologist_lsp.colors import TOKEN_MODIFIERS, TOKEN_TYPES
from philologist_lsp.detect import LanguageDetectorService, Paragraph
from philologist_lsp.render import decorations as decoration_render
from philologist_lsp.render import hover as hover_render
from philologist_lsp.render import semantic_tokens as st_render
from philologist_lsp.spacy_pool import SpacyPool

logger = logging.getLogger("philologist_lsp")

DEBOUNCE_SECONDS = 0.25

# Per-file opt-out marker. Honored when philologist.respectDisableMarker is on.
# Matched anywhere in the first 10 lines of the document.
DISABLE_MARKER_RE = re.compile(
    r"philologist\s*:\s*(off|disable|disabled)\b", re.IGNORECASE
)


def _is_disabled_in_file(text: str) -> bool:
    head = "\n".join(text.split("\n", 11)[:10])
    return bool(DISABLE_MARKER_RE.search(head))


class PhilologistServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(name="philologist-lsp", version=__version__)
        self.detector: LanguageDetectorService | None = None
        self.pool: SpacyPool | None = None
        self.definitions: DefinitionService | None = None
        self.havelock: HavelockService | None = None
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="philo")
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}
        self._download_tokens: dict[str, str] = {}
        self.analyses: dict[str, DocumentAnalysis] = {}
        self.orality_by_uri: dict[str, list[OralitySpan]] = {}
        self._analysis_ready: dict[str, asyncio.Event] = {}
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._spacy_size: str = "md"

        # Feature toggles. Mirrors the philologist.* settings on the client.
        # Server defaults to "all on"; client sends actuals via
        # initializationOptions on initialize and didChangeConfiguration
        # afterwards.
        self.feature_enabled: bool = True
        self.morphology_enabled: bool = True
        self.orality_enabled: bool = True
        self.definitions_enabled: bool = True
        self.respect_disable_marker: bool = True
        self.orality_min_confidence: float = 0.25

    def initialize_services(self) -> None:
        if self.detector is None:
            logger.info("loading lingua language detector")
            self.detector = LanguageDetectorService()
        if self.pool is None:
            logger.info("creating spaCy pool (size=%s)", self._spacy_size)
            self.pool = SpacyPool(
                size=self._spacy_size,
                on_download_start=self._download_progress_begin,
                on_download_end=self._download_progress_end,
                on_ready=self._on_model_ready,
            )
        if self.definitions is None or self.havelock is None:
            # transformers 5.x uses _LazyModule with __getattr__ that races
            # between threads — multiple background loaders calling
            # `from transformers import X` concurrently can hit a
            # partially-initialized module and raise ImportError. Warm the
            # lazy attributes once on the main thread before kicking off any
            # service whose preload thread will need them.
            try:
                import transformers  # noqa: PLC0415
                transformers.AutoModel
                transformers.AutoTokenizer
                transformers.AutoModelForCausalLM
            except Exception:  # noqa: BLE001
                logger.exception("transformers warm-up failed")

        if self.definitions is None:
            logger.info("starting definition LLM preload")
            self.definitions = DefinitionService(
                on_load_start=self._download_progress_begin,
                on_load_end=self._download_progress_end,
            )
        if self.havelock is None:
            logger.info("starting havelock orality preload")
            self.havelock = HavelockService(
                on_load_start=self._download_progress_begin,
                on_load_end=self._download_progress_end,
            )

    def _on_model_ready(self, iso_code: str) -> None:
        """Re-analyze every open document when a new model finishes loading.

        Called from a background thread, so we hop back onto the event loop.
        """
        logger.info("spaCy model ready: %s — re-analyzing open documents", iso_code)
        loop = getattr(self, "_event_loop", None)
        if loop is None:
            return
        for uri in list(self.analyses):
            loop.call_soon_threadsafe(_schedule_analysis, self, uri)

    def ready_event(self, uri: str) -> asyncio.Event:
        evt = self._analysis_ready.get(uri)
        if evt is None:
            evt = asyncio.Event()
            self._analysis_ready[uri] = evt
        return evt

    def _download_progress_begin(self, key: str, title: str) -> None:
        token = f"philologist-download-{key}-{uuid.uuid4().hex[:8]}"
        self._download_tokens[key] = token
        try:
            self.work_done_progress.create(token)
            self.work_done_progress.begin(
                token,
                lsp.WorkDoneProgressBegin(title=title, cancellable=False),
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to begin progress for %s", key)

    def _download_progress_end(self, key: str, message: str) -> None:
        token = self._download_tokens.pop(key, None)
        if token is None:
            return
        try:
            self.work_done_progress.end(
                token, lsp.WorkDoneProgressEnd(message=message)
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to end progress for %s", key)


server = PhilologistServer()


# ---------------------------------------------------------------------------
# Analysis pipeline
# ---------------------------------------------------------------------------


def _analyze_paragraph_sync(
    pool: SpacyPool, paragraph: Paragraph
) -> tuple[list[TokenAnalysis], list[Sentence]]:
    iso = paragraph.detection.iso_code
    if iso is None:
        return [], []
    nlp = pool.get(iso)
    if nlp is None:
        return [], []
    doc = nlp(paragraph.text)
    tokens = extract_tokens(doc, language=iso, document_offset=paragraph.start)
    sentences = [
        Sentence(
            text=sent.text,
            start=paragraph.start + sent.start_char,
            end=paragraph.start + sent.end_char,
            language=iso,
        )
        for sent in doc.sents
    ]
    return tokens, sentences


async def _analyze_document(ls: PhilologistServer, uri: str) -> None:
    try:
        doc = ls.workspace.get_text_document(uri)
    except KeyError:
        return
    text = doc.source
    version = doc.version or 0
    # Stash the running loop so the pool's on_ready callback (fired from a
    # worker thread) can hand work back to us via call_soon_threadsafe.
    ls._event_loop = asyncio.get_running_loop()

    # Master toggle and per-file `philologist: off` marker. When either is
    # in effect, blank out previous outputs and skip the heavy work.
    file_disabled = (
        ls.respect_disable_marker and _is_disabled_in_file(text)
    )
    if not ls.feature_enabled or file_disabled:
        await _clear_analysis(ls, uri, text, version)
        if file_disabled:
            logger.info("file has `philologist: off` marker — skipping %s", uri)
        return

    ls.initialize_services()
    assert ls.detector is not None and ls.pool is not None

    paragraphs = ls.detector.detect_paragraphs(text)
    loop = asyncio.get_running_loop()

    all_tokens: list[TokenAnalysis] = []
    all_sentences: list[Sentence] = []
    for paragraph in paragraphs:
        tokens, sentences = await loop.run_in_executor(
            ls.executor, _analyze_paragraph_sync, ls.pool, paragraph
        )
        all_tokens.extend(tokens)
        all_sentences.extend(sentences)

    if not ls.morphology_enabled:
        all_tokens = []
    analysis = DocumentAnalysis(
        uri=uri,
        text=text,
        tokens=tuple(all_tokens),
        sentences=tuple(all_sentences),
        version=version,
    )
    ls.analyses[uri] = analysis
    ls.ready_event(uri).set()

    languages = sorted({p.detection.iso_code for p in paragraphs if p.detection.iso_code})
    logger.info(
        "analysis ready: %s (%d tokens, %d paragraphs, langs=%s)",
        uri, len(all_tokens), len(paragraphs), ",".join(languages) or "?",
    )

    # Tell VSCode to re-pull semantic tokens.
    try:
        ls.workspace_semantic_tokens_refresh(None)
    except Exception:  # noqa: BLE001
        logger.debug("semantic tokens refresh not supported", exc_info=True)

    # Push our custom sigil decorations to the extension client.
    try:
        ls.protocol.notify(
            "philologist/decorations",
            decoration_render.build_payload(analysis),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send decorations")

    # Run orality on English sentences (best-effort; the model may still be
    # loading on first run, in which case we send an empty list now and the
    # next analysis cycle will fill it in). Sentence boundaries come from
    # spaCy via the morph analysis we just completed.
    if ls.havelock is not None and ls.orality_enabled:
        # Filter sentences before classification:
        #   (a) drop ones that are too short or have no letters at all —
        #       these tend to be punctuation fragments that the classifier
        #       still labels (with low confidence) as something arbitrary;
        #   (b) trim leading/trailing whitespace so the OralitySpan offsets
        #       land on the actual sentence text, never on a blank line.
        english_sentences: list[tuple[str, int, int]] = []
        for s in all_sentences:
            if s.language != "en":
                continue
            stripped = s.text.strip()
            if len(stripped) < 8 or not any(c.isalpha() for c in stripped):
                continue
            leading = len(s.text) - len(s.text.lstrip())
            trailing = len(s.text) - len(s.text.rstrip())
            english_sentences.append(
                (stripped, s.start + leading, s.end - trailing)
            )
        orality_spans: list[OralitySpan] = []
        if english_sentences:
            try:
                spans = await loop.run_in_executor(
                    ls.executor,
                    ls.havelock.analyze_sentences,
                    english_sentences,
                )
            except Exception:  # noqa: BLE001
                logger.exception("havelock failed")
                spans = None
            if spans:
                # Drop spans whose top label has no real signal — at this
                # confidence range the classifier is essentially picking
                # arbitrarily among bad options.
                orality_spans = [
                    s for s in spans if s.confidence >= ls.orality_min_confidence
                ]
        ls.orality_by_uri[uri] = orality_spans

        # Document-level regressor score: weighted mean across English
        # sentences. Only meaningful when there's English content in the
        # document; otherwise we send None and the client hides the bar.
        document_score: float | None = None
        if english_sentences:
            try:
                document_score = await loop.run_in_executor(
                    ls.executor,
                    ls.havelock.score_document,
                    [text for text, _, _ in english_sentences],
                )
            except Exception:  # noqa: BLE001
                logger.exception("regressor failed")

        category = None
        if document_score is not None:
            if document_score >= 0.7:
                category = "oral dominant"
            elif document_score >= 0.4:
                category = "mixed"
            else:
                category = "literate dominant"

        try:
            ls.protocol.notify(
                "philologist/orality",
                {
                    "uri": uri,
                    "version": version,
                    "spans": [orality_payload(s) for s in orality_spans],
                    "documentScore": document_score,
                    "documentCategory": category,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send orality notification")
        # Tell the client to re-pull code lenses now that we have new spans.
        try:
            ls.workspace_code_lens_refresh(None)
        except Exception:  # noqa: BLE001
            logger.debug("code lens refresh not supported", exc_info=True)


async def _clear_analysis(
    ls: PhilologistServer, uri: str, text: str, version: int
) -> None:
    """Wipe all server-pushed annotations for a document and tell the client
    to re-pull empty results. Used when philologist is disabled (master
    switch off, or per-file `philologist: off` marker)."""
    empty = DocumentAnalysis(
        uri=uri, text=text, tokens=(), sentences=(), version=version
    )
    ls.analyses[uri] = empty
    ls.orality_by_uri[uri] = []
    ls.ready_event(uri).set()
    try:
        ls.protocol.notify(
            "philologist/decorations",
            {"uri": uri, "version": version, "decorations": []},
        )
    except Exception:  # noqa: BLE001
        logger.debug("decorations clear failed", exc_info=True)
    try:
        ls.protocol.notify(
            "philologist/orality",
            {
                "uri": uri,
                "version": version,
                "spans": [],
                "documentScore": None,
                "documentCategory": None,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("orality clear failed", exc_info=True)
    try:
        ls.workspace_semantic_tokens_refresh(None)
    except Exception:  # noqa: BLE001
        pass
    try:
        ls.workspace_code_lens_refresh(None)
    except Exception:  # noqa: BLE001
        pass


def _schedule_analysis(ls: PhilologistServer, uri: str) -> None:
    existing = ls._debounce_tasks.get(uri)
    if existing is not None and not existing.done():
        existing.cancel()
    ls.ready_event(uri).clear()

    async def _run() -> None:
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
            await _analyze_document(ls, uri)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("analysis failed for %s", uri)

    ls._debounce_tasks[uri] = asyncio.create_task(_run())


async def _await_analysis(
    ls: PhilologistServer, uri: str, timeout: float = 1.5
) -> DocumentAnalysis | None:
    """Wait briefly for analysis if it hasn't completed yet, then return
    whatever's currently cached. Short timeout keeps the server responsive
    while heavy downloads happen in the background."""
    if uri in ls.analyses:
        return ls.analyses[uri]
    try:
        await asyncio.wait_for(ls.ready_event(uri).wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return ls.analyses.get(uri)


# ---------------------------------------------------------------------------
# Lifecycle handlers
# ---------------------------------------------------------------------------


@server.feature(lsp.INITIALIZED)
def on_initialized(ls: PhilologistServer, params: lsp.InitializedParams) -> None:
    logger.info("initialized")
    ls.window_log_message(
        lsp.LogMessageParams(
            type=lsp.MessageType.Info,
            message=f"philologist-lsp {__version__} initialized",
        )
    )


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def on_did_open(
    ls: PhilologistServer, params: lsp.DidOpenTextDocumentParams
) -> None:
    doc = params.text_document
    logger.info("didOpen %s (%s, %d chars)", doc.uri, doc.language_id, len(doc.text))
    _schedule_analysis(ls, doc.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def on_did_change(
    ls: PhilologistServer, params: lsp.DidChangeTextDocumentParams
) -> None:
    _schedule_analysis(ls, params.text_document.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def on_did_close(
    ls: PhilologistServer, params: lsp.DidCloseTextDocumentParams
) -> None:
    uri = params.text_document.uri
    logger.info("didClose %s", uri)
    task = ls._debounce_tasks.pop(uri, None)
    if task is not None and not task.done():
        task.cancel()
    ls.analyses.pop(uri, None)
    ls.orality_by_uri.pop(uri, None)
    ls._analysis_ready.pop(uri, None)


def _apply_settings(ls: PhilologistServer, settings: dict) -> None:
    """Read the philologist.* settings dict and update server state.

    Called both from the workspace/didChangeConfiguration handler and from
    the initialize handler (via initializationOptions) so the server picks
    up settings before the first analysis runs.
    """
    philologist = settings.get("philologist", {}) if isinstance(settings, dict) else {}
    if not isinstance(philologist, dict):
        return

    def _bool(key: str, default: bool) -> bool:
        section, _, leaf = key.rpartition(".")
        node = philologist
        if section:
            for part in section.split("."):
                node = node.get(part, {}) if isinstance(node, dict) else {}
        value = node.get(leaf) if isinstance(node, dict) else None
        return bool(value) if isinstance(value, bool) else default

    def _num(key: str, default: float) -> float:
        section, _, leaf = key.rpartition(".")
        node = philologist
        if section:
            for part in section.split("."):
                node = node.get(part, {}) if isinstance(node, dict) else {}
        value = node.get(leaf) if isinstance(node, dict) else None
        return float(value) if isinstance(value, (int, float)) else default

    new_size = philologist.get("spacyModelSize", ls._spacy_size)
    if new_size != ls._spacy_size:
        logger.info("spacy size changed: %s -> %s", ls._spacy_size, new_size)
        ls._spacy_size = new_size
        ls.pool = None

    ls.feature_enabled = _bool("enable", True)
    ls.morphology_enabled = _bool("morphology.enabled", True)
    ls.orality_enabled = _bool("orality.enabled", True)
    ls.definitions_enabled = _bool("definitions.enabled", True)
    ls.respect_disable_marker = _bool("respectDisableMarker", True)
    ls.orality_min_confidence = _num("orality.minConfidence", 0.25)


@server.feature(lsp.INITIALIZE)
def on_initialize(
    ls: PhilologistServer, params: lsp.InitializeParams
) -> None:
    options = getattr(params, "initialization_options", None)
    if isinstance(options, dict):
        _apply_settings(ls, options)


@server.feature(lsp.WORKSPACE_DID_CHANGE_CONFIGURATION)
def on_did_change_configuration(
    ls: PhilologistServer, params: lsp.DidChangeConfigurationParams
) -> None:
    _apply_settings(ls, params.settings or {})


# ---------------------------------------------------------------------------
# Render handlers
# ---------------------------------------------------------------------------


@server.feature(
    lsp.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    lsp.SemanticTokensLegend(
        token_types=list(TOKEN_TYPES),
        token_modifiers=list(TOKEN_MODIFIERS),
    ),
)
async def on_semantic_tokens_full(
    ls: PhilologistServer, params: lsp.SemanticTokensParams
) -> lsp.SemanticTokens:
    analysis = await _await_analysis(ls, params.text_document.uri)
    if analysis is None:
        return lsp.SemanticTokens(data=[])
    return lsp.SemanticTokens(data=st_render.encode(analysis))


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
async def on_hover(
    ls: PhilologistServer, params: lsp.HoverParams
) -> lsp.Hover | None:
    analysis = await _await_analysis(ls, params.text_document.uri)
    if analysis is None:
        return None

    located = hover_render.find_token(analysis, params.position)
    if located is None:
        return None
    token, _ = located

    definition: str | None = None
    if ls.definitions is not None and ls.definitions_enabled:
        ls.initialize_services()
        sentence = hover_render.sentence_for(analysis, token)
        loop = asyncio.get_running_loop()
        try:
            definition = await asyncio.wait_for(
                loop.run_in_executor(
                    ls.executor,
                    ls.definitions.define,
                    token.text,
                    token.language,
                    sentence,
                ),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "definition lookup timed out for %r (%s)",
                token.text, token.language,
            )

    orality_block = _orality_for_token(ls, params.text_document.uri, token)

    return hover_render.build(
        analysis,
        params.position,
        definition=definition,
        orality_block=orality_block,
    )


@server.feature(
    lsp.TEXT_DOCUMENT_CODE_LENS,
    lsp.CodeLensOptions(resolve_provider=False),
)
def on_code_lens(
    ls: PhilologistServer, params: lsp.CodeLensParams
) -> list[lsp.CodeLens] | None:
    uri = params.text_document.uri
    spans = ls.orality_by_uri.get(uri)
    analysis = ls.analyses.get(uri)
    if not spans or analysis is None:
        return None

    from philologist_lsp.render.positions import LineIndex  # noqa: PLC0415
    line_index = LineIndex(analysis.text)
    text_lines = analysis.text.split("\n")
    lenses: list[lsp.CodeLens] = []
    for span in spans:
        line = line_index.position(span.start).line
        # Defensive: never anchor a lens to a line that has no content.
        # Walk forward to the first non-empty line if needed.
        while line < len(text_lines) and not text_lines[line].strip():
            line += 1
        if line >= len(text_lines):
            continue
        rng = lsp.Range(
            start=lsp.Position(line=line, character=0),
            end=lsp.Position(line=line, character=0),
        )
        emoji = "🟢" if span.category == "oral" else "🟣"
        display = span.marker.replace("_", " ").upper()
        suffix = f" +{len(span.alternatives)}" if span.alternatives else ""
        title = f"{emoji} {display}{suffix} · {int(span.confidence * 100)}%"
        lenses.append(
            lsp.CodeLens(range=rng, command=lsp.Command(title=title, command=""))
        )
    return lenses


def _orality_for_token(
    ls: PhilologistServer, uri: str, token: TokenAnalysis
) -> str | None:
    """If the token is inside an orality span, return a Markdown block to
    append to the hover."""
    spans = ls.orality_by_uri.get(uri)
    if not spans:
        return None
    for span in spans:
        if span.start <= token.start and token.end <= span.end:
            return _format_orality(span)
    return None


def _format_orality(span: OralitySpan) -> str:
    display = span.marker.replace("_", " ").upper()
    # VSCode hover strips even basic HTML tags despite supportHtml=true.
    # Emoji circles render reliably and give visual continuity with the
    # editor's teal/purple tag chips: 🟢 = oral, 🟣 = literate.
    dot = "🟢" if span.category == "oral" else "🟣"
    lines: list[str] = [
        f"{dot} **{display}** — {span.category.upper()} marker",
        "",
        description_for(span.marker),
    ]
    examples = examples_for(span.marker)
    if examples:
        lines.append("")
        lines.append("*Examples:*")
        for ex in examples:
            lines.append(f"> {ex}")
    if span.alternatives:
        lines.append("")
        lines.append("*Also possible:*")
        for alt in span.alternatives:
            lines.append(
                f"- **{alt.marker.replace('_', ' ').upper()}** "
                f"({alt.confidence * 100:.0f}%)"
            )
    lines.append("")
    lines.append(f"_Confidence: {span.confidence * 100:.0f}%_")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("starting philologist-lsp %s on stdio", __version__)
    server.start_io()


if __name__ == "__main__":
    main()
