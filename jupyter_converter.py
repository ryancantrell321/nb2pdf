software_version = 2026.01

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, subprocess, sys, os, shutil, queue, gc, time, atexit
from pathlib import Path
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# Instance lock — prevents multiple copies running simultaneously
# ══════════════════════════════════════════════════════════════════════════════

def _get_lock_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) \
           else Path(__file__).parent
    return base / "notebook_converter.lock"


def acquire_instance_lock():
    """
    Acquires an exclusive file lock so only one instance can run.
    Uses portalocker if installed, falls back to a PID-file approach.
    Shows a messagebox and exits if another instance is detected.
    """
    lock_path = _get_lock_path()

    try:
        import portalocker

        lock_fd = open(lock_path, "w")
        try:
            portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException:
            lock_fd.close()
            _root = tk.Tk()
            _root.withdraw()
            messagebox.showerror(
                "Already Running",
                "Notebook → PDF Converter is already running.\n"
                "Check your taskbar."
            )
            _root.destroy()
            sys.exit(1)

        lock_fd.write(str(os.getpid()))
        lock_fd.flush()

        def _release():
            try:
                portalocker.unlock(lock_fd)
                lock_fd.close()
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass

        atexit.register(_release)
        return lock_fd

    except ImportError:
        # Fallback: plain PID file (no portalocker installed)
        if lock_path.exists():
            try:
                pid = int(lock_path.read_text().strip())
                alive = False
                try:
                    import psutil
                    alive = psutil.pid_exists(pid)
                except ImportError:
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except OSError:
                        alive = False

                if alive:
                    _root = tk.Tk()
                    _root.withdraw()
                    messagebox.showerror(
                        "Already Running",
                        "Notebook → PDF Converter is already running.\n"
                        "Check your taskbar."
                    )
                    _root.destroy()
                    sys.exit(1)
            except (ValueError, OSError):
                pass  # stale lock — overwrite

        lock_path.write_text(str(os.getpid()))
        atexit.register(lambda: lock_path.unlink(missing_ok=True))
        return None


_LOCK_FD = acquire_instance_lock()


# ══════════════════════════════════════════════════════════════════════════════
# Memory cleaner — background daemon thread
# ══════════════════════════════════════════════════════════════════════════════

class MemoryCleaner:
    """
    Calls gc.collect() every `interval_sec` seconds.
    If psutil is installed, also reports RSS memory to the app log.
    """

    def __init__(self, interval_sec: int = 30, log_cb=None):
        self._interval = interval_sec
        self._log_cb   = log_cb
        self._stop     = threading.Event()
        self._thread   = threading.Thread(
            target=self._run, daemon=True, name="MemoryCleaner"
        )

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(timeout=self._interval):
            collected = gc.collect()
            if self._log_cb and collected:
                try:
                    import psutil
                    mb = psutil.Process(os.getpid()).memory_info().rss / 1_048_576
                    self._log_cb(
                        f"[GC] freed {collected} objects  •  RSS {mb:.1f} MB",
                        "dim"
                    )
                except ImportError:
                    self._log_cb(f"[GC] freed {collected} objects", "dim")


# ══════════════════════════════════════════════════════════════════════════════
# Resource path — works for script, PyInstaller, and Nuitka bundles
# ══════════════════════════════════════════════════════════════════════════════

def resource_path(filename: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).parent
    return base / filename


# ══════════════════════════════════════════════════════════════════════════════
# Optional drag-and-drop
# ══════════════════════════════════════════════════════════════════════════════

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# Design tokens
# ══════════════════════════════════════════════════════════════════════════════

BG          = "#0F0F13"      # near-black canvas
CARD        = "#17171E"      # card surface
CARD2       = "#1E1E28"      # card surface elevated
BORDER      = "#2A2A38"      # subtle border
ACCENT      = "#6C63FF"      # violet
ACCENT2     = "#4ECCA3"      # teal — second accent
TEXT        = "#EAEAF2"      # primary text
MUTED       = "#6B6B88"      # secondary text
OK          = "#4ECCA3"
WARN        = "#FFB347"
ERR         = "#FF6B6B"

# Font stack
TF  = ("Segoe UI Semibold", 22)   # hero title
HF  = ("Segoe UI Semibold", 11)   # card heading
BF  = ("Segoe UI", 10)             # body
SF  = ("Segoe UI", 9)              # small / muted
MF  = ("Consolas", 9)              # mono log

# ══════════════════════════════════════════════════════════════════════════════
# Conversion engine  (Chrome/Edge/Brave  +  LaTeX only)
# ══════════════════════════════════════════════════════════════════════════════

