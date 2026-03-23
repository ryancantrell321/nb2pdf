from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

from config.constants import (
    APP_NAME, APP_VERSION, METHOD_BROWSER, METHOD_LATEX,
    UI_POLL_INTERVAL,
)
from config.settings import Settings
from core.converter_factory import ConverterFactory
from integrations.memory_cleaner import MemoryCleaner
from services.system_checker import SystemCheckReport, SystemChecker
from services.updater import UpdateChecker
from ui.drop_zone import DropZone
from ui.log_console import LogConsole
from ui.settings_dialog import SettingsDialog
from ui.theme import Theme, get_theme
from ui.system_check_dialog import SystemCheckDialog
from ui.update_dialog import UpdateDialog
from ui.widgets import (
    AccentButton, BodyLabel, Card, GhostButton, Heading,
    ProgressBar, Separator, StatusDot, SubHeading, _font,
)
from utils.file_utils import (
    derive_output_path,
    human_readable_size,
    set_window_icon,
    validate_notebook_path,
    validate_output_dir,
)
from utils.logger import get_logger, setup_logger
from utils.paths import get_logs_dir

logger = get_logger("app_window")


class AppWindow:
    """
    Top-level application window.

    Parameters
    ----------
    settings:
        Application settings (loaded from disk).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._theme: Theme = get_theme(settings.theme)
        self._checker = SystemChecker()
        self._cleaner = MemoryCleaner()
        self._update_checker = UpdateChecker()

        # State
        self._notebook_path: str = ""
        self._output_dir: str = settings.last_output_dir or ""
        self._converting = False

        # Build root window
        self._root = tk.Tk()
        self._root.title(f"{APP_NAME}  v{APP_VERSION}")
        self._root.configure(bg=self._theme.bg_primary)
        self._root.minsize(880, 620)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_window_icon()

        self._apply_window_size()
        self._build_ui()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Enter the Tk main loop. Blocks until the window is closed."""
        self._root.after(200, self._post_start)
        self._root.mainloop()

    def _post_start(self) -> None:
        """Actions run shortly after mainloop starts."""
        self._run_system_checks()
        if self._settings.check_updates_on_startup:
            threading.Thread(
                target=self._background_update_check, daemon=True
            ).start()

    def _on_close(self) -> None:
        """Clean up and close the application."""
        if self._converting:
            if not messagebox.askyesno(
                "Conversion in Progress",
                "A conversion is running.\nClose anyway?",
                parent=self._root,
            ):
                return
        self._settings.last_output_dir = self._output_dir
        self._settings.save()
        self._root.destroy()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        t = self._theme
        root = self._root

        # ── Menu bar ──────────────────────────────────────────────────
        menubar = tk.Menu(root, bg=t.bg_secondary, fg=t.text_primary,
                          activebackground=t.accent, activeforeground=t.accent_text,
                          relief="flat", borderwidth=0)
        root.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False,
                            bg=t.bg_secondary, fg=t.text_primary,
                            activebackground=t.accent, activeforeground=t.accent_text)
        file_menu.add_command(label="Open Notebook…", command=self._browse_notebook)
        file_menu.add_command(label="Set Output Directory…", command=self._browse_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False,
                             bg=t.bg_secondary, fg=t.text_primary,
                             activebackground=t.accent, activeforeground=t.accent_text)
        tools_menu.add_command(label="System Dependencies…", command=self._open_system_check)
        tools_menu.add_command(label="Open Log File", command=self._open_log_file)
        tools_menu.add_separator()
        tools_menu.add_command(label="Settings", command=self._open_settings)
        tools_menu.add_command(label="Clean Temp Files", command=self._clean_temp)
        tools_menu.add_command(label="Check for Updates", command=self._open_update_dialog)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=False,
                            bg=t.bg_secondary, fg=t.text_primary,
                            activebackground=t.accent, activeforeground=t.accent_text)
        help_menu.add_command(label=f"About {APP_NAME}", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        # ── Top title bar ─────────────────────────────────────────────
        title_bar = tk.Frame(root, bg=t.bg_secondary,
                             highlightbackground=t.border, highlightthickness=1)
        title_bar.pack(fill="x")

        Heading(title_bar, t, text=f"  {APP_NAME}").pack(side="left",
                                                           padx=t.pad_md, pady=t.pad_sm)
        BodyLabel(
            title_bar, t,
            text=f"Jupyter Notebook → PDF Converter  ·  v{APP_VERSION}",
            secondary=True,
        ).pack(side="left", padx=(0, t.pad_md))

        GhostButton(
            title_bar, t, text="⚙ Settings",
            command=self._open_settings,
            bg=t.bg_secondary,
        ).pack(side="right", padx=t.pad_sm, pady=t.pad_sm)

        GhostButton(
            title_bar, t, text="🔍 Dependencies",
            command=self._open_system_check,
            bg=t.bg_secondary,
        ).pack(side="right", padx=(0, 0), pady=t.pad_sm)

        # ── Main content area (grid for proper resizing) ─────────────
        main = tk.Frame(root, bg=t.bg_primary)
        main.pack(fill="both", expand=True, padx=t.pad_md, pady=t.pad_md)

        # Grid: left column expands, right column fixed at 300 px minimum
        main.columnconfigure(0, weight=3)   # left: takes all spare space
        main.columnconfigure(1, weight=1, minsize=300)  # right: resizes too
        main.rowconfigure(0, weight=1)

        # Left column (input + options + progress)
        left = tk.Frame(main, bg=t.bg_primary)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, t.pad_sm))
        left.columnconfigure(0, weight=1)

        self._build_input_card(left)
        self._build_options_card(left)
        self._build_progress_card(left)

        # Right column (log console only — status moved to SystemCheckDialog)
        right = tk.Frame(main, bg=t.bg_primary)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)  # log console takes full height

        self._build_log_console(right)

    # ------------------------------------------------------------------ #
    # Input card                                                           #
    # ------------------------------------------------------------------ #

    def _build_input_card(self, parent: tk.Frame) -> None:
        t = self._theme
        card = Card(parent, t)
        card.pack(fill="x", pady=(0, t.pad_sm))

        inner = tk.Frame(card, bg=t.bg_secondary, padx=t.pad_md, pady=t.pad_md)
        inner.pack(fill="both")

        SubHeading(inner, t, text="Input Notebook").pack(anchor="w", pady=(0, t.pad_sm))

        # Drop zone
        self._drop_zone = DropZone(
            inner, t,
            on_file_selected=self._on_notebook_selected,
            height=110,
        )
        self._drop_zone.pack(fill="x", pady=(0, t.pad_sm))

        # Output directory row
        out_row = tk.Frame(inner, bg=t.bg_secondary)
        out_row.pack(fill="x")

        BodyLabel(out_row, t, text="Output Folder:").pack(side="left", padx=(0, 8))

        self._output_var = tk.StringVar(value=self._output_dir or "Same as notebook")
        out_entry = tk.Entry(
            out_row,
            textvariable=self._output_var,
            bg=t.bg_tertiary,
            fg=t.text_primary,
            insertbackground=t.text_primary,
            relief="flat",
            font=_font(t),
        )
        out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)

        GhostButton(
            out_row, t, text="Browse…",
            command=self._browse_output_dir,
            bg=t.bg_secondary,
        ).pack(side="right")

    # ------------------------------------------------------------------ #
    # Options card                                                         #
    # ------------------------------------------------------------------ #

    def _build_options_card(self, parent: tk.Frame) -> None:
        t = self._theme
        card = Card(parent, t)
        card.pack(fill="x", pady=(0, t.pad_sm))

        inner = tk.Frame(card, bg=t.bg_secondary, padx=t.pad_md, pady=t.pad_md)
        inner.pack(fill="both")

        SubHeading(inner, t, text="Conversion Method").pack(anchor="w", pady=(0, t.pad_sm))

        method_frame = tk.Frame(inner, bg=t.bg_secondary)
        method_frame.pack(fill="x")

        self._method_var = tk.StringVar(value=self._settings.preferred_method)

        for col, (label, value, desc) in enumerate([
            ("Browser", METHOD_BROWSER, "Chrome / Edge / Brave\nHeadless rendering"),
            ("LaTeX",   METHOD_LATEX,   "MiKTeX / TeX Live\nHigh-fidelity typesetting"),
        ]):
            method_frame.columnconfigure(col, weight=1, uniform="method")
            tile = tk.Frame(
                method_frame,
                bg=t.bg_tertiary,
                highlightbackground=t.border,
                highlightthickness=1,
                cursor="hand2",
            )
            tile.grid(row=0, column=col, padx=(0 if col else 0, t.pad_sm if col == 0 else 0),
                      sticky="nsew")

            rb = tk.Radiobutton(
                tile,
                text=label,
                variable=self._method_var,
                value=value,
                bg=t.bg_tertiary,
                fg=t.text_primary,
                selectcolor=t.bg_tertiary,
                activebackground=t.bg_tertiary,
                font=_font(t, t.font_size_md, bold=True),
                indicatoron=True,
            )
            rb.pack(anchor="w", padx=t.pad_sm, pady=(t.pad_sm, 2))

            tk.Label(
                tile,
                text=desc,
                bg=t.bg_tertiary,
                fg=t.text_secondary,
                font=_font(t, t.font_size_sm),
                justify="left",
            ).pack(anchor="w", padx=(t.pad_md + 4, t.pad_sm), pady=(0, t.pad_sm))

            tile.bind("<Button-1>", lambda e, v=value: self._method_var.set(v))

    # ------------------------------------------------------------------ #
    # Progress card                                                        #
    # ------------------------------------------------------------------ #

    def _build_progress_card(self, parent: tk.Frame) -> None:
        t = self._theme
        card = Card(parent, t)
        card.pack(fill="x", pady=(0, t.pad_sm))

        inner = tk.Frame(card, bg=t.bg_secondary, padx=t.pad_md, pady=t.pad_md)
        inner.pack(fill="both")

        # Status row
        status_row = tk.Frame(inner, bg=t.bg_secondary)
        status_row.pack(fill="x", pady=(0, t.pad_sm))

        self._status_dot = StatusDot(status_row, t, status="unknown")
        self._status_dot.pack(side="left", padx=(0, 8))

        self._status_text = tk.Label(
            status_row,
            text="Ready",
            bg=t.bg_secondary,
            fg=t.text_secondary,
            font=_font(t, t.font_size_md),
        )
        self._status_text.pack(side="left")

        self._progress_bar = ProgressBar(inner, t)
        self._progress_bar.pack(fill="x", pady=(0, t.pad_md))

        # Convert button
        btn_row = tk.Frame(inner, bg=t.bg_secondary)
        btn_row.pack(fill="x")

        self._convert_btn = AccentButton(
            btn_row, t,
            text="▶  Convert to PDF",
            command=self._start_conversion,
        )
        self._convert_btn.pack(side="left")

        self._open_btn = GhostButton(
            btn_row, t,
            text="Open PDF",
            command=self._open_output_pdf,
            bg=t.bg_secondary,
        )
        self._open_btn.pack(side="left", padx=(t.pad_sm, 0))
        self._open_btn.configure(state="disabled")

        self._clean_btn = GhostButton(
            btn_row, t,
            text="🧹 Clean Temp",
            command=self._clean_temp,
            bg=t.bg_secondary,
        )
        self._clean_btn.pack(side="right")

        self._last_output: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Log console                                                          #
    # ------------------------------------------------------------------ #

    def _build_log_console(self, parent: tk.Frame) -> None:
        t = self._theme
        self._log_console = LogConsole(parent, t)
        self._log_console.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Conversion logic                                                     #
    # ------------------------------------------------------------------ #

    def _start_conversion(self) -> None:
        if self._converting:
            return

        # Validate inputs
        nb_error = validate_notebook_path(self._notebook_path)
        if nb_error:
            messagebox.showerror("Input Error", nb_error, parent=self._root)
            return

        output_dir = self._output_var.get().strip()
        if not output_dir or output_dir == "Same as notebook":
            output_dir = os.path.dirname(self._notebook_path)
        out_error = validate_output_dir(output_dir)
        if out_error:
            messagebox.showerror("Output Error", out_error, parent=self._root)
            return

        self._output_dir = output_dir
        output_path = derive_output_path(self._notebook_path, output_dir)
        method = self._method_var.get()

        self._set_converting(True)
        self._progress_bar.reset()
        self._set_status("Converting…", "info")

        threading.Thread(
            target=self._conversion_worker,
            args=(self._notebook_path, output_path, method),
            daemon=True,
        ).start()

    def _conversion_worker(
        self, notebook_path: str, output_path: str, method: str
    ) -> None:
        try:
            converter = ConverterFactory.create(method)

            def progress_cb(percent: int, message: str) -> None:
                self._root.after(0, lambda p=percent, m=message: (
                    self._progress_bar.set(p),
                    self._set_status(m, "info"),
                ))

            result = converter.convert(notebook_path, output_path, progress_cb)

        except Exception as exc:
            logger.error(
                f"Unhandled exception in conversion thread: {exc}", exc_info=True
            )
            from core.base_converter import ConversionResult
            result = ConversionResult.fail(
                f"Unexpected error during conversion:\n{type(exc).__name__}: {exc}"
            )

        self._root.after(0, lambda r=result: self._on_conversion_done(r))

    def _on_conversion_done(self, result) -> None:
        self._set_converting(False)

        if result.success:
            size = human_readable_size(result.output_path)
            self._set_status(f"Done — {os.path.basename(result.output_path)} ({size})", "ok")
            self._progress_bar.set(100)
            self._last_output = result.output_path
            self._open_btn.configure(state="normal")

            if self._settings.open_pdf_after_conversion:
                self._open_output_pdf()

            # Clean temp artefacts
            self._cleaner.clean_conversion_artefacts(self._notebook_path)
        else:
            logger.error(f"Conversion failed: {result.error_message}")
            self._set_status("Conversion failed — see log", "error")
            self._progress_bar.set(0)
            messagebox.showerror(
                "Conversion Failed",
                result.error_message,
                parent=self._root,
            )

    # ------------------------------------------------------------------ #
    # System checks                                                        #
    # ------------------------------------------------------------------ #

    def _run_system_checks(self) -> None:
        """Run checks in background; results are shown in SystemCheckDialog."""
        threading.Thread(
            target=self._checker.run_all, daemon=True
        ).start()

    def _install_packages(self, packages: list) -> None:
        self._set_status(f"Installing {packages}…", "info")
        threading.Thread(
            target=self._install_worker,
            args=(packages,),
            daemon=True,
        ).start()

    def _install_worker(self, packages: list) -> None:
        result = self._checker.install_packages(packages)
        if result.returncode == 0:
            self._root.after(0, lambda: (
                self._set_status("Packages installed — re-checking…", "ok"),
                self._run_system_checks(),
            ))
        else:
            self._root.after(0, lambda: (
                self._set_status("Package installation failed — see log", "error"),
                messagebox.showerror(
                    "Installation Failed",
                    result.stderr[-800:],
                    parent=self._root,
                ),
            ))

    # ------------------------------------------------------------------ #
    # Update check                                                         #
    # ------------------------------------------------------------------ #

    def _background_update_check(self) -> None:
        info = self._update_checker.check_for_updates()
        if info and info.is_newer:
            self._root.after(
                0,
                lambda: self._notify_update_available(info.latest_version),
            )

    def _notify_update_available(self, version: str) -> None:
        if messagebox.askyesno(
            "Update Available",
            f"NB2PDF {version} is available.\n\nOpen the update dialog?",
            parent=self._root,
        ):
            self._open_update_dialog()

    def _open_update_dialog(self) -> None:
        UpdateDialog(self._root, self._theme, self._update_checker)

    # ------------------------------------------------------------------ #
    # Helpers / callbacks                                                  #
    # ------------------------------------------------------------------ #

    def _on_notebook_selected(self, path: str) -> None:
        self._notebook_path = path
        self._settings.last_input_dir = os.path.dirname(path)
        if not self._output_dir:
            self._output_var.set(os.path.dirname(path))
        self._set_status("Notebook loaded — ready to convert", "ok")
        logger.info(f"Notebook selected: {path}")

    def _browse_notebook(self) -> None:
        initial = self._settings.last_input_dir or os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Select Jupyter Notebook",
            initialdir=initial,
            filetypes=[("Jupyter Notebooks", "*.ipynb"), ("All Files", "*.*")],
            parent=self._root,
        )
        if path:
            self._drop_zone.set_file(path)
            self._on_notebook_selected(path)

    def _browse_output_dir(self) -> None:
        initial = self._output_dir or os.path.expanduser("~")
        directory = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=initial,
            parent=self._root,
        )
        if directory:
            self._output_dir = directory
            self._output_var.set(directory)

    def _open_output_pdf(self) -> None:
        if not self._last_output or not os.path.isfile(self._last_output):
            messagebox.showinfo(
                "No PDF", "No PDF has been generated yet.", parent=self._root
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(self._last_output)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self._last_output])
            else:
                subprocess.Popen(["xdg-open", self._last_output])
        except Exception as exc:
            messagebox.showerror("Cannot Open PDF", str(exc), parent=self._root)

    def _open_system_check(self) -> None:
        """Open the system dependencies check dialog."""
        SystemCheckDialog(
            self._root,
            self._theme,
            self._checker,
            on_install_packages=self._install_packages,
        )

    def _open_log_file(self) -> None:
        """Open the log file in the system default text editor."""
        from config.constants import APP_NAME, LOG_FILENAME
        log_path = os.path.join(get_logs_dir(APP_NAME), LOG_FILENAME)
        if not os.path.isfile(log_path):
            messagebox.showinfo(
                "Log File",
                f"Log file not found:\n{log_path}\n\nNo events have been logged yet.",
                parent=self._root,
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(log_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", log_path])
            else:
                subprocess.Popen(["xdg-open", log_path])
        except Exception as exc:
            messagebox.showerror("Cannot Open Log", str(exc), parent=self._root)

    def _open_settings(self) -> None:
        SettingsDialog(
            self._root,
            self._theme,
            self._settings,
            on_theme_change=self._apply_theme,
        )

    def _clean_temp(self) -> None:
        removed = self._cleaner.clean_all()
        messagebox.showinfo(
            "Temp Files Cleaned",
            f"Removed {len(removed)} temporary item(s).",
            parent=self._root,
        )

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            (
                f"{APP_NAME} — Jupyter Notebook to PDF Converter\n"
                f"Version {APP_VERSION}\n\n"
                "Converts .ipynb notebooks to PDF using either\n"
                "a headless browser or a LaTeX pipeline.\n\n"
                "Built with Python + Tkinter."
            ),
            parent=self._root,
        )

    def _set_converting(self, state: bool) -> None:
        self._converting = state
        btn_state = "disabled" if state else "normal"
        self._convert_btn.configure(
            state=btn_state,
            text="Converting…" if state else "▶  Convert to PDF",
        )

    def _set_status(self, message: str, level: str = "info") -> None:
        level_map = {
            "ok":    ("ok",      self._theme.color_ok),
            "error": ("error",   self._theme.color_error),
            "warn":  ("warn",    self._theme.color_warn),
            "info":  ("info",    self._theme.color_info),
        }
        dot_status, color = level_map.get(level, ("unknown", self._theme.text_secondary))
        self._status_dot.set_status(dot_status)
        self._status_text.configure(text=message, fg=color)

    def _apply_theme(self, theme_name: str) -> None:
        """Notify user that a restart is needed for theme change."""
        self._settings.theme = theme_name
        self._settings.save()
        messagebox.showinfo(
            "Theme Changed",
            "The new theme will be applied when you restart NB2PDF.",
            parent=self._root,
        )

    def _set_window_icon(self) -> None:
        set_window_icon(self._root)

    def _apply_window_size(self) -> None:
        self._root.geometry("980x680")
        # Centre on screen
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = 980, 680
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")
