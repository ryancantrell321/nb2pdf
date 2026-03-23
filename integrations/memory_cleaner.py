"""
NB2PDF - Memory and temporary file cleaner.

Removes artefacts left over from conversion runs so the host system
doesn't accumulate stale HTML / LaTeX / image files.
"""

from __future__ import annotations

import gc
import glob
import os
import shutil
from typing import List

from config.constants import APP_NAME
from utils.logger import get_logger
from utils.paths import get_temp_dir

logger = get_logger("memory_cleaner")


class MemoryCleaner:
    """
    Cleans temporary conversion artefacts.

    Usage
    -----
    cleaner = MemoryCleaner()
    cleaner.clean_temp_dir()   # remove all temp files for this app
    cleaner.force_gc()         # run Python garbage collection
    """

    def __init__(self) -> None:
        self._temp_dir = get_temp_dir(APP_NAME)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def clean_all(self) -> List[str]:
        """
        Remove all temporary files and run GC.

        Returns a list of paths that were removed.
        """
        removed = self.clean_temp_dir()
        self.force_gc()
        return removed

    def clean_temp_dir(self) -> List[str]:
        """
        Remove contents of the app temp directory.

        Returns a list of paths that were removed.
        """
        removed: List[str] = []
        if not os.path.isdir(self._temp_dir):
            return removed

        for entry in os.listdir(self._temp_dir):
            entry_path = os.path.join(self._temp_dir, entry)
            try:
                if os.path.isfile(entry_path) or os.path.islink(entry_path):
                    os.unlink(entry_path)
                    removed.append(entry_path)
                elif os.path.isdir(entry_path):
                    shutil.rmtree(entry_path, ignore_errors=True)
                    removed.append(entry_path)
            except OSError as exc:
                logger.warning(f"Could not remove temp item {entry_path}: {exc}")

        logger.info(f"Cleaned {len(removed)} temp item(s) from {self._temp_dir}")
        return removed

    def clean_conversion_artefacts(self, base_path: str) -> List[str]:
        """
        Remove intermediate files related to a specific conversion.

        Matches: <base_path>.html, <base_path>_files/, <base_path>.tex, etc.
        """
        removed: List[str] = []
        stem = os.path.splitext(base_path)[0]
        patterns = [
            stem + ".html",
            stem + ".tex",
            stem + "_files",
            stem + "_notebook_files",
        ]
        for pattern in patterns:
            for match in glob.glob(pattern):
                try:
                    if os.path.isfile(match):
                        os.unlink(match)
                    elif os.path.isdir(match):
                        shutil.rmtree(match, ignore_errors=True)
                    removed.append(match)
                except OSError as exc:
                    logger.warning(f"Could not remove artefact {match}: {exc}")

        if removed:
            logger.debug(f"Removed {len(removed)} conversion artefact(s)")
        return removed

    @staticmethod
    def force_gc() -> None:
        """Run Python garbage collection."""
        collected = gc.collect()
        logger.debug(f"GC collected {collected} object(s)")