class Engine:

    # ── dependency probes ──────────────────────────────────────────────────────

    @staticmethod
    def deps() -> dict:
        d = {}
        for pkg in ("nbconvert", "nbformat"):
            try:
                m = __import__(pkg)
                d[pkg] = getattr(m, "__version__", "installed")
            except Exception:
                d[pkg] = None
        d["browser"]      = Engine._find_browser()
        d["browser_name"] = Path(d["browser"]).stem if d["browser"] else None
        d["latex"]        = shutil.which("xelatex") or shutil.which("pdflatex")
        return d

    @staticmethod
    def _find_browser() -> str | None:
        candidates = [
            # Brave
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            # Chrome
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            # Edge — pre-installed on Windows 10/11
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for name in ("brave", "chrome", "google-chrome", "chromium", "msedge"):
            found = shutil.which(name)
            if found:
                return found
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    # ── shared subprocess ──────────────────────────────────────────────────────

    @staticmethod
    def _python() -> str:
        """
        Return the real Python interpreter path.
        When bundled with Nuitka/PyInstaller, sys.executable is the .exe itself,
        so we must locate the actual python.exe on PATH instead.
        """
        if getattr(sys, "frozen", False):
            # Try to find python.exe on PATH
            py = shutil.which("python") or shutil.which("python3")
            if py:
                return py
            # Last resort: look next to the exe (portable installs)
            exe_dir = Path(sys.executable).parent
            for name in ("python.exe", "python3.exe"):
                candidate = exe_dir / name
                if candidate.exists():
                    return str(candidate)
            raise RuntimeError(
                "Cannot find python.exe. Make sure Python is on your PATH."
            )
        return sys.executable

    @staticmethod
    def _run(cmd, cwd=None):
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        r = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=cwd, creationflags=flags)
        return r.returncode, r.stdout, r.stderr

    @staticmethod
    def _to_html(src, tmp, log):
        cmd = [Engine._python(), "-m", "nbconvert", "--to", "html",
               "--output", src.stem, "--output-dir", str(tmp), str(src)]
        log("  Exporting notebook → HTML …")
        rc, out, err = Engine._run(cmd)
        html = Path(tmp) / (src.stem + ".html")
        if rc != 0 or not html.exists():
            return None, (out + "\n" + err).strip()
        return html, ""

    # ── Method A: Browser headless ─────────────────────────────────────────────

    @staticmethod
    def convert_browser(ipynb: str, out_dir: str, log) -> tuple:
        browser = Engine._find_browser()
        if not browser:
            return False, ("No Chromium-based browser found.\n"
                           "Install Chrome, Edge, or Brave.")
        try:
            import nbconvert  # noqa
        except ImportError:
            return False, "nbconvert not installed.  Run: pip install nbconvert"

        import tempfile
        src = Path(ipynb)
        out_pdf = Path(out_dir) / (src.stem + ".pdf")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            html, err = Engine._to_html(src, tmp, log)
            if html is None:
                return False, err

            bname = Path(browser).stem
            log(f"  Rendering PDF via {bname} headless …")
            cmd = [
                browser,
                "--headless=new", "--disable-gpu",
                "--no-sandbox", "--disable-dev-shm-usage",
                "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={out_pdf}",
                str(html),
            ]
            rc, out, err = Engine._run(cmd)
            if out_pdf.exists() and out_pdf.stat().st_size > 1000:
                log(f"  ✔  Saved → {out_pdf.name}")
                return True, str(out_pdf)
            return False, (out + "\n" + err).strip()[:300]

    # ── Method B: LaTeX ────────────────────────────────────────────────────────

    @staticmethod
    def convert_latex(ipynb: str, out_dir: str, log) -> tuple:
        latex = shutil.which("xelatex") or shutil.which("pdflatex")
        if not latex:
            return False, ("No LaTeX compiler found.\n"
                           "Install MiKTeX: https://miktex.org/download")
        try:
            import nbconvert  # noqa
        except ImportError:
            return False, "nbconvert not installed.  Run: pip install nbconvert"

        import tempfile, shutil as sh
        src = Path(ipynb)
        out_pdf = Path(out_dir) / (src.stem + ".pdf")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            cmd = [Engine._python(), "-m", "nbconvert", "--to", "latex",
                   "--output", src.stem, "--output-dir", tmp, str(src)]
            log("  Exporting notebook → LaTeX …")
            rc, out, err = Engine._run(cmd)
            if rc != 0:
                return False, (out + "\n" + err).strip()

            tex = Path(tmp) / (src.stem + ".tex")
            log(f"  Compiling with {Path(latex).stem} …")
            for _ in range(2):
                rc, out, err = Engine._run(
                    [latex, "-interaction=nonstopmode", tex.name], cwd=tmp)
            compiled = Path(tmp) / (src.stem + ".pdf")
            if compiled.exists():
                sh.copy2(compiled, out_pdf)
                log(f"  ✔  Saved → {out_pdf.name}")
                return True, str(out_pdf)
            return False, (out + "\n" + err).strip()[-400:]

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    @staticmethod
    def convert(ipynb: str, out_dir: str, method: str, log_cb=None) -> tuple:
        def log(m):
            if log_cb: log_cb(m)
        log(f"▸  {Path(ipynb).name}")
        if method == "browser":
            return Engine.convert_browser(ipynb, out_dir, log)
        if method == "latex":
            return Engine.convert_latex(ipynb, out_dir, log)
        return False, f"Unknown method: {method}"


