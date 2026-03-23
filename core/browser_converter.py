"""
NB2PDF - Browser-based converter.

Pipeline: .ipynb → HTML (nbconvert Python API) → PDF (headless Chromium).

Design notes
------------
* nbconvert is called via its Python API (not subprocess) — works in frozen
  PyApp builds where sys.executable is the bootstrapper EXE.
* The browser is launched WITHOUT CREATE_NO_WINDOW / STARTUPINFO flags.
  Chromium-based browsers are GUI subsystem processes; passing console-
  suppression flags to them blocks their internal IPC/GPU renderer child,
  causing a silent exit-0 with no PDF written.
* The HTML file and the output PDF are both written to a short, space-free
  temp path (e.g. C:\\Users\\x\\AppData\\Local\\Temp\\nb2pdf_XXXXXX\\nb.html)
  because Edge/Chrome silently ignore --print-to-pdf when the path contains
  spaces, even with percent-encoding.
* --headless=new is tried first (Chrome 112+ / Edge 109+); falls back to
  legacy --headless on non-zero exit with no PDF.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Optional

from core.base_converter import BaseConverter, ConversionResult, ProgressCallback
from utils.logger import get_logger

logger = get_logger("browser_converter")

_WINDOWS_BROWSER_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
]

_MACOS_BROWSER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

_PATH_CANDIDATES = [
    "google-chrome", "google-chrome-stable",
    "msedge", "microsoft-edge",
    "brave-browser", "chromium-browser", "chromium",
]

# Browser flags common to both headless modes
_BROWSER_FLAGS = [
    "--disable-gpu",
    "--no-sandbox",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
    "--print-to-pdf-no-header",
]


class BrowserConverter(BaseConverter):
    """Converts notebooks to PDF via nbconvert (HTML) + headless Chromium."""

    display_name = "Browser (Chrome / Edge / Brave)"

    def __init__(self) -> None:
        self._browser_path: Optional[str] = None

    # ------------------------------------------------------------------ #
    # BaseConverter interface                                              #
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        try:
            import nbconvert  # noqa: F401
        except ImportError:
            return False
        return bool(self._find_browser())

    def convert(
        self,
        notebook_path: str,
        output_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> ConversionResult:

        log_lines: list = []

        def log(level: str, msg: str) -> None:
            getattr(logger, level)(msg)
            log_lines.append(f"[{level.upper()}] {msg}")

        log("info", "=== Browser conversion started ===")
        log("info", f"Notebook : {notebook_path}")
        log("info", f"Output   : {output_path}")

        browser = self._find_browser()
        if not browser:
            return ConversionResult.fail(
                "No compatible browser found.\n"
                "Install Google Chrome, Microsoft Edge, or Brave Browser.",
                log_lines,
            )
        log("info", f"Browser  : {browser}")

        # Use a short, space-free temp directory.
        # tempfile.mkdtemp() on Windows always returns a path under
        # %LOCALAPPDATA%\Temp which is guaranteed to be space-free on
        # standard Windows installs.  We rename the HTML to "nb.html" and
        # the PDF target to "out.pdf" so neither filename ever has spaces.
        tmpdir = tempfile.mkdtemp(prefix="nb2pdf_")
        try:
            html_path = os.path.join(tmpdir, "nb.html")
            pdf_tmp   = os.path.join(tmpdir, "out.pdf")

            log("info", f"Temp dir : {tmpdir}")

            # ── Step 1: notebook → HTML ───────────────────────────────────
            if progress_cb:
                progress_cb(10, "Converting notebook to HTML…")
            log("info", "Step 1/2 — nbconvert: notebook → HTML")

            err = self._nbconvert_to_html(notebook_path, html_path)
            if err:
                log("error", err)
                return ConversionResult.fail(err, log_lines)

            log("info", f"HTML written: {html_path}  ({os.path.getsize(html_path):,} bytes)")

            # ── Step 2: HTML → PDF ────────────────────────────────────────
            if progress_cb:
                progress_cb(55, "Rendering PDF with headless browser…")
            log("info", "Step 2/2 — headless browser: HTML → PDF")

            err = self._browser_print(browser, html_path, pdf_tmp, log)
            if err:
                log("error", err)
                return ConversionResult.fail(err, log_lines)

            # ── Move to final destination ─────────────────────────────────
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            shutil.move(pdf_tmp, output_path)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if progress_cb:
            progress_cb(100, "Conversion complete!")
        log("info", f"=== Conversion succeeded → {output_path} ===")
        return ConversionResult.ok(output_path, log_lines)

    # ------------------------------------------------------------------ #
    # Step 1: nbconvert Python API                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _nbconvert_to_html(notebook_path: str, html_path: str) -> Optional[str]:
        """
        Convert *notebook_path* to a self-contained HTML file at *html_path*.
        Returns an error string on failure, None on success.
        """
        try:
            import nbformat
            from nbconvert.exporters import HTMLExporter

            nb = nbformat.read(notebook_path, as_version=4)
            body, _ = HTMLExporter().from_notebook_node(nb)
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return None
        except Exception:
            detail = traceback.format_exc()
            logger.error(f"HTMLExporter failed:\n{detail}")
            return f"nbconvert (HTML) failed:\n{detail}"

    # ------------------------------------------------------------------ #
    # Step 2: headless browser                                             #
    # ------------------------------------------------------------------ #

    def _browser_print(
        self,
        browser: str,
        html_path: str,
        pdf_path: str,
        log,
    ) -> Optional[str]:
        """
        Render *html_path* to *pdf_path* using a headless browser.
        Returns an error string on failure, None on success.

        IMPORTANT: Do NOT pass CREATE_NO_WINDOW or any STARTUPINFO to the
        browser process.  Chromium browsers are GUI subsystem applications;
        console-suppression flags prevent their renderer/GPU child processes
        from initialising, causing a silent exit-0 with no PDF produced.
        """
        # file:// URL — html_path is already space-free (we named it nb.html)
        html_url = "file:///" + html_path.replace("\\", "/")

        def _run(headless_flag: str) -> subprocess.CompletedProcess:
            cmd = [browser, headless_flag] + _BROWSER_FLAGS + [
                f"--print-to-pdf={pdf_path}",
                html_url,
            ]
            log("info", f"Browser cmd: {' '.join(cmd)}")
            # No _SUBPROCESS_FLAGS here — see docstring above.
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                cwd=os.path.dirname(pdf_path),
            )

        result = _run("--headless=new")
        pdf_ok = os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0

        if result.stdout.strip():
            log("info", f"Browser stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            log("info", f"Browser stderr: {result.stderr.strip()}")

        if not pdf_ok and result.returncode != 0:
            log("info", "--headless=new failed; retrying with legacy --headless")
            result = _run("--headless")
            pdf_ok = os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0
            if result.stdout.strip():
                log("info", f"Browser stdout (retry): {result.stdout.strip()}")
            if result.stderr.strip():
                log("info", f"Browser stderr (retry): {result.stderr.strip()}")

        if not pdf_ok:
            return (
                f"Headless browser exited {result.returncode} and produced no PDF.\n"
                f"stdout: {result.stdout or '(empty)'}\n"
                f"stderr: {result.stderr or '(empty)'}"
            )
        return None

    # ------------------------------------------------------------------ #
    # Browser discovery                                                    #
    # ------------------------------------------------------------------ #

    def _find_browser(self) -> Optional[str]:
        if self._browser_path and os.path.isfile(self._browser_path):
            return self._browser_path

        candidates = _WINDOWS_BROWSER_PATHS if sys.platform == "win32" else _MACOS_BROWSER_PATHS
        for path in candidates:
            if os.path.isfile(path):
                self._browser_path = path
                return path

        for exe in _PATH_CANDIDATES:
            found = shutil.which(exe)
            if found:
                self._browser_path = found
                return found

        return None
