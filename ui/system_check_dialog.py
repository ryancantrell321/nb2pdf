"""
NB2PDF - System Dependencies dialog.

A standalone Toplevel that shows the full dependency check report
with smart per-item install/fix buttons:
  - If a dependency is OK  → button is greyed out ("Installed")
  - If a dependency is missing → button is active ("Install" / "Download")
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from typing import Callable, List, Optional

from services.system_checker import (
    CheckResult, CheckStatus, SystemCheckReport, SystemChecker,
)
from ui.theme import Theme
from ui.widgets import (
    AccentButton, BodyLabel, Card, GhostButton,
    Separator, StatusDot, SubHeading, _font,
)
from utils.file_utils import set_window_icon
from utils.logger import get_logger

logger = get_logger("system_check_dialog")

# Download URLs for non-pip dependencies
_DOWNLOAD_URLS = {
    "pandoc":    "https://pandoc.org/installing.html",
    "miktex":    "https://miktex.org/download",
    "tex live":  "https://tug.org/texlive/",
    "chrome":    "https://www.google.com/chrome/",
    "edge":      "https://www.microsoft.com/edge",
    "brave":     "https://brave.com/download/",
}


class SystemCheckDialog(tk.Toplevel):
    """
    Modal system dependency check window.

    Opens, immediately triggers a background check, then populates
    the results with per-row smart action buttons.
    """

    def __init__(
        self,
        parent: tk.Tk,
        theme: Theme,
        checker: SystemChecker,
        on_install_packages: Optional[Callable[[List[str]], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._checker = checker
        self._on_install = on_install_packages
        self._report: Optional[SystemCheckReport] = None

        self.title("System Dependencies")
        self.configure(bg=theme.bg_primary)
        self.resizable(False, False)
        self.grab_set()
        set_window_icon(self)

        self._build_ui()
        self._center_on_parent(parent)
        self._start_check()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        t = self._theme
        pad = t.pad_md

        outer = tk.Frame(self, bg=t.bg_primary, padx=pad, pady=pad)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(outer, bg=t.bg_primary)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, pad))

        SubHeading(hdr, t, text="System Dependencies").pack(side="left")

        self._refresh_btn = GhostButton(
            hdr, t, text="↺  Re-check",
            command=self._start_check,
            bg=t.bg_primary,
        )
        self._refresh_btn.pack(side="right")

        # ── Scrollable results area ───────────────────────────────────────
        canvas_frame = tk.Frame(
            outer, bg=t.bg_secondary,
            highlightbackground=t.border, highlightthickness=1,
        )
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            canvas_frame, bg=t.bg_secondary,
            highlightthickness=0, bd=0,
        )
        scrollbar = tk.Scrollbar(
            canvas_frame, orient="vertical",
            command=self._canvas.yview,
            bg=t.bg_secondary,
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._scroll_frame = tk.Frame(self._canvas, bg=t.bg_secondary)
        self._scroll_window = self._canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw",
        )
        self._scroll_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel scrolling
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind("<Destroy>", self._on_destroy)

        # ── Footer buttons ────────────────────────────────────────────────
        footer = tk.Frame(outer, bg=t.bg_primary)
        footer.grid(row=2, column=0, sticky="ew", pady=(pad, 0))

        self._install_all_btn = AccentButton(
            footer, t,
            text="Install All Missing",
            command=self._install_all_missing,
        )
        self._install_all_btn.pack(side="left")
        self._install_all_btn.configure(state="disabled")

        GhostButton(
            footer, t, text="Close",
            command=self.destroy,
            bg=t.bg_primary,
        ).pack(side="right")

        # Initial loading state
        self._show_loading()

    # ------------------------------------------------------------------ #
    # Loading / results                                                    #
    # ------------------------------------------------------------------ #

    def _show_loading(self) -> None:
        self._clear_scroll_frame()
        lbl = BodyLabel(
            self._scroll_frame, self._theme,
            text="⟳  Checking dependencies…",
            secondary=True,
        )
        lbl.pack(padx=self._theme.pad_md, pady=self._theme.pad_lg)

    def _populate(self, report: SystemCheckReport) -> None:
        self._report = report
        self._clear_scroll_frame()

        t = self._theme
        pad = t.pad_md

        sections = [
            ("🐍  Python Packages",               report.python_packages),
            ("🌐  Browsers  (Browser pipeline)",  report.browsers),
            ("📐  LaTeX  (LaTeX pipeline)",        report.latex),
            ("🔀  Pandoc  (LaTeX pipeline — required for Markdown cells)", report.pandoc),
        ]

        any_missing = False

        for i, (title, results) in enumerate(sections):
            if i > 0:
                Separator(self._scroll_frame, t).pack(
                    fill="x", padx=pad, pady=(6, 0)
                )

            # Section heading
            tk.Label(
                self._scroll_frame,
                text=title,
                bg=t.bg_secondary,
                fg=t.text_secondary,
                font=_font(t, t.font_size_sm, bold=True),
            ).pack(anchor="w", padx=pad, pady=(t.pad_sm, 2))

            for result in results:
                if result.status == CheckStatus.MISSING:
                    any_missing = True
                self._build_result_row(result)

        # Enable "Install All" only if something is missing
        self._install_all_btn.configure(
            state="normal" if any_missing else "disabled"
        )

    def _build_result_row(self, result: CheckResult) -> None:
        t = self._theme
        pad = t.pad_md

        row = tk.Frame(self._scroll_frame, bg=t.bg_secondary)
        row.pack(fill="x", padx=pad, pady=3)
        row.columnconfigure(1, weight=1)

        # Status dot
        status_map = {
            CheckStatus.OK:      "ok",
            CheckStatus.MISSING: "error",
            CheckStatus.PARTIAL: "warn",
            CheckStatus.UNKNOWN: "unknown",
        }
        StatusDot(
            row, t, status=status_map.get(result.status, "unknown")
        ).grid(row=0, column=0, padx=(0, 10), pady=2, sticky="w")

        # Name
        tk.Label(
            row,
            text=result.name,
            bg=t.bg_secondary,
            fg=t.text_primary,
            font=_font(t, t.font_size_md, bold=True),
        ).grid(row=0, column=1, sticky="w")

        # Detail
        if result.detail:
            tk.Label(
                row,
                text=result.detail,
                bg=t.bg_secondary,
                fg=t.text_secondary,
                font=_font(t, t.font_size_sm),
                wraplength=360,
                justify="left",
            ).grid(row=1, column=1, sticky="w", pady=(0, 2))

        # Action button — always present, state depends on status
        self._build_action_button(row, result)

    def _build_action_button(self, row: tk.Frame, result: CheckResult) -> None:
        t = self._theme
        is_ok = result.status == CheckStatus.OK
        action = result.fix_action or ""

        # Decide label and command
        if is_ok:
            label = "✔  Installed"
            cmd = None
        elif action.startswith("pip install"):
            pkg = action.replace("pip install", "").strip()
            label = f"Install  {pkg}"
            cmd = lambda p=pkg: self._run_pip_install([p])
        elif action.startswith("http"):
            label = "Download  →"
            cmd = lambda u=action: webbrowser.open(u)
        else:
            # Try to extract a URL from the action string
            import re
            urls = re.findall(r"https?://\S+", action)
            if urls:
                label = "Download  →"
                cmd = lambda u=urls[0]: webbrowser.open(u)
            else:
                label = "Fix  →"
                cmd = None

        btn = tk.Button(
            row,
            text=label,
            state="disabled" if is_ok else "normal",
            command=cmd,
            bg=t.accent if not is_ok else t.bg_tertiary,
            fg=t.accent_text if not is_ok else t.text_disabled,
            activebackground=t.accent_hover if not is_ok else t.bg_tertiary,
            activeforeground=t.accent_text,
            relief="flat",
            font=_font(t, t.font_size_sm, bold=not is_ok),
            padx=t.pad_sm,
            pady=t.pad_xs,
            cursor="hand2" if not is_ok else "arrow",
            borderwidth=0,
        )
        btn.grid(row=0, column=2, rowspan=2, padx=(t.pad_sm, 0), sticky="e")

    # ------------------------------------------------------------------ #
    # Check worker                                                         #
    # ------------------------------------------------------------------ #

    def _start_check(self) -> None:
        self._show_loading()
        self._install_all_btn.configure(state="disabled")
        self._refresh_btn.configure(state="disabled", text="Checking…")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        report = self._checker.run_all()
        self.after(0, lambda r=report: self._on_check_done(r))

    def _on_check_done(self, report: SystemCheckReport) -> None:
        self._refresh_btn.configure(state="normal", text="↺  Re-check")
        self._populate(report)

    # ------------------------------------------------------------------ #
    # Install actions                                                      #
    # ------------------------------------------------------------------ #

    def _run_pip_install(self, packages: List[str]) -> None:
        if self._on_install:
            self._on_install(packages)
            # Re-check after a short delay to let pip finish
            self.after(3000, self._start_check)

    def _install_all_missing(self) -> None:
        if not self._report:
            return
        missing_pkgs = [
            r.name for r in self._report.python_packages
            if r.status == CheckStatus.MISSING
        ]
        if missing_pkgs:
            self._run_pip_install(missing_pkgs)

        # Open download pages for non-pip missing deps
        for results in (self._report.browsers, self._report.latex, self._report.pandoc):
            for r in results:
                if r.status == CheckStatus.MISSING and r.fix_action:
                    import re
                    urls = re.findall(r"https?://\S+", r.fix_action)
                    if urls:
                        webbrowser.open(urls[0])

    # ------------------------------------------------------------------ #
    # Scroll helpers                                                       #
    # ------------------------------------------------------------------ #

    def _on_frame_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._scroll_window, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if self._canvas.winfo_exists():
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._canvas.unbind_all("<MouseWheel>")

    def _clear_scroll_frame(self) -> None:
        for w in self._scroll_frame.winfo_children():
            w.destroy()

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _center_on_parent(self, parent: tk.Tk) -> None:
        w, h = 620, 580
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.update_idletasks()