# ══════════════════════════════════════════════════════════════════════════════
# Custom tkinter widgets
# ══════════════════════════════════════════════════════════════════════════════

def card(parent, **kw) -> tk.Frame:
    """A rounded-look card frame."""
    defaults = dict(bg=CARD, highlightbackground=BORDER,
                    highlightthickness=1, padx=0, pady=0)
    defaults.update(kw)
    return tk.Frame(parent, **defaults)


class HoverButton(tk.Label):
    """A label that behaves like a styled button with hover states."""
    def __init__(self, parent, text, command,
                 bg=ACCENT, fg=TEXT, hover_bg=None,
                 font=BF, padx=18, pady=8, **kw):
        self._bg     = bg
        self._hbg    = hover_bg or _darken(bg)
        self._cmd    = command
        super().__init__(parent, text=text, bg=bg, fg=fg,
                         font=font, padx=padx, pady=pady,
                         cursor="hand2", **kw)
        self.bind("<Enter>",    lambda e: self.config(bg=self._hbg))
        self.bind("<Leave>",    lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._cmd())

    def set_state(self, enabled: bool):
        if enabled:
            self.config(cursor="hand2")
            self.bind("<Button-1>", lambda e: self._cmd())
        else:
            self.config(cursor="")
            self.unbind("<Button-1>")


def _darken(hex_color: str, factor: float = 0.82) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r * factor), int(g * factor), int(b * factor))


class Pill(tk.Label):
    """Small coloured badge."""
    def __init__(self, parent, text, color=MUTED, **kw):
        super().__init__(parent, text=f"  {text}  ",
                         bg=color, fg=BG,
                         font=("Segoe UI Semibold", 8),
                         **kw)


class FileCard(tk.Frame):
    """One notebook entry rendered as a card."""

    STATUS_CFG = {
        "queued":     ("QUEUED",      MUTED,   CARD2),
        "converting": ("CONVERTING",  WARN,    CARD2),
        "done":       ("DONE",        OK,      "#141C1A"),
        "error":      ("FAILED",      ERR,     "#1C1414"),
    }

    def __init__(self, parent, path: str, on_remove, **kw):
        super().__init__(parent, bg=CARD2,
                         highlightbackground=BORDER, highlightthickness=1, **kw)
        self.path    = path
        self._status = "queued"
        self._build()

    def _build(self):
        # Left accent stripe
        self._stripe = tk.Frame(self, bg=MUTED, width=4)
        self._stripe.pack(side="left", fill="y")

        body = tk.Frame(self, bg=CARD2)
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        # Top row: filename + badge + remove
        top = tk.Frame(body, bg=CARD2)
        top.pack(fill="x")

        name = Path(self.path).name
        tk.Label(top, text=name, bg=CARD2, fg=TEXT,
                 font=HF, anchor="w").pack(side="left")

        self._badge = tk.Label(top, text="  QUEUED  ",
                                bg=CARD2, fg=MUTED,
                                font=("Segoe UI Semibold", 8))
        self._badge.pack(side="left", padx=(10, 0))

        # Remove button
        rb = tk.Label(top, text="✕", bg=CARD2, fg=MUTED,
                      font=SF, cursor="hand2", padx=6)
        rb.pack(side="right")
        rb.bind("<Enter>", lambda e: rb.config(fg=ERR))
        rb.bind("<Leave>", lambda e: rb.config(fg=MUTED))
        rb.bind("<Button-1>", lambda e: self._on_remove())
        self._remove_btn = rb

        # Bottom row: path + progress bar (hidden initially)
        bot = tk.Frame(body, bg=CARD2)
        bot.pack(fill="x", pady=(4, 0))

        short = str(Path(self.path).parent)
        if len(short) > 70: short = "…" + short[-67:]
        tk.Label(bot, text=short, bg=CARD2, fg=MUTED,
                 font=SF, anchor="w").pack(side="left")

        self._bar = ttk.Progressbar(bot, mode="indeterminate", length=120)

    def _on_remove(self):
        if hasattr(self, "_remove_cb") and self._remove_cb:
            self._remove_cb(self)

    def set_remove_cb(self, cb):
        self._remove_cb = cb

    def set_status(self, status: str):
        self._status = status
        label, colour, bg = self.STATUS_CFG.get(status, ("?", MUTED, CARD2))
        self._stripe.config(bg=colour)
        self._badge.config(text=f"  {label}  ", fg=colour, bg=CARD2)
        self.config(bg=bg, highlightbackground=colour if status in ("done","error") else BORDER)
        self._remove_btn.config(bg=bg)
        for w in self.winfo_children():
            _set_bg_recursive(w, bg)
        self._stripe.config(bg=colour)   # restore stripe after recursive set
        self._badge.config(bg=CARD2)

        if status == "converting":
            self._bar.pack(side="right", padx=(8, 0))
            self._bar.start(10)
        else:
            self._bar.stop()
            self._bar.pack_forget()

    @property
    def status(self): return self._status


