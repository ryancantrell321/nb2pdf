"""
NB2PDF - Centralized logging setup.

Writes to both a rotating file and a GUI-compatible queue handler
so the UI console can display live log output without blocking.

Design note
-----------
``setup_logger()`` must be called once from ``main.py`` before any
other module is imported.  Child loggers created via ``get_logger()``
inherit the root NB2PDF logger's handlers through normal propagation.
We also call ``setup_logger()`` lazily inside ``get_logger()`` as a
safety net so that logging never silently fails even if the call order
changes during development.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import queue

from config.constants import APP_NAME, LOG_FILENAME
from utils.paths import get_logs_dir

# Module-level queue shared between logger and UI
_log_queue: queue.Queue = queue.Queue(maxsize=5000)

# Track whether setup has run so we never double-attach handlers
_setup_done: bool = False


class QueueHandler(logging.Handler):
    """Pushes formatted log records onto a thread-safe queue for UI consumption."""

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self._queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(self.format(record))
        except queue.Full:
            pass  # Drop if UI isn't draining fast enough


def get_log_queue() -> queue.Queue:
    """Return the shared log queue (used by UI to poll messages)."""
    return _log_queue


def setup_logger(level: str = "DEBUG") -> logging.Logger:
    """
    Configure the root NB2PDF logger with file + queue handlers.

    Safe to call multiple times — subsequent calls are no-ops.
    Level defaults to DEBUG so all detail reaches the log file;
    the GUI queue handler only forwards INFO and above.
    """
    global _setup_done

    root = logging.getLogger(APP_NAME)

    if _setup_done:
        return root

    # Set root level to DEBUG so nothing is filtered before reaching handlers
    root.setLevel(logging.DEBUG)
    # Stop propagation to the Python root logger (avoids duplicate console output)
    root.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file handler (DEBUG and above, 10 MB × 5 backups) ──────
    try:
        log_path = os.path.join(get_logs_dir(APP_NAME), LOG_FILENAME)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:
        # Can't write log file — fall back to stderr so we at least see it
        fallback = logging.StreamHandler()
        fallback.setFormatter(fmt)
        root.addHandler(fallback)
        root.warning(f"Could not open log file: {exc}. Falling back to stderr.")

    # ── Queue handler for GUI console (INFO and above) ───────────────────
    queue_handler = QueueHandler(_log_queue)
    queue_handler.setLevel(logging.INFO)
    queue_handler.setFormatter(fmt)
    root.addHandler(queue_handler)

    _setup_done = True
    root.debug("Logger initialised")
    return root


def get_logger(name: str) -> logging.Logger:
    """
    Return a named child logger under the NB2PDF namespace.

    Calls setup_logger() lazily as a safety net in case this is
    called before main() has had a chance to initialise logging.
    """
    if not _setup_done:
        setup_logger()
    return logging.getLogger(f"{APP_NAME}.{name}")
