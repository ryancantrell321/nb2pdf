"""
NB2PDF - File handling utilities.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

from config.constants import NOTEBOOK_EXTENSION, PDF_EXTENSION

# On Windows GUI builds suppress the console window for every child process.
if sys.platform == "win32":
    _SUBPROCESS_FLAGS: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _SUBPROCESS_FLAGS: dict = {}
from utils.logger import get_logger

logger = get_logger("file_utils")


def set_window_icon(window: object) -> None:
    """Apply the .ico icon to any Tk or Toplevel window. Silently skips if missing."""
    import tkinter as tk
    from utils.paths import get_resource_path
    ico_path = get_resource_path("assets/notebook_to_pdf.ico")
    if not os.path.isfile(ico_path):
        return
    try:
        window.iconbitmap(ico_path)  # type: ignore[attr-defined]
    except Exception:
        pass
    # iconbitmap alone does not update the taskbar on Windows —
    # iconphoto with a PhotoImage is required for that.
    try:
        img = tk.PhotoImage(file=ico_path)
        window.iconphoto(True, img)  # type: ignore[attr-defined]
        # Keep a reference so the image isn’t garbage-collected
        window._icon_image = img  # type: ignore[attr-defined]
    except Exception:
        pass


def validate_notebook_path(path: str) -> Optional[str]:
    """
    Validate that *path* points to a readable .ipynb file.

    Returns an error message string, or None if valid.
    """
    if not path:
        return "No file selected."
    if not os.path.isfile(path):
        return f"File not found: {path}"
    if not path.lower().endswith(NOTEBOOK_EXTENSION):
        return f"File must be a Jupyter Notebook ({NOTEBOOK_EXTENSION})."
    if not os.access(path, os.R_OK):
        return f"Cannot read file (permission denied): {path}"
    return None


def validate_output_dir(directory: str) -> Optional[str]:
    """
    Validate that *directory* is a writable directory.

    Creates the directory if it does not exist.
    Returns an error message string, or None if valid.
    """
    if not directory:
        return "No output directory selected."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        return f"Cannot create output directory: {exc}"
    if not os.access(directory, os.W_OK):
        return f"Output directory is not writable: {directory}"
    return None


def derive_output_path(notebook_path: str, output_dir: str) -> str:
    """Derive the target PDF path from a notebook path and output directory."""
    stem = os.path.splitext(os.path.basename(notebook_path))[0]
    return os.path.join(output_dir, stem + PDF_EXTENSION)


def safe_copy(src: str, dst: str) -> None:
    """Copy *src* to *dst*, creating parent directories as needed."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    logger.debug(f"Copied {src} → {dst}")


def human_readable_size(path: str) -> str:
    """Return a human-readable file size for *path*."""
    try:
        size = os.path.getsize(path)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except OSError:
        return "unknown size"
