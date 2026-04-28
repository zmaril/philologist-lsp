"""Lazy-loading pool of spaCy pipelines, one per ISO language code.

`get(iso_code)` is non-blocking: it returns a loaded pipeline if one is
ready, otherwise it kicks off a background download and returns None. The
caller is expected to render whatever it can with the models currently
available; when more models finish loading, the pool fires `on_ready` and
the caller re-runs analysis.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    # spaCy is part of the optional `[nlp]` extra; defer import so the
    # module is importable for CI smoke tests without ML deps installed.
    from spacy.language import Language

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _silenced_stdio():
    """Silence both fd 1/2 and Python's sys.stdout/sys.stderr while spaCy
    runs `pip install` as a subprocess.

    The fd redirect handles subprocess output (pip writes "Collecting...",
    "Downloading..." to the inherited stdout). The Python-level redirect
    handles spaCy's own progress prints via wasabi, which write through a
    cached TextIOWrapper that doesn't always re-resolve fd 1.

    Our LSP transport *is* stdout — any unframed byte there breaks the
    Content-Length protocol and the client tears the connection down.
    """
    null_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    null_writer = open(os.devnull, "w")
    try:
        os.dup2(null_fd, 1)
        os.dup2(null_fd, 2)
        with (
            contextlib.redirect_stdout(null_writer),
            contextlib.redirect_stderr(null_writer),
        ):
            yield
    finally:
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(null_fd)
        os.close(saved_stdout)
        os.close(saved_stderr)
        null_writer.close()


# ISO 639-1 → canonical spaCy model name (md size).
LANGUAGE_MODELS: dict[str, str] = {
    "ca": "ca_core_news_md",
    "zh": "zh_core_web_md",
    "hr": "hr_core_news_md",
    "da": "da_core_news_md",
    "nl": "nl_core_news_md",
    "en": "en_core_web_md",
    "fi": "fi_core_news_md",
    "fr": "fr_core_news_md",
    "de": "de_core_news_md",
    "el": "el_core_news_md",
    "it": "it_core_news_md",
    "ja": "ja_core_news_md",
    "ko": "ko_core_news_md",
    "lt": "lt_core_news_md",
    "mk": "mk_core_news_md",
    "pl": "pl_core_news_md",
    "pt": "pt_core_news_md",
    "ro": "ro_core_news_md",
    "ru": "ru_core_news_md",
    "sl": "sl_core_news_md",
    "es": "es_core_news_md",
    "sv": "sv_core_news_md",
    "uk": "uk_core_news_md",
}

FALLBACK_MODEL = "xx_sent_ud_sm"


ProgressHook = Callable[[str, str], None]
ReadyHook = Callable[[str], None]


class SpacyPool:
    """Non-blocking spaCy pipeline cache with a background download worker.

    Public API:
        get(iso_code) -> Language | None    # ready now, or None
        prime(iso_code)                     # request a model without using it
    """

    def __init__(
        self,
        size: str = "md",
        on_download_start: ProgressHook | None = None,
        on_download_end: ProgressHook | None = None,
        on_ready: ReadyHook | None = None,
    ) -> None:
        self._size = size
        self._cache: dict[str, "Language"] = {}
        self._cache_lock = threading.Lock()
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._failed: set[str] = set()
        self._queue: queue.Queue[str] = queue.Queue()
        self._on_download_start = on_download_start
        self._on_download_end = on_download_end
        self._on_ready = on_ready

        self._worker = threading.Thread(
            target=self._download_worker,
            name="philo-spacy-download",
            daemon=True,
        )
        self._worker.start()

    def _model_name(self, iso_code: str) -> str | None:
        canonical = LANGUAGE_MODELS.get(iso_code)
        if canonical is None:
            return None
        prefix, _, _suffix = canonical.rpartition("_")
        return f"{prefix}_{self._size}"

    def get(self, iso_code: str) -> "Language | None":
        """Return the loaded pipeline for `iso_code`, or None if not yet
        ready. Triggers a background download on first miss."""
        with self._cache_lock:
            if iso_code in self._cache:
                return self._cache[iso_code]
            if iso_code in self._failed:
                return None

        model_name = self._model_name(iso_code)
        if model_name is None:
            return None

        import spacy  # noqa: PLC0415 — lazy import; see module top.

        # Try a fast in-process load first (model already on disk, just
        # needs to be loaded into memory). If that fails, queue a download.
        try:
            nlp = spacy.load(model_name)
        except OSError:
            self._enqueue(iso_code)
            return None
        except Exception:  # noqa: BLE001
            logger.exception("failed to load %s", model_name)
            with self._cache_lock:
                self._failed.add(iso_code)
            return None

        with self._cache_lock:
            self._cache[iso_code] = nlp
        if self._on_ready:
            self._on_ready(iso_code)
        return nlp

    def prime(self, iso_code: str) -> None:
        """Request a model without blocking on the result."""
        self.get(iso_code)

    def _enqueue(self, iso_code: str) -> None:
        with self._inflight_lock:
            if iso_code in self._inflight:
                return
            self._inflight.add(iso_code)
        self._queue.put(iso_code)

    def _download_worker(self) -> None:
        while True:
            iso_code = self._queue.get()
            try:
                self._download_one(iso_code)
            except Exception:  # noqa: BLE001
                logger.exception("download worker error for %s", iso_code)
            finally:
                with self._inflight_lock:
                    self._inflight.discard(iso_code)

    def _download_one(self, iso_code: str) -> None:
        model_name = self._model_name(iso_code)
        if model_name is None:
            return
        logger.info("downloading spaCy model %s", model_name)
        import spacy  # noqa: PLC0415
        from spacy.cli.download import download as spacy_download  # noqa: PLC0415

        if self._on_download_start:
            try:
                self._on_download_start(
                    model_name, f"Downloading spaCy model: {model_name}"
                )
            except Exception:  # noqa: BLE001
                logger.exception("download_start hook failed")
        try:
            with _silenced_stdio():
                spacy_download(model_name)
            nlp = spacy.load(model_name)
        except SystemExit:
            # spacy.cli.download may sys.exit on certain failures; capture
            # so we don't take the whole server with us.
            logger.exception("spacy_download exited unexpectedly for %s", model_name)
            with self._cache_lock:
                self._failed.add(iso_code)
            return
        except Exception:  # noqa: BLE001
            logger.exception("download failed for %s", model_name)
            with self._cache_lock:
                self._failed.add(iso_code)
            return
        finally:
            if self._on_download_end:
                try:
                    self._on_download_end(model_name, f"Downloaded {model_name}")
                except Exception:  # noqa: BLE001
                    logger.exception("download_end hook failed")

        with self._cache_lock:
            self._cache[iso_code] = nlp
        if self._on_ready:
            try:
                self._on_ready(iso_code)
            except Exception:  # noqa: BLE001
                logger.exception("on_ready hook failed for %s", iso_code)
