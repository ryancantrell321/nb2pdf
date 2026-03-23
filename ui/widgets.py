"""
NB2PDF - Reusable styled widget library.

All widgets accept a Theme instance and apply consistent styling.
This module is the single source of truth for visual appearance.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ui.theme import Theme


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _font(theme: Theme, size: int = 0, bold: bool = False) -> tuple:
    sz = size or theme.font_size_md
    weight = "bold" if bold else "normal"
    return (theme.font_family, sz, weight)


# ──────────────────────────────────────────────────────────────────────────────
# Card frame
# ──────────────────────────────────────────────────────────────────────────────

class Card(tk.Frame):
    """A raised panel with secondary background color and border."""

    def __init__(self, parent: tk.Widget, theme: Theme, **kwargs) -> None:
        super().__init__(
            parent,
            bg=theme.bg_secondary,
            highlightbackground=theme.border,
            highlightthickness=1,
            **kwargs,
        )
        self.theme = theme


# ──────────────────────────────────────────────────────────────────────────────
# Styled labels
# ──────────────────────────────────────────────────────────────────────────────

class Heading(tk.Label):
    """Large bold heading label."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=theme.text_primary,
            font=_font(theme, theme.font_size_xl, bold=True),
            **kwargs,
        )


class SubHeading(tk.Label):
    """Medium section heading."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=theme.text_primary,
            font=_font(theme, theme.font_size_lg, bold=True),
            **kwargs,
        )


class BodyLabel(tk.Label):
    """Standard body-text label."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str = "",
        secondary: bool = False,
        **kwargs,
    ) -> None:
        fg = theme.text_secondary if secondary else theme.text_primary
        super().__init__(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=fg,
            font=_font(theme, theme.font_size_md),
            **kwargs,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Accent button
# ──────────────────────────────────────────────────────────────────────────────

class AccentButton(tk.Button):
    """Primary action button with accent color."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        command: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=theme.accent,
            fg=theme.accent_text,
            activebackground=theme.accent_hover,
            activeforeground=theme.accent_text,
            relief="flat",
            cursor="hand2",
            font=_font(theme, theme.font_size_md, bold=True),
            padx=theme.pad_md,
            pady=theme.pad_sm,
            borderwidth=0,
            **kwargs,
        )
        self.theme = theme
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        self.configure(bg=self.theme.accent_hover)

    def _on_leave(self, _event=None) -> None:
        self.configure(bg=self.theme.accent)


class GhostButton(tk.Button):
    """Secondary action button with transparent background."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        command: Optional[Callable] = None,
        bg: Optional[str] = None,
        **kwargs,
    ) -> None:
        _bg = bg or parent.cget("bg")
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=_bg,
            fg=theme.accent,
            activebackground=theme.bg_hover,
            activeforeground=theme.accent,
            relief="flat",
            cursor="hand2",
            font=_font(theme, theme.font_size_md),
            padx=theme.pad_sm,
            pady=theme.pad_xs,
            borderwidth=0,
            **kwargs,
        )
        self._bg = _bg
        self.theme = theme
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        self.configure(bg=self.theme.bg_hover)

    def _on_leave(self, _event=None) -> None:
        self.configure(bg=self._bg)


# ──────────────────────────────────────────────────────────────────────────────
# Styled Entry
# ──────────────────────────────────────────────────────────────────────────────

class StyledEntry(tk.Frame):
    """Entry field with themed border and focus highlight."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        textvariable: Optional[tk.StringVar] = None,
        placeholder: str = "",
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            bg=theme.border,
            padx=1,
            pady=1,
        )
        self.theme = theme
        self._placeholder = placeholder
        self._has_placeholder = False

        self._var = textvariable or tk.StringVar()
        self._entry = tk.Entry(
            self,
            textvariable=self._var,
            bg=theme.bg_tertiary,
            fg=theme.text_primary,
            insertbackground=theme.text_primary,
            relief="flat",
            font=_font(theme, theme.font_size_md),
            **kwargs,
        )
        self._entry.pack(fill="both", expand=True, padx=2, pady=2)

        if placeholder:
            self._show_placeholder()
            self._entry.bind("<FocusIn>", self._on_focus_in)
            self._entry.bind("<FocusOut>", self._on_focus_out)

        self._entry.bind("<FocusIn>", self._highlight, add="+")
        self._entry.bind("<FocusOut>", self._unhighlight, add="+")

    @property
    def var(self) -> tk.StringVar:
        return self._var

    def get(self) -> str:
        val = self._var.get()
        if self._has_placeholder and val == self._placeholder:
            return ""
        return val

    def set(self, value: str) -> None:
        self._var.set(value)
        self._has_placeholder = False
        self._entry.configure(fg=self.theme.text_primary)

    def _show_placeholder(self) -> None:
        if not self._var.get():
            self._var.set(self._placeholder)
            self._entry.configure(fg=self.theme.text_secondary)
            self._has_placeholder = True

    def _on_focus_in(self, _event=None) -> None:
        if self._has_placeholder:
            self._var.set("")
            self._entry.configure(fg=self.theme.text_primary)
            self._has_placeholder = False

    def _on_focus_out(self, _event=None) -> None:
        self._show_placeholder()

    def _highlight(self, _event=None) -> None:
        self.configure(bg=self.theme.border_focus)

    def _unhighlight(self, _event=None) -> None:
        self.configure(bg=self.theme.border)


# ──────────────────────────────────────────────────────────────────────────────
# Status indicator dot
# ──────────────────────────────────────────────────────────────────────────────

class StatusDot(tk.Canvas):
    """Small colored circle indicating a status (ok / warn / error)."""

    _SIZE = 10

    def __init__(self, parent: tk.Widget, theme: Theme, status: str = "ok") -> None:
        super().__init__(
            parent,
            width=self._SIZE,
            height=self._SIZE,
            bg=parent.cget("bg"),
            highlightthickness=0,
        )
        self.theme = theme
        self._dot = self.create_oval(1, 1, self._SIZE - 1, self._SIZE - 1)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        colors = {
            "ok": self.theme.color_ok,
            "warn": self.theme.color_warn,
            "error": self.theme.color_error,
            "info": self.theme.color_info,
            "unknown": self.theme.text_disabled,
        }
        color = colors.get(status, self.theme.text_disabled)
        self.itemconfig(self._dot, fill=color, outline=color)


# ──────────────────────────────────────────────────────────────────────────────
# Horizontal separator
# ──────────────────────────────────────────────────────────────────────────────

class Separator(tk.Frame):
    """Thin horizontal divider line."""

    def __init__(self, parent: tk.Widget, theme: Theme, **kwargs) -> None:
        super().__init__(parent, bg=theme.border, height=1, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Progress bar
# ──────────────────────────────────────────────────────────────────────────────

class ProgressBar(tk.Frame):
    """Custom determinate/indeterminate progress bar."""

    _HEIGHT = 6

    def __init__(self, parent: tk.Widget, theme: Theme, **kwargs) -> None:
        super().__init__(
            parent,
            bg=theme.bg_tertiary,
            height=self._HEIGHT,
            highlightthickness=0,
            **kwargs,
        )
        self.theme = theme
        self._fill = tk.Frame(self, bg=theme.accent, height=self._HEIGHT)
        self._fill.place(x=0, y=0, relheight=1, relwidth=0)
        self._value = 0

    def set(self, percent: int) -> None:
        """Set progress to *percent* (0–100)."""
        self._value = max(0, min(100, percent))
        self._fill.place(relwidth=self._value / 100)

    def get(self) -> int:
        return self._value

    def reset(self) -> None:
        self.set(0)
