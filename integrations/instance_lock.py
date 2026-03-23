"""
NB2PDF - Single-instance lock using portalocker.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import portalocker

from config.constants import APP_NAME
from utils.logger import get_logger

logger = get_logger("instance_lock")

_LOCK_FILENAME = f"{APP_NAME}.lock"


class InstanceLocker:
    """Enforces single-instance execution via a portalocker file lock."""

    def __init__(self) -> None:
        self._lock_path: str = os.path.join(tempfile.gettempdir(), _LOCK_FILENAME)
        self._fh: Optional[object] = None

    def acquire(self) -> bool:
        """Return True if the lock was acquired, False if another instance holds it."""
        try:
            self._fh = open(self._lock_path, "w", encoding="utf-8")
            portalocker.lock(self._fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
            self._fh.write(str(os.getpid()))
            self._fh.flush()
            logger.debug(f"Instance lock acquired (PID {os.getpid()})")
            return True
        except portalocker.LockException:
            logger.warning("Instance lock held by another process.")
            if self._fh:
                self._fh.close()
                self._fh = None
            return False

    def release(self) -> None:
        """Release the instance lock."""
        if self._fh:
            try:
                portalocker.unlock(self._fh)
                self._fh.close()
                os.unlink(self._lock_path)
                logger.debug("Instance lock released")
            except OSError:
                pass
            self._fh = None

    def __del__(self) -> None:
        self.release()
