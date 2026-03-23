"""
NB2PDF - Settings dialog.

A modal Toplevel window that lets the user configure preferences.
Changes are applied immediately and persisted on close.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from config.constants import METHOD_BROWSER, METHOD_LATEX
from config.settings import Settings
from ui.theme import Theme
from ui.widgets import (
    AccentButton, BodyLabel, Card, GhostButton, Separator,
    SubHeading, _font,
)
from utils.file_utils import set_window_icon
from utils.logger import get_logger

logger = get_logger("settings_dialog")


class SettingsDialog(tk.Toplevel):
    """
    Modal settings window.

    Parameters
    ----------
    parent:
        Owner window.
    theme:
        Active UI theme.
    settings:
        Settings instance to read from and write to.
    on_theme_change:
        Callback invoked with the new theme name when the user switches themes.
    """

    def __init__(
        self,
        parent: tk.Tk,
        theme: Theme,
        settings: Settings,
        on_theme_change: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.theme = theme
        self._settings = settings
        self._on_theme_change = on_theme_change

        self.title("Settings")
        self.resizable(False, False)
        self.configure(bg=theme.bg_primary)
        self.grab_set()  # Modal
        set_window_icon(self)

        self._build_ui()
        self._center_on_parent(parent)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        pad = self.theme.pad_md
        outer = tk.Frame(self, bg=self.theme.bg_primary, padx=pad, pady=pad)
        outer.pack(fill="both", expand=True)

        SubHeading(outer, self.theme, text="Settings").pack(anchor="w", pady=(0, pad))

        card = Card(outer, self.theme)
        card.pack(fill="both", expand=True, pady=(0, pad))

        content = tk.Frame(card, bg=self.theme.bg_secondary, padx=pad, pady=pad)
        content.pack(fill="both", expand=True)

        # ── Conversion method ─────────────────────────────────────────
        self._add_section_label(content, "Default Conversion Method")
        self._method_var = tk.StringVar(value=self._settings.preferred_method)
        for label, value in [
            ("Browser (Chrome / Edge / Brave)", METHOD_BROWSER),
            ("LaTeX (MiKTeX / TeX Live)",        METHOD_LATEX),
        ]:
            rb = tk.Radiobutton(
                content,
                text=label,
                variable=self._method_var,
                value=value,
                bg=self.theme.bg_secondary,
                fg=self.theme.text_primary,
                selectcolor=self.theme.bg_tertiary,
                activebackground=self.theme.bg_secondary,
                activeforeground=self.theme.text_primary,
                font=_font(self.theme, self.theme.font_size_md),
            )
            rb.pack(anchor="w", padx=(pad, 0), pady=2)

        Separator(content, self.theme).pack(fill="x", pady=pad)

        # ── Behaviour ─────────────────────────────────────────────────
        self._add_section_label(content, "Behaviour")
        self._open_pdf_var = tk.BooleanVar(value=self._settings.open_pdf_after_conversion)
        self._add_checkbox(content, "Open PDF after conversion", self._open_pdf_var)

        self._check_updates_var = tk.BooleanVar(value=self._settings.check_updates_on_startup)
        self._add_checkbox(content, "Check for updates on startup", self._check_updates_var)

        Separator(content, self.theme).pack(fill="x", pady=pad)

        # ── Appearance ────────────────────────────────────────────────
        self._add_section_label(content, "Appearance")
        theme_row = tk.Frame(content, bg=self.theme.bg_secondary)
        theme_row.pack(anchor="w", padx=(pad, 0), pady=4)
        BodyLabel(theme_row, self.theme, text="Theme:").pack(side="left", padx=(0, 8))
        self._theme_var = tk.StringVar(value=self._settings.theme)
        for label, value in [("Dark", "dark"), ("Light", "light")]:
            rb = tk.Radiobutton(
                theme_row,
                text=label,
                variable=self._theme_var,
                value=value,
                bg=self.theme.bg_secondary,
                fg=self.theme.text_primary,
                selectcolor=self.theme.bg_tertiary,
                activebackground=self.theme.bg_secondary,
                activeforeground=self.theme.text_primary,
                font=_font(self.theme, self.theme.font_size_md),
            )
            rb.pack(side="left", padx=4)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = tk.Frame(outer, bg=self.theme.bg_primary)
        btn_row.pack(fill="x")

        GhostButton(
            btn_row, self.theme, text="Cancel",
            command=self.destroy,
            bg=self.theme.bg_primary,
        ).pack(side="right", padx=(8, 0))

        AccentButton(
            btn_row, self.theme, text="Save",
            command=self._save,
        ).pack(side="right")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _add_section_label(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self.theme.bg_secondary,
            fg=self.theme.text_secondary,
            font=_font(self.theme, self.theme.font_size_sm, bold=True),
        ).pack(anchor="w", pady=(4, 2))

    def _add_checkbox(
        self, parent: tk.Widget, label: str, variable: tk.BooleanVar
    ) -> None:
        cb = tk.Checkbutton(
            parent,
            text=label,
            variable=variable,
            bg=self.theme.bg_secondary,
            fg=self.theme.text_primary,
            selectcolor=self.theme.bg_tertiary,
            activebackground=self.theme.bg_secondary,
            activeforeground=self.theme.text_primary,
            font=_font(self.theme, self.theme.font_size_md),
        )
        cb.pack(anchor="w", padx=(self.theme.pad_md, 0), pady=2)

    def _save(self) -> None:
        self._settings.preferred_method = self._method_var.get()
        self._settings.open_pdf_after_conversion = self._open_pdf_var.get()
        self._settings.check_updates_on_startup = self._check_updates_var.get()
        old_theme = self._settings.theme
        self._settings.theme = self._theme_var.get()
        self._settings.save()
        logger.info("Settings saved")

        if self._on_theme_change and self._settings.theme != old_theme:
            self._on_theme_change(self._settings.theme)

        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")
