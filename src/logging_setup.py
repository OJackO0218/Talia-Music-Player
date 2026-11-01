"""Application-wide logging setup.

Writes a rotating log file next to the executable (``logs/talia.log``) and mirrors
messages to the console when one is available. A windowed PyInstaller build has no
console, so the file handler is what makes failures diagnosable. If the install
folder is read-only, logging falls back to ``%LOCALAPPDATA%/Talia/logs`` and then
to the system temp folder instead of crashing at startup.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

from config import PROJECT_ROOT

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "talia.log")


def _pick_log_dir() -> str | None:
    """Returns the first writable log directory, or None if none can be created."""
    candidates = [LOG_DIR]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Talia", "logs"))
    candidates.append(os.path.join(tempfile.gettempdir(), "Talia", "logs"))
    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, f".write-test-{os.getpid()}")
            with open(probe, "w", encoding="utf-8"):
                pass
            os.remove(probe)
            return candidate
        except OSError:
            continue
    return None


def setup_logging(level: int = logging.INFO, console: bool = True) -> logging.Logger:
    """Configures the root logger once and returns it."""
    global LOG_FILE
    root = logging.getLogger()
    if getattr(root, "_talia_configured", False):
        return root
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    log_dir = _pick_log_dir()
    if log_dir is not None:
        LOG_FILE = os.path.join(log_dir, "talia.log")
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            LOG_FILE = ""

    # A windowed PyInstaller build has no stderr, so console logging is optional.
    if console and sys.stderr is not None:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
    root._talia_configured = True  # type: ignore[attr-defined]
    logger = logging.getLogger(__name__)
    if LOG_FILE:
        logger.info("Logging to %s", LOG_FILE)
    else:
        logger.warning("No writable log directory found; logging to console only.")
    return root
