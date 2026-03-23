"""
NB2PDF - Drag-and-drop file input zone.

Provides a drop target that accepts .ipynb files dragged from the
file manager. Falls back gracefully when tkdnd is unavailable,
showing a click-to-browse button instead.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional

from ui.theme import Theme
from ui.widgets import BodyLabel, GhostButton, _font


class DropZone(tk.Frame):
    """
    File input widget with drag-and-drop and click-to-browse support.

    Parameters
    ----------
    parent:
        Parent widget.
    theme:
        Active UI theme.
    on_file_selected:
        Callback invoked with the selected file path whenever a valid
        .ipynb file is chosen (drag or browse).
    """

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        on_file_selected: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            bg=theme.bg_tertiary,
            highlightbackground=theme.border,
            highlightthickness=2,
            **kwargs,
        )
        self.theme = theme
        self._callback = on_file_selected
        self._dragging = False
        self._dnd_available = False

        self._build_ui()
        self._try_enable_dnd()
        self.bind("<Button-1>", self._browse)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_file(self, path: str) -> None:
        """Update the displayed file path."""
        if path:
            name = os.path.basename(path)
            self._label.configure(
                text=f"📄  {name}",
                fg=self.theme.text_primary,
            )
        else:
            self._label.configure(
                text="Drop a .ipynb file here\nor click to browse",
                fg=self.theme.text_secondary,
            )

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)

        icon = tk.Label(
            self,
            text="⬇",
            bg=self.theme.bg_tertiary,
            fg=self.theme.accent,
            font=_font(self.theme, 28),
        )
        icon.grid(row=0, column=0, pady=(18, 4))

        self._label = tk.Label(
            self,
            text="Drop a .ipynb file here\nor click to browse",
            bg=self.theme.bg_tertiary,
            fg=self.theme.text_secondary,
            font=_font(self.theme, self.theme.font_size_md),
            justify="center",
        )
        self._label.grid(row=1, column=0, pady=(0, 6))

        self._browse_btn = GhostButton(
            self,
            theme=self.theme,
            text="Browse…",
            command=self._browse,
            bg=self.theme.bg_tertiary,
        )
        self._browse_btn.grid(row=2, column=0, pady=(0, 14))

        # Propagate clicks from children
        for child in (icon, self._label):
            child.bind("<Button-1>", self._browse)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------------ #
    # Drag-and-drop                                                        #
    # ------------------------------------------------------------------ #

    def _try_enable_dnd(self) -> None:
        """Attempt to register tkdnd drop handlers."""
        try:
            self.tk.call("package", "require", "tkdnd")
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.dnd_bind("<<DragLeave>>", self._on_drag_leave)
            self._dnd_available = True
        except Exception:
            # tkdnd not available — browse only
            pass

    def _on_drop(self, event) -> None:
        self._on_drag_leave()
        path = event.data.strip("{}")  # Windows paths arrive in braces
        self._handle_path(path)

    def _on_drag_enter(self, _event=None) -> None:
        self.configure(highlightbackground=self.theme.accent)

    def _on_drag_leave(self, _event=None) -> None:
        self.configure(highlightbackground=self.theme.border)

    # ------------------------------------------------------------------ #
    # Browse                                                               #
    # ------------------------------------------------------------------ #

    def _browse(self, _event=None) -> None:
        path = filedialog.askopenfilename(
            title="Select Jupyter Notebook",
            filetypes=[("Jupyter Notebooks", "*.ipynb"), ("All Files", "*.*")],
        )
        if path:
            self._handle_path(path)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _handle_path(self, path: str) -> None:
        if not path.lower().endswith(".ipynb"):
            self._label.configure(
                text="⚠  Please select a .ipynb file",
                fg=self.theme.color_warn,
            )
            return
        self.set_file(path)
        self._callback(path)

    def _on_enter(self, _event=None) -> None:
        self.configure(bg=self.theme.bg_hover)
        for child in self.winfo_children():
            try:
                child.configure(bg=self.theme.bg_hover)
            except tk.TclError:
                pass

    def _on_leave(self, _event=None) -> None:
        self.configure(bg=self.theme.bg_tertiary)
        for child in self.winfo_children():
            try:
                child.configure(bg=self.theme.bg_tertiary)
            except tk.TclError:
                pass
