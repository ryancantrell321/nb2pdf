"""
NB2PDF - Update dialog.

Shows available update information and lets the user download/install.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Callable, Optional

from services.updater import UpdateChecker, UpdateInfo
from ui.theme import Theme
from ui.widgets import (
    AccentButton, BodyLabel, Card, GhostButton, ProgressBar,
    SubHeading, _font,
)
from utils.file_utils import set_window_icon
from utils.logger import get_logger

logger = get_logger("update_dialog")


class UpdateDialog(tk.Toplevel):
    """
    Modal dialog for the update workflow.

    Handles:
    - Displaying current vs. latest version
    - Showing changelog
    - Download progress
    - Launching the external updater
    """

    def __init__(
        self,
        parent: tk.Tk,
        theme: Theme,
        checker: UpdateChecker,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.theme = theme
        self._checker = checker
        self._update_info: Optional[UpdateInfo] = None

        self.title("Software Update")
        self.resizable(False, False)
        self.configure(bg=theme.bg_primary)
        self.grab_set()
        set_window_icon(self)

        self._build_ui()
        self._center_on_parent(parent)
        self._start_check()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        pad = self.theme.pad_md
        outer = tk.Frame(self, bg=self.theme.bg_primary, padx=pad, pady=pad)
        outer.pack(fill="both", expand=True)

        SubHeading(outer, self.theme, text="Software Update").pack(anchor="w", pady=(0, pad))

        card = Card(outer, self.theme)
        card.pack(fill="both", expand=True, pady=(0, pad))

        self._body = tk.Frame(card, bg=self.theme.bg_secondary, padx=pad, pady=pad)
        self._body.pack(fill="both", expand=True)

        self._status_label = BodyLabel(
            self._body, self.theme, text="Checking for updates…"
        )
        self._status_label.pack(anchor="w")

        self._changelog = tk.Text(
            self._body,
            height=8,
            bg=self.theme.bg_tertiary,
            fg=self.theme.text_secondary,
            font=("Consolas", self.theme.font_size_sm),
            relief="flat",
            state="disabled",
            wrap="word",
        )
        self._changelog.pack(fill="both", expand=True, pady=(pad, 0))
        self._changelog.pack_forget()  # Hidden until data arrives

        self._progress = ProgressBar(self._body, self.theme)
        self._progress.pack(fill="x", pady=(pad, 0))
        self._progress.pack_forget()

        # Button row
        btn_row = tk.Frame(outer, bg=self.theme.bg_primary)
        btn_row.pack(fill="x")

        self._close_btn = GhostButton(
            btn_row, self.theme, text="Close",
            command=self.destroy,
            bg=self.theme.bg_primary,
        )
        self._close_btn.pack(side="right", padx=(8, 0))

        self._action_btn = AccentButton(
            btn_row, self.theme, text="Download & Install",
            command=self._download_and_install,
        )
        self._action_btn.pack(side="right")
        self._action_btn.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Update check                                                         #
    # ------------------------------------------------------------------ #

    def _start_check(self) -> None:
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        info = self._checker.check_for_updates()
        self.after(0, lambda: self._on_check_result(info))

    def _on_check_result(self, info: Optional[UpdateInfo]) -> None:
        if info is None:
            self._status_label.configure(
                text="Could not check for updates.\nCheck your internet connection.",
                fg=self.theme.color_warn,
            )
            return

        self._update_info = info

        if info.is_newer:
            self._status_label.configure(
                text=(
                    f"✦  New version available!\n\n"
                    f"  Current : {info.current_version}\n"
                    f"  Latest  : {info.latest_version}"
                ),
                fg=self.theme.color_ok,
            )
            self._action_btn.configure(state="normal")
        else:
            self._status_label.configure(
                text=f"✔  You are up to date  (v{info.current_version})",
                fg=self.theme.color_ok,
            )

        # Show changelog
        if info.changelog:
            self._changelog.configure(state="normal")
            self._changelog.delete("1.0", "end")
            self._changelog.insert("end", info.changelog)
            self._changelog.configure(state="disabled")
            self._changelog.pack(fill="both", expand=True, pady=(self.theme.pad_md, 0))

    # ------------------------------------------------------------------ #
    # Download & install                                                   #
    # ------------------------------------------------------------------ #

    def _download_and_install(self) -> None:
        if not self._update_info:
            return
        if not self._update_info.download_url:
            self._status_label.configure(
                text="No download URL available for this release.",
                fg=self.theme.color_warn,
            )
            return

        self._action_btn.configure(state="disabled")
        self._progress.pack(fill="x", pady=(self.theme.pad_md, 0))
        self._status_label.configure(
            text="Downloading update…", fg=self.theme.text_primary
        )
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self) -> None:
        info = self._update_info
        path = self._checker.download_update(info)
        self.after(0, lambda: self._on_download_complete(path))

    def _on_download_complete(self, path: Optional[str]) -> None:
        if not path:
            self._status_label.configure(
                text="Download failed. Please try again.",
                fg=self.theme.color_error,
            )
            self._action_btn.configure(state="normal")
            return

        self._progress.set(100)
        self._status_label.configure(
            text="Download complete!\nThe updater will run after you close this window.",
            fg=self.theme.color_ok,
        )
        launched = self._checker.launch_updater(path)
        if launched:
            self._close_btn.configure(text="Close & Apply Update")
        else:
            self._status_label.configure(
                text=f"Update downloaded to:\n{path}\n\nPlease replace the app manually.",
                fg=self.theme.color_warn,
            )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{max(w, 400)}x{max(h, 360)}+{x}+{y}")
