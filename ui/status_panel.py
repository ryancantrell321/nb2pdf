"""
NB2PDF - System status dashboard panel.

Displays dependency check results with status indicators and
actionable fix buttons.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Callable, Optional

from services.system_checker import CheckResult, CheckStatus, SystemCheckReport
from ui.theme import Theme
from ui.widgets import (
    AccentButton, BodyLabel, Card, GhostButton, Separator,
    StatusDot, SubHeading, _font,
)
from utils.logger import get_logger

logger = get_logger("status_panel")

_BROWSER_DOWNLOAD_URLS = {
    "Chrome": "https://www.google.com/chrome/",
    "Edge":   "https://www.microsoft.com/edge",
    "Brave":  "https://brave.com/download/",
}

_LATEX_URLS = {
    "MiKTeX":   "https://miktex.org/download",
    "TeX Live": "https://tug.org/texlive/",
}


class StatusPanel(tk.Frame):
    """
    Dependency status dashboard rendered inside a Card.

    Parameters
    ----------
    parent:
        Parent widget.
    theme:
        Active UI theme.
    on_install_packages:
        Callback invoked when the user requests package installation.
    """

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        on_install_packages: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        self.theme = theme
        self._on_install = on_install_packages
        self._rows: list = []

        self._build_skeleton()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def show_loading(self) -> None:
        """Show a 'checking…' spinner placeholder."""
        self._clear_rows()
        lbl = BodyLabel(
            self._body,
            self.theme,
            text="⟳  Checking dependencies…",
            secondary=True,
        )
        lbl.pack(padx=self.theme.pad_md, pady=self.theme.pad_sm)
        self._rows.append(lbl)

    def update_report(self, report: SystemCheckReport) -> None:
        """Populate the panel with check results."""
        self._clear_rows()

        sections = [
            ("Python Packages",       report.python_packages),
            ("Browsers",              report.browsers),
            ("LaTeX",                 report.latex),
            ("Pandoc  (LaTeX pipeline required)", report.pandoc),
        ]

        for i, (section_name, results) in enumerate(sections):
            if i > 0:
                sep = Separator(self._body, self.theme)
                sep.pack(fill="x", padx=self.theme.pad_md, pady=(4, 0))
                self._rows.append(sep)

            sect_label = tk.Label(
                self._body,
                text=section_name,
                bg=self.theme.bg_secondary,
                fg=self.theme.text_secondary,
                font=_font(self.theme, self.theme.font_size_sm, bold=True),
            )
            sect_label.pack(
                anchor="w",
                padx=self.theme.pad_md,
                pady=(self.theme.pad_sm, 2),
            )
            self._rows.append(sect_label)

            for result in results:
                row = self._build_result_row(result)
                row.pack(fill="x", padx=self.theme.pad_md, pady=1)
                self._rows.append(row)

        # Action buttons
        self._add_action_buttons(report)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_skeleton(self) -> None:
        card = Card(self, self.theme)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=self.theme.bg_secondary)
        header.pack(fill="x", padx=self.theme.pad_md, pady=(self.theme.pad_md, 4))

        SubHeading(header, self.theme, text="System Status").pack(side="left")

        self._refresh_btn = GhostButton(
            header,
            self.theme,
            text="↺ Refresh",
            bg=self.theme.bg_secondary,
        )
        self._refresh_btn.pack(side="right")

        sep = Separator(card, self.theme)
        sep.pack(fill="x", padx=self.theme.pad_md)

        self._body = tk.Frame(card, bg=self.theme.bg_secondary)
        self._body.pack(fill="both", expand=True, pady=(4, self.theme.pad_md))

        self.show_loading()

    def _build_result_row(self, result: CheckResult) -> tk.Frame:
        row = tk.Frame(self._body, bg=self.theme.bg_secondary)
        row.columnconfigure(1, weight=1)

        status_map = {
            CheckStatus.OK:      "ok",
            CheckStatus.MISSING: "error",
            CheckStatus.PARTIAL: "warn",
            CheckStatus.UNKNOWN: "unknown",
        }
        dot = StatusDot(row, self.theme, status=status_map.get(result.status, "unknown"))
        dot.grid(row=0, column=0, padx=(0, 8), pady=2, sticky="w")

        name_lbl = tk.Label(
            row,
            text=result.name,
            bg=self.theme.bg_secondary,
            fg=self.theme.text_primary,
            font=_font(self.theme, self.theme.font_size_md),
        )
        name_lbl.grid(row=0, column=1, sticky="w")

        detail_lbl = tk.Label(
            row,
            text=result.detail,
            bg=self.theme.bg_secondary,
            fg=self.theme.text_secondary,
            font=_font(self.theme, self.theme.font_size_sm),
        )
        detail_lbl.grid(row=1, column=1, sticky="w", padx=(0, 4))

        if result.fix_action and result.status == CheckStatus.MISSING:
            fix_btn = GhostButton(
                row,
                self.theme,
                text="Fix →",
                bg=self.theme.bg_secondary,
                command=lambda r=result: self._handle_fix(r),
            )
            fix_btn.grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="e")

        return row

    def _add_action_buttons(self, report: SystemCheckReport) -> None:
        missing_pkgs = [
            r.name for r in report.python_packages
            if r.status == CheckStatus.MISSING
        ]
        if missing_pkgs and self._on_install:
            frame = tk.Frame(self._body, bg=self.theme.bg_secondary)
            frame.pack(fill="x", padx=self.theme.pad_md, pady=(self.theme.pad_sm, 4))

            AccentButton(
                frame,
                self.theme,
                text=f"Install {len(missing_pkgs)} Missing Package(s)",
                command=lambda: self._on_install(missing_pkgs),
            ).pack(side="left")
            self._rows.append(frame)

    def _clear_rows(self) -> None:
        for widget in self._rows:
            widget.destroy()
        self._rows.clear()

    def _handle_fix(self, result: CheckResult) -> None:
        action = result.fix_action or ""
        if action.startswith("pip install"):
            pkg = action.split("pip install")[-1].strip()
            if self._on_install:
                self._on_install([pkg])
        else:
            # Open browser to download page
            for key, url in {**_BROWSER_DOWNLOAD_URLS, **_LATEX_URLS}.items():
                if key.lower() in action.lower():
                    webbrowser.open(url)
                    return
            # Generic: open first URL found
            import re
            urls = re.findall(r"https?://\S+", action)
            if urls:
                webbrowser.open(urls[0])

    @property
    def refresh_button(self) -> GhostButton:
        return self._refresh_btn
