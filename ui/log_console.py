"""
NB2PDF - Live log console widget.

Reads from the shared log queue and appends formatted lines to a
read-only Text widget.  Polls on a fixed interval so the UI stays
responsive.
"""

from __future__ import annotations

import queue
import tkinter as tk

from ui.theme import Theme
from ui.widgets import GhostButton, SubHeading, _font
from utils.logger import get_log_queue


_LEVEL_COLORS = {
    "INFO":     "#63b3ed",
    "WARNING":  "#f0b429",
    "WARN":     "#f0b429",
    "ERROR":    "#f56565",
    "CRITICAL": "#f56565",
    "DEBUG":    "#9196a8",
}

_MAX_LINES = 500


class LogConsole(tk.Frame):
    """
    Scrollable, colour-coded log console.

    Polls the shared log queue every *poll_ms* milliseconds.
    """

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        poll_ms: int = 150,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        self.theme = theme
        self._poll_ms = poll_ms
        self._log_queue = get_log_queue()
        self._line_count = 0

        self._build_ui()
        self._start_polling()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def append(self, message: str) -> None:
        """Manually append a *message* line to the console."""
        self._insert_line(message)

    def clear(self) -> None:
        """Clear all log output."""
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._line_count = 0

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # Header row
        header = tk.Frame(self, bg=self["bg"])
        header.pack(fill="x", pady=(0, 4))

        SubHeading(header, self.theme, text="Conversion Log").pack(side="left")

        GhostButton(
            header,
            self.theme,
            text="Clear",
            command=self.clear,
            bg=self["bg"],
        ).pack(side="right")

        # Text area + scrollbar
        text_frame = tk.Frame(
            self,
            bg=self.theme.bg_tertiary,
            highlightbackground=self.theme.border,
            highlightthickness=1,
        )
        text_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(text_frame, bg=self.theme.bg_secondary)
        scrollbar.pack(side="right", fill="y")

        self._text = tk.Text(
            text_frame,
            state="disabled",
            bg=self.theme.bg_tertiary,
            fg=self.theme.text_primary,
            font=("Consolas", self.theme.font_size_sm),
            relief="flat",
            wrap="word",
            yscrollcommand=scrollbar.set,
            cursor="arrow",
            selectbackground=self.theme.bg_hover,
            selectforeground=self.theme.text_primary,
            padx=8,
            pady=6,
        )
        self._text.pack(fill="both", expand=True)
        scrollbar.configure(command=self._text.yview)

        # Configure level-specific text tags
        for level, color in _LEVEL_COLORS.items():
            self._text.tag_configure(level, foreground=color)

        # Right-click context menu
        self._context_menu = tk.Menu(
            self._text, tearoff=False,
            bg=self.theme.bg_secondary,
            fg=self.theme.text_primary,
            activebackground=self.theme.accent,
            activeforeground=self.theme.accent_text,
            relief="flat",
            borderwidth=0,
        )
        self._context_menu.add_command(label="Copy",       command=self._copy_selection)
        self._context_menu.add_command(label="Select All", command=self._select_all)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Clear Log",  command=self.clear)
        self._text.bind("<Button-3>", self._show_context_menu)
        self._text.bind("<Control-c>", lambda e: self._copy_selection())
        self._text.bind("<Control-a>", lambda e: self._select_all())

    # ------------------------------------------------------------------ #
    # Polling                                                              #
    # ------------------------------------------------------------------ #

    def _start_polling(self) -> None:
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._insert_line(line)
        except queue.Empty:
            pass
        # Reschedule; after() is safe to call from any thread
        try:
            self.after(self._poll_ms, self._poll)
        except tk.TclError:
            pass  # Widget destroyed

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, event) -> None:
        """Show the right-click context menu."""
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _copy_selection(self) -> None:
        """Copy selected text to clipboard, or entire log if nothing selected."""
        try:
            selected = self._text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # Nothing selected — copy everything
            selected = self._text.get("1.0", "end")
        self._text.clipboard_clear()
        self._text.clipboard_append(selected)

    def _select_all(self) -> None:
        """Select all text in the log console."""
        self._text.configure(state="normal")
        self._text.tag_add(tk.SEL, "1.0", "end")
        self._text.configure(state="disabled")
        return "break"

    def _insert_line(self, line: str) -> None:
        # Trim buffer
        if self._line_count >= _MAX_LINES:
            self._text.configure(state="normal")
            self._text.delete("1.0", "2.0")
            self._text.configure(state="normal")
        else:
            self._line_count += 1

        # Determine level tag
        tag = "INFO"
        for level in _LEVEL_COLORS:
            if f"  {level}" in line or f" {level} " in line:
                tag = level
                break

        self._text.configure(state="normal")
        self._text.insert("end", line.rstrip() + "\n", tag)
        self._text.configure(state="disabled")
        self._text.see("end")