def _set_bg_recursive(widget, bg):
    try: widget.config(bg=bg)
    except Exception: pass
    for child in widget.winfo_children():
        _set_bg_recursive(child, bg)


# ══════════════════════════════════════════════════════════════════════════════
# Dialogs
# ══════════════════════════════════════════════════════════════════════════════

class DepsDialog(tk.Toplevel):
    def __init__(self, parent, deps: dict):
        super().__init__(parent)
        self.title("System Check")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._build(deps)
        self.update_idletasks()
        w, h = 520, 380
        self.geometry(f"{w}x{h}")
        x = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self, deps):
        # Header
        hdr = tk.Frame(self, bg=CARD, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="System Check", bg=CARD, fg=TEXT, font=TF,
                 padx=24).pack(side="left")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        rows = [
            ("nbconvert",      "Core converter",              deps.get("nbconvert")),
            ("nbformat",       "Notebook reader",             deps.get("nbformat")),
            ("Chrome/Edge/Brave", "Browser PDF method",       deps.get("browser_name")),
            ("LaTeX (xelatex/pdflatex)", "LaTeX PDF method",  deps.get("latex")),
        ]

        for name, desc, val in rows:
            row = tk.Frame(body, bg=CARD2,
                           highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=3)

            dot_col = OK if val else ERR
            tk.Label(row, text="●", bg=CARD2, fg=dot_col,
                     font=("Segoe UI", 12), padx=12, pady=10).pack(side="left")
            tk.Label(row, text=name, bg=CARD2, fg=TEXT,
                     font=HF, width=22, anchor="w").pack(side="left")
            tk.Label(row, text=desc, bg=CARD2, fg=MUTED,
                     font=SF).pack(side="left")
            status_txt = str(val) if val else "not found"
            status_col = OK if val else MUTED
            tk.Label(row, text=status_txt, bg=CARD2, fg=status_col,
                     font=SF, padx=12).pack(side="right")

        # Install hint
        hint = card(body, bg=CARD)
        hint.pack(fill="x", pady=(14, 0))
        tk.Label(hint, text="  pip install nbconvert nbformat",
                 bg=CARD, fg=ACCENT2, font=MF, pady=10, anchor="w").pack(fill="x")

        HoverButton(self, "Close", self.destroy,
                    bg=CARD2, hover_bg=BORDER, fg=TEXT,
                    font=BF).pack(pady=16)


# ══════════════════════════════════════════════════════════════════════════════
# Main application
# ══════════════════════════════════════════════════════════════════════════════

BaseClass = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk


class App(BaseClass):

    def __init__(self):
        super().__init__()
        self.title("Notebook → PDF")
        self.configure(bg=BG)
        self.geometry("960x700")
        self.minsize(780, 580)
        ico = resource_path("notebook_to_pdf.ico")
        self.iconbitmap(str(ico))

        # State
        self._rows    = []
        self._q       = queue.Queue()
        self._busy    = False
        self._out_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        self._method  = tk.StringVar(value="browser")

        # ttk styles (progress bar)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar",
                        background=ACCENT, troughcolor=CARD2,
                        bordercolor=CARD2, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("Thin.Horizontal.TProgressbar",
                        background=ACCENT, troughcolor=BORDER,
                        thickness=3)

        self._build()
        self._poll()
        self.after(200, self._startup_check)

        # Start memory cleaner — logs to app every 30 s
        self._mem_cleaner = MemoryCleaner(
            interval_sec=30,
            log_cb=self._log
        ).start()

        # Stop cleaner gracefully when window closes
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._mem_cleaner.stop()
        self.destroy()

    # ══ Layout ════════════════════════════════════════════════════════════════
    # Pack order: sidebar (left) | main column (right, fills)
    # Inside main column: bottom bar first, then scrollable content
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self):
        # ── Sidebar ────────────────────────────────────────────────────────────
        sidebar = tk.Frame(self, bg=CARD, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # ── Main area ──────────────────────────────────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        self._build_bottom_bar(main)   # bottom first — always visible
        self._build_log_panel(main)    # above bottom bar
        self._build_file_area(main)    # fills remaining space

    # ── Sidebar ────────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        # App name / logo area
        brand = tk.Frame(parent, bg=CARD, pady=0)
        brand.pack(fill="x")

        accent_bar = tk.Frame(brand, bg=ACCENT, height=3)
        accent_bar.pack(fill="x")

        tk.Label(brand, text="nb → pdf", bg=CARD, fg=TEXT,
                 font=TF, pady=20, padx=20, anchor="w").pack(fill="x")
        tk.Label(brand, text="Notebook Converter", bg=CARD, fg=MUTED,
                 font=SF, padx=20, anchor="w").pack(fill="x")

        divider(parent, bg=BORDER)

        # ── Method selector ────────────────────────────────────────────────────
        tk.Label(parent, text="METHOD", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8),
                 padx=20, pady=8, anchor="w").pack(fill="x", pady=(8, 0))

        self._method_btns = {}
        methods = [
            ("browser", "Chrome / Edge / Brave",
             "Uses your installed browser.\nNo extra setup required."),
            ("latex",   "LaTeX",
             "Highest quality typesetting.\nRequires MiKTeX or TeX Live."),
        ]
        for key, label, tip in methods:
            btn = self._method_btn(parent, key, label, tip)
            self._method_btns[key] = btn

        self._select_method("browser")   # default

        divider(parent, bg=BORDER)

        # ── Output folder ──────────────────────────────────────────────────────
        tk.Label(parent, text="OUTPUT FOLDER", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8),
                 padx=20, pady=6, anchor="w").pack(fill="x", pady=(10, 2))

        dir_card = tk.Frame(parent, bg=CARD2,
                            highlightbackground=BORDER, highlightthickness=1)
        dir_card.pack(fill="x", padx=14, pady=(0, 4))

        self._dir_lbl = tk.Label(dir_card, bg=CARD2, fg=TEXT,
                                  font=SF, anchor="w",
                                  wraplength=170, justify="left",
                                  padx=10, pady=8)
        self._dir_lbl.pack(fill="x")
        self._update_dir_label()
        self._out_dir.trace_add("write", lambda *_: self._update_dir_label())

        HoverButton(parent, "Change Folder", self._pick_dir,
                    bg=CARD2, hover_bg=BORDER, fg=MUTED,
                    font=SF, padx=14, pady=6,
                    anchor="w").pack(fill="x", padx=14, pady=(0, 4))

        HoverButton(parent, "Open Folder ↗", self._open_out,
                    bg=CARD2, hover_bg=BORDER, fg=MUTED,
                    font=SF, padx=14, pady=6,
                    anchor="w").pack(fill="x", padx=14)

        divider(parent, bg=BORDER)

        # ── System check button ────────────────────────────────────────────────
        HoverButton(parent, "System Check", self._show_deps,
                    bg=CARD2, hover_bg=BORDER, fg=MUTED,
                    font=SF, padx=14, pady=6,
                    anchor="w").pack(fill="x", padx=14, pady=(14, 4))

        # Spacer pushes version to bottom
        tk.Frame(parent, bg=CARD).pack(fill="both", expand=True)

        tk.Label(parent, text="v3.0  •  nbconvert", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8), pady=12).pack()

    def _method_btn(self, parent, key, label, tip):
        """Creates a clickable method card in the sidebar."""
        frm = tk.Frame(parent, bg=CARD, cursor="hand2")
        frm.pack(fill="x", padx=14, pady=2)

        indicator = tk.Frame(frm, bg=CARD, width=3)
        indicator.pack(side="left", fill="y")

        inner = tk.Frame(frm, bg=CARD, padx=10, pady=8)
        inner.pack(side="left", fill="both", expand=True)

        lbl  = tk.Label(inner, text=label, bg=CARD, fg=MUTED, font=HF, anchor="w")
        lbl.pack(fill="x")
        tip_lbl = tk.Label(inner, text=tip, bg=CARD, fg=MUTED,
                           font=("Segoe UI", 8), anchor="w",
                           wraplength=165, justify="left")
        tip_lbl.pack(fill="x")

        def on_click(_=None):
            self._select_method(key)

        for w in (frm, inner, lbl, tip_lbl, indicator):
            w.bind("<Button-1>", on_click)

        return {"frame": frm, "indicator": indicator,
                "lbl": lbl, "tip": tip_lbl, "inner": inner}

    def _select_method(self, key: str):
        self._method.set(key)
        for k, parts in self._method_btns.items():
            active = (k == key)
            bg       = CARD2   if active else CARD
            ind_col  = ACCENT  if active else CARD
            fg_lbl   = TEXT    if active else MUTED
            fg_tip   = MUTED   if True   else MUTED
            parts["frame"].config(bg=bg,
                                   highlightbackground=BORDER if active else CARD,
                                   highlightthickness=1 if active else 0)
            parts["inner"].config(bg=bg)
            parts["indicator"].config(bg=ind_col)
            parts["lbl"].config(bg=bg, fg=fg_lbl)
            parts["tip"].config(bg=bg)

    # ── Bottom bar (Convert button) ────────────────────────────────────────────

    def _build_bottom_bar(self, parent):
        bar = tk.Frame(parent, bg=CARD,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(side="bottom", fill="x")

        inner = tk.Frame(bar, bg=CARD)
        inner.pack(fill="x", padx=20, pady=14)

        # Progress + status (left)
        left = tk.Frame(inner, bg=CARD)
        left.pack(side="left", fill="x", expand=True)

        self._status_lbl = tk.Label(left, text="Ready — add notebooks to begin",
                                     bg=CARD, fg=MUTED, font=SF)
        self._status_lbl.pack(anchor="w")

        prog_row = tk.Frame(left, bg=CARD)
        prog_row.pack(fill="x", pady=(6, 0))

        self._prog_bar = ttk.Progressbar(prog_row, length=260,
                                          mode="determinate",
                                          style="Thin.Horizontal.TProgressbar")
        self._prog_bar.pack(side="left")
        self._prog_lbl = tk.Label(prog_row, text="", bg=CARD, fg=MUTED, font=SF)
        self._prog_lbl.pack(side="left", padx=(10, 0))

        # Convert button (right)
        self.btn_convert = HoverButton(
            inner, "  Convert All  →", self._start,
            bg=ACCENT, hover_bg=_darken(ACCENT),
            fg=TEXT, font=("Segoe UI Semibold", 11),
            padx=28, pady=12,
        )
        self.btn_convert.pack(side="right")

    # ── Log panel ──────────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        log_wrap = tk.Frame(parent, bg=BG)
        log_wrap.pack(side="bottom", fill="x", padx=20, pady=(0, 8))

        hdr = tk.Frame(log_wrap, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="CONVERSION LOG", bg=BG, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        HoverButton(hdr, "Clear", self._clear_log,
                    bg=BG, hover_bg=CARD, fg=MUTED,
                    font=SF, padx=8, pady=2).pack(side="right")

        log_card = tk.Frame(log_wrap, bg=CARD,
                             highlightbackground=BORDER, highlightthickness=1)
        log_card.pack(fill="x")

        self._log_box = tk.Text(
            log_card, height=5,
            bg=CARD, fg=TEXT, font=MF,
            relief="flat", bd=0, padx=12, pady=10,
            state="disabled", wrap="word",
        )
        self._log_box.pack(fill="x")
        self._log_box.tag_configure("ok",   foreground=OK)
        self._log_box.tag_configure("err",  foreground=ERR)
        self._log_box.tag_configure("warn", foreground=WARN)
        self._log_box.tag_configure("dim",  foreground=MUTED)
        self._log_box.tag_configure("acc",  foreground=ACCENT2)

    # ── File area (drop zone + cards list) ────────────────────────────────────

    def _build_file_area(self, parent):
        # Section header
        area_hdr = tk.Frame(parent, bg=BG)
        area_hdr.pack(side="top", fill="x", padx=20, pady=(20, 0))

        left_hdr = tk.Frame(area_hdr, bg=BG)
        left_hdr.pack(side="left")
        tk.Label(left_hdr, text="Notebooks", bg=BG, fg=TEXT, font=HF).pack(side="left")
        self._count_lbl = tk.Label(left_hdr, text="", bg=BG, fg=MUTED, font=SF)
        self._count_lbl.pack(side="left", padx=(8, 0))

        right_hdr = tk.Frame(area_hdr, bg=BG)
        right_hdr.pack(side="right")
        HoverButton(right_hdr, "Add Files", self._browse_files,
                    bg=CARD2, hover_bg=BORDER, fg=TEXT,
                    font=SF, padx=12, pady=5).pack(side="left", padx=(0, 6))
        HoverButton(right_hdr, "Add Folder", self._browse_folder,
                    bg=CARD2, hover_bg=BORDER, fg=TEXT,
                    font=SF, padx=12, pady=5).pack(side="left", padx=(0, 6))
        HoverButton(right_hdr, "Clear All", self._clear_all,
                    bg=BG, hover_bg=CARD, fg=MUTED,
                    font=SF, padx=12, pady=5).pack(side="left")

        # Drop zone (shown when empty) + scrollable card list
        content = tk.Frame(parent, bg=BG)
        content.pack(side="top", fill="both", expand=True, padx=20, pady=12)

        # Drop zone placeholder
        self._drop_zone = self._make_drop_zone(content)
        self._drop_zone.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Scrollable card list
        canvas = tk.Canvas(content, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
        self._card_frame = tk.Frame(canvas, bg=BG)
        self._card_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self._canvas_win = canvas.create_window(
            (0, 0), window=self._card_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(
                        self._canvas_win, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._canvas = canvas
        self._sb = sb
        self._content_frame = content

        # DnD
        if DND_AVAILABLE:
            self._drop_zone.drop_target_register(DND_FILES)
            self._drop_zone.dnd_bind("<<Drop>>", self._on_drop)
            self._card_frame.drop_target_register(DND_FILES)
            self._card_frame.dnd_bind("<<Drop>>", self._on_drop)

    def _make_drop_zone(self, parent) -> tk.Frame:
        frm = tk.Frame(parent, bg=BG,
                       highlightbackground=BORDER, highlightthickness=1)
        inner = tk.Frame(frm, bg=BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        # Large icon (using text)
        tk.Label(inner, text="⬇", bg=BG, fg=BORDER,
                 font=("Segoe UI Emoji", 36)).pack()

        tk.Label(inner,
                 text="Drop .ipynb files here" if DND_AVAILABLE
                      else "Add notebooks to get started",
                 bg=BG, fg=MUTED,
                 font=("Segoe UI Semibold", 13)).pack(pady=(8, 4))

        tk.Label(inner, text="or use the buttons above",
                 bg=BG, fg=MUTED, font=SF).pack()

        if DND_AVAILABLE:
            frm.drop_target_register(DND_FILES)
            frm.dnd_bind("<<Drop>>", self._on_drop)

        return frm

    def _update_drop_zone_visibility(self):
        if self._rows:
            self._drop_zone.place_forget()
        else:
            self._drop_zone.place(relx=0, rely=0, relwidth=1, relheight=1)

    # ══ Helpers ═══════════════════════════════════════════════════════════════

    def _update_dir_label(self):
        d = self._out_dir.get()
        short = d if len(d) <= 26 else "…" + d[-23:]
        self._dir_lbl.config(text=short)

    def _update_count(self):
        n = len(self._rows)
        if n:
            done  = sum(1 for r in self._rows if r.status == "done")
            fail  = sum(1 for r in self._rows if r.status == "error")
            parts = [f"{n} file{'s' if n>1 else ''}"]
            if done:  parts.append(f"{done} done")
            if fail:  parts.append(f"{fail} failed")
            self._count_lbl.config(text="  •  ".join(parts))
        else:
            self._count_lbl.config(text="")
        self._update_drop_zone_visibility()

    # ══ File management ═══════════════════════════════════════════════════════

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        self._add([p for p in paths if p.lower().endswith(".ipynb")])

    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Jupyter Notebooks",
            filetypes=[("Jupyter Notebooks", "*.ipynb"), ("All files", "*.*")]
        )
        if paths:
            self._add(list(paths))

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select folder with .ipynb files")
        if d:
            found = [str(p) for p in Path(d).rglob("*.ipynb")]
            if found:
                self._add(found)
            else:
                messagebox.showinfo("No notebooks found",
                                    f"No .ipynb files in:\n{d}")

    def _add(self, paths):
        existing = {r.path for r in self._rows}
        n = 0
        for p in paths:
            if p not in existing:
                fc = FileCard(self._card_frame, p, on_remove=None)
                fc.set_remove_cb(self._remove)
                fc.pack(fill="x", pady=3, padx=2)
                self._rows.append(fc)
                existing.add(p)
                n += 1
        if n:
            self._update_count()
            self._log(f"Added {n} notebook(s).", "dim")

    def _remove(self, card):
        if self._busy: return
        self._rows.remove(card)
        card.destroy()
        self._update_count()

    def _clear_all(self):
        if self._busy: return
        for r in self._rows: r.destroy()
        self._rows.clear()
        self._update_count()

    # ══ Output dir ════════════════════════════════════════════════════════════

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Output folder",
                                     initialdir=self._out_dir.get())
        if d: self._out_dir.set(d)

    def _open_out(self):
        d = self._out_dir.get()
        if os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showwarning("Not found", f"Folder does not exist:\n{d}")

    # ══ Logging ═══════════════════════════════════════════════════════════════

    def _log(self, text: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._q.put((f"[{ts}]  {text}\n", tag))

    def _poll(self):
        try:
            while True:
                msg, tag = self._q.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", msg, tag or ())
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ══ System check ══════════════════════════════════════════════════════════

    def _show_deps(self):
        deps = Engine.deps()
        DepsDialog(self, deps)

    def _startup_check(self):
        deps = Engine.deps()
        if not deps.get("nbconvert"):
            self._log("nbconvert not installed!  Run:  pip install nbconvert nbformat", "err")
        elif not deps.get("browser") and not deps.get("latex"):
            self._log("No conversion backend found. Install Chrome/Edge/Brave OR MiKTeX.", "warn")
        else:
            bname = deps.get("browser_name") or "—"
            latex = "✔" if deps.get("latex") else "✗"
            self._log(
                f"Ready.  Browser: {bname}   LaTeX: {latex}   "
                f"nbconvert: {deps.get('nbconvert', '✗')}",
                "acc"
            )

    # ══ Conversion ════════════════════════════════════════════════════════════

    def _start(self):
        if self._busy: return
        pending = [r for r in self._rows if r.status not in ("done",)]
        if not pending:
            messagebox.showinfo("Nothing to do",
                                "Add notebooks above, then click Convert All.")
            return
        out = self._out_dir.get().strip()
        if not out:
            messagebox.showerror("No output folder", "Set an output folder first.")
            return

        method = self._method.get()
        self._busy = True
        self.btn_convert.set_state(False)
        self.btn_convert.config(text="  Converting…  ", bg=_darken(ACCENT))

        self._prog_bar["maximum"] = len(pending)
        self._prog_bar["value"]   = 0
        self._status_lbl.config(text=f"Converting 0 / {len(pending)}…")
        self._log(f"Starting {len(pending)} file(s) — method: {method}", "dim")

        threading.Thread(target=self._worker,
                         args=(pending, out, method), daemon=True).start()

    def _worker(self, rows, out_dir, method):
        ok = fail = 0
        for i, row in enumerate(rows):
            self.after(0, row.set_status, "converting")
            success, msg = Engine.convert(row.path, out_dir, method,
                                          log_cb=self._log)
            if success:
                ok += 1
                self.after(0, row.set_status, "done")
                self._log(f"✔  {Path(row.path).name}", "ok")
            else:
                fail += 1
                self.after(0, row.set_status, "error")
                self._log(f"✘  {Path(row.path).name}:  {msg[:150]}", "err")

            self.after(0, self._tick, i + 1, len(rows))

        summary = f"{ok} converted successfully" + (f", {fail} failed" if fail else "") + "."
        self._log(summary, "ok" if fail == 0 else "warn")
        self.after(0, self._done, summary, ok, fail)

    def _tick(self, v, total):
        self._prog_bar["value"] = v
        self._status_lbl.config(text=f"Converting {v} / {total}…")
        self._update_count()

    def _done(self, summary, ok, fail):
        self._busy = False
        self.btn_convert.set_state(True)
        self.btn_convert.config(text="  Convert All  →", bg=ACCENT)
        self._status_lbl.config(text=summary,
                                 fg=OK if fail == 0 else WARN)
        self._update_count()


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def divider(parent, **kw):
    defaults = dict(bg=BORDER, height=1)
    defaults.update(kw)
    tk.Frame(parent, **defaults).pack(fill="x", pady=6)


# ══ Entry point ═══════════════════════════════════════════════════════════════

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()