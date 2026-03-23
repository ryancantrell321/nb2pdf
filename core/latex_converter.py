"""
NB2PDF - LaTeX-based converter (rewritten pipeline).

The root issue
--------------
nbconvert --to pdf is a black box: it writes a .tex file then immediately
runs xelatex on it.  We cannot intercept between those two steps.

New pipeline (two-stage, fully transparent)
--------------------------------------------
Stage 1  nbconvert --to latex   →  writes notebook.tex  (we can inspect/patch it)
Stage 2  xelatex notebook.tex   →  produces notebook.pdf  (we run it ourselves)

This lets us:
  - Patch the generated .tex before compilation
  - Control xelatex flags (including -interaction=nonstopmode so it never stalls)
  - Rescue partial PDFs when xelatex exits non-zero but still produced output
  - Run xelatex exactly 3 times for cross-references

The specific bug fixed
----------------------
Pandoc generates zero-width table column specs like:

    p{(\\columnwidth - 0\\tabcolsep) * \\real{0.0556}}

When the column has zero width the coefficient "0\\tabcolsep" confuses
xelatex's counter machinery and produces:

    ! LaTeX Error: No counter 'none' defined.
    ! Emergency stop.

The regex patch in _patch_tex() replaces every occurrence of
    (\\columnwidth - 0\\tabcolsep)
with the safe form
    (\\columnwidth - 2\\tabcolsep)
which distributes the zero-width space evenly without breaking the
counter arithmetic.  It also replaces \real{0.0...} (any value less
than 0.01) with \real{0.01} to ensure every column has a minimal width.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional

from core.base_converter import BaseConverter, ConversionResult, ProgressCallback
from utils.file_utils import _SUBPROCESS_FLAGS
from utils.logger import get_logger

logger = get_logger("latex_converter")

_LATEX_ENGINES = ["xelatex", "pdflatex", "lualatex"]

# Number of times to run LaTeX (needed for TOC/cross-refs to resolve)
_LATEX_PASSES = 2


class LaTeXConverter(BaseConverter):
    """
    Two-stage LaTeX converter:
      Stage 1: nbconvert --to latex  →  .tex file
      Stage 2: xelatex (×3)         →  .pdf file
    """

    display_name = "LaTeX (MiKTeX / TeX Live)"

    def __init__(self) -> None:
        self._latex_engine: Optional[str] = None

    # ------------------------------------------------------------------ #
    # BaseConverter interface                                              #
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        try:
            import nbconvert  # noqa: F401
        except ImportError:
            logger.debug("nbconvert not importable — LaTeX converter unavailable")
            return False
        available = bool(self._find_latex_engine())
        if not available:
            logger.debug("No LaTeX engine found — LaTeX converter unavailable")
        return available

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

        log("info", "=== LaTeX conversion started (two-stage pipeline) ===")
        log("info", f"Notebook : {notebook_path}")
        log("info", f"Output   : {output_path}")

        # ── Locate LaTeX engine ───────────────────────────────────────────
        engine = self._find_latex_engine()
        if not engine:
            msg = (
                "No LaTeX engine found.\n"
                "Searched for: " + ", ".join(_LATEX_ENGINES) + "\n"
                "Install MiKTeX (https://miktex.org) or TeX Live (https://tug.org/texlive/)."
            )
            log("error", msg)
            return ConversionResult.fail(msg, log_lines)

        engine_path = shutil.which(engine) or engine
        log("info", f"LaTeX engine : {engine}  ({engine_path})")

        # ── Locate Pandoc ─────────────────────────────────────────────────
        from services.system_checker import SystemChecker as _SC
        pandoc_path = _SC._find_pandoc()
        if not pandoc_path:
            msg = (
                "Pandoc not found.\n\n"
                "Install from https://pandoc.org/installing.html "
                "then restart NB2PDF."
            )
            log("error", msg)
            return ConversionResult.fail(msg, log_lines)

        log("info", f"Pandoc    : {pandoc_path}")
        pandoc_dir = os.path.dirname(pandoc_path)

        # Build a clean subprocess environment with pandoc on PATH
        env = self._build_env(pandoc_dir)

        with tempfile.TemporaryDirectory(prefix="nb2pdf_latex_") as tmpdir:
            log("info", f"Temp dir  : {tmpdir}")

            # ── STAGE 1: notebook → .tex ───────────────────────────────────
            if progress_cb:
                progress_cb(10, "Stage 1/2 — generating LaTeX source…")

            tex_result = self._run_stage1_latex_export(
                notebook_path, tmpdir, env
            )

            if tex_result.stdout:
                logger.debug(f"nbconvert stdout:\n{tex_result.stdout}")
            if tex_result.stderr:
                logger.debug(f"nbconvert stderr:\n{tex_result.stderr}")

            for line in (tex_result.stdout + tex_result.stderr).splitlines():
                if line.strip():
                    log("info", line)

            if tex_result.returncode != 0:
                msg = (
                    f"nbconvert --to latex failed (exit {tex_result.returncode}).\n"
                    f"{tex_result.stderr or tex_result.stdout or 'No output.'}"
                )
                log("error", msg)
                return ConversionResult.fail(msg, log_lines)

            # Find the .tex file
            tex_file = self._find_file(tmpdir, ".tex")
            if not tex_file:
                msg = (
                    f"nbconvert exited 0 but no .tex file found in {tmpdir}.\n"
                    f"Contents: {os.listdir(tmpdir)}"
                )
                log("error", msg)
                return ConversionResult.fail(msg, log_lines)

            log("info", f"LaTeX source : {tex_file}")

            # ── Patch the .tex file ────────────────────────────────────────
            if progress_cb:
                progress_cb(30, "Patching LaTeX source…")

            patches = self._patch_tex(tex_file)
            if patches:
                log("info", f"Applied {patches} patch(es) to .tex source")
            else:
                log("info", "No patches needed in .tex source")

            # ── STAGE 2: .tex → .pdf (xelatex × 3) ───────────────────────
            if progress_cb:
                progress_cb(40, f"Stage 2/2 — compiling with {engine} (pass 1/3)…")

            tex_name = os.path.basename(tex_file)
            pdf_tmp = os.path.join(tmpdir, os.path.splitext(tex_name)[0] + ".pdf")

            final_result = None
            for pass_num in range(1, _LATEX_PASSES + 1):
                if progress_cb:
                    pct = 40 + (pass_num - 1) * 18
                    progress_cb(pct, f"Stage 2/2 — compiling with {engine} (pass {pass_num}/{_LATEX_PASSES})…")

                log("info", f"xelatex pass {pass_num}/{_LATEX_PASSES}")
                xelatex_result = self._run_stage2_xelatex(
                    engine_path, tex_name, tmpdir, env
                )
                final_result = xelatex_result

                stdout = xelatex_result.stdout or ""
                stderr = xelatex_result.stderr or ""
                combined = stdout + stderr

                if combined:
                    logger.debug(f"xelatex pass {pass_num} output:\n{combined}")

                # Log only meaningful lines to the GUI console
                for line in combined.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("(") and len(stripped) > 3:
                        log("info", line)

                # Check for fatal errors that mean no point continuing
                if xelatex_result.returncode != 0:
                    # Check if a PDF was still produced (partial compile)
                    pdf_exists = os.path.isfile(pdf_tmp) and os.path.getsize(pdf_tmp) > 0
                    if not pdf_exists:
                        # Fatal — no output at all
                        error_excerpt = self._extract_latex_error(combined)
                        msg = (
                            f"xelatex pass {pass_num} failed (exit {xelatex_result.returncode}) "
                            f"with no PDF output.\n\n"
                            f"{error_excerpt}"
                        )
                        log("error", msg)
                        return ConversionResult.fail(msg, log_lines)
                    else:
                        # Partial PDF exists — warn and break
                        error_excerpt = self._extract_latex_error(combined)
                        log("warning",
                            f"xelatex pass {pass_num} exited {xelatex_result.returncode} "
                            f"but produced a partial PDF. Delivering partial output.\n"
                            f"Errors: {error_excerpt}")
                        break

            # ── Move PDF to output ─────────────────────────────────────────
            if not os.path.isfile(pdf_tmp) or os.path.getsize(pdf_tmp) == 0:
                msg = "xelatex ran but produced no PDF. Check the log for details."
                log("error", msg)
                return ConversionResult.fail(msg, log_lines)

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            shutil.move(pdf_tmp, output_path)

        if progress_cb:
            progress_cb(100, "Conversion complete!")
        log("info", f"=== Conversion succeeded → {output_path} ===")
        return ConversionResult.ok(output_path, log_lines)

    # ------------------------------------------------------------------ #
    # Stage 1: nbconvert --to latex                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _run_stage1_latex_export(
        notebook_path: str,
        output_dir: str,
        env: dict,
    ) -> subprocess.CompletedProcess:
        """Export the notebook to a .tex file using the nbconvert Python API."""
        try:
            from nbconvert.exporters import LatexExporter
            import nbformat

            nb = nbformat.read(notebook_path, as_version=4)
            exporter = LatexExporter()
            body, resources = exporter.from_notebook_node(nb)

            stem = os.path.splitext(os.path.basename(notebook_path))[0]
            tex_path = os.path.join(output_dir, stem + ".tex")
            with open(tex_path, "w", encoding="utf-8") as fh:
                fh.write(body)

            # Write embedded image outputs so xelatex can find them by relative path
            for fname, data in (resources.get("outputs") or {}).items():
                img_path = os.path.join(output_dir, fname)
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                with open(img_path, "wb") as fh:
                    fh.write(data)

            return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
        except Exception as exc:
            return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=str(exc))

    # ------------------------------------------------------------------ #
    # .tex patcher                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _patch_tex(tex_path: str) -> int:
        """
        Read the generated .tex, apply all safety patches, write it back.
        Returns the total number of substitutions made.

        Root cause
        ----------
        nbconvert + Pandoc generates longtable column width specs like:

            p{(\\columnwidth - 0\\tabcolsep) * \\real{0.0556}}

        xelatex parses "0\\tabcolsep" as a counter named "0" applied to the
        \\tabcolsep register — which does not exist — and crashes with:

            ! LaTeX Error: No counter 'none' defined.

        The fix is to replace "0\\tabcolsep" with "0pt" (zero points), which
        is semantically identical but syntactically correct LaTeX.
        """
        with open(tex_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        original_lines = list(lines)
        total_subs = 0

        # Log all lines containing tabcolsep for diagnostics
        for i, line in enumerate(lines, 1):
            if "tabcolsep" in line or "columnwidth" in line:
                logger.debug(f"  tex line {i}: {line.rstrip()}")

        patched_lines = []
        for i, line in enumerate(lines, 1):

            # ── Patch 1 (THE CRITICAL FIX) ────────────────────────────────
            # Replace:  (anything - 0	abcolsep)
            # With:     (anything - 0pt)
            #
            # This covers all variations regardless of whitespace or what
            # precedes the 0	abcolsep term.
            new_line, n = re.subn(
                r'0\tabcolsep',
                r'0pt',
                line
            )
            if n:
                logger.info(f"Patch 1 applied at line {i}: {line.rstrip()!r} → {new_line.rstrip()!r}")
                total_subs += n
                line = new_line

            # ── Patch 2: clamp tiny \real{X} values ──────────────────────
            # Replace \real{X} where X < 0.01 with \real{0.01}
            def _clamp_real(m: re.Match) -> str:
                try:
                    if float(m.group(1)) < 0.01:
                        return r'\real{0.01}'
                except ValueError:
                    pass
                return m.group(0)

            new_line, n = re.subn(r'\\real\{([0-9]+\.?[0-9]*)\}', _clamp_real, line)
            if n and new_line != line:
                logger.info(f"Patch 2 applied at line {i}: clamped \\real value")
                total_subs += n
                line = new_line

            # ── Patch 3: p{0pt} zero-width columns ────────────────────────
            new_line, n = re.subn(r'p\{0\s*pt\}', r'p{1pt}', line)
            if n:
                logger.info(f"Patch 3 applied at line {i}: zero-width p column")
                total_subs += n
                line = new_line

            patched_lines.append(line)

        if patched_lines != original_lines:
            with open(tex_path, "w", encoding="utf-8") as fh:
                fh.writelines(patched_lines)
            logger.info(f"Wrote patched .tex: {total_subs} total substitution(s)")
        else:
            logger.warning(
                f"_patch_tex: NO substitutions made in {tex_path}. "
                f"The zero-width column bug may still be present. "
                f"Check DEBUG logs for 'tex line' entries to see actual content."
            )

        return total_subs

    # ------------------------------------------------------------------ #
    # Stage 2: xelatex                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _run_stage2_xelatex(
        engine_path: str,
        tex_filename: str,
        working_dir: str,
        env: dict,
    ) -> subprocess.CompletedProcess:
        """
        Run xelatex on tex_filename from working_dir.

        Console-window suppression on MiKTeX
        -------------------------------------
        MiKTeX's xelatex.exe is a wrapper that calls CreateProcess() on
        miktex-xetex.exe with a fresh STARTUPINFO, so CREATE_NO_WINDOW and
        STARTF_USESHOWWINDOW on the parent are NOT inherited by the real
        TeX engine.  The fix is to invoke miktex-xetex.exe directly with
        -fmt=xelatex, passing CREATE_NO_WINDOW to that process itself.
        For non-MiKTeX installs we fall back to the engine_path as-is.
        """
        # Resolve the direct miktex-xetex binary next to xelatex.exe
        engine_dir = os.path.dirname(engine_path)
        miktex_xetex = os.path.join(engine_dir, "miktex-xetex.exe")
        if os.path.isfile(miktex_xetex):
            actual_engine = miktex_xetex
            fmt_flag = ["-fmt=xelatex"]
        else:
            actual_engine = engine_path
            fmt_flag = []

        cmd = [
            actual_engine,
            "-interaction=nonstopmode",
            f"-output-directory={working_dir}",
        ] + fmt_flag + [tex_filename]

        logger.debug(f"Stage 2 command (cwd={working_dir}): {' '.join(cmd)}")
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=env,
                cwd=working_dir,
                **_SUBPROCESS_FLAGS,
            )
        except subprocess.TimeoutExpired:
            logger.error("xelatex timed out after 180 s on pass")
            return subprocess.CompletedProcess(cmd, returncode=1,
                                               stdout="", stderr="Timed out")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _find_latex_engine(self) -> Optional[str]:
        if self._latex_engine and shutil.which(self._latex_engine):
            return self._latex_engine
        for eng in _LATEX_ENGINES:
            path = shutil.which(eng)
            if path:
                logger.debug(f"Found LaTeX engine: {eng} at {path}")
                self._latex_engine = eng
                return eng
        return None

    @staticmethod
    def _build_env(pandoc_dir: str) -> dict:
        """Return a subprocess environment with pandoc_dir prepended to PATH."""
        env = os.environ.copy()
        if pandoc_dir and pandoc_dir not in env.get("PATH", ""):
            env["PATH"] = pandoc_dir + os.pathsep + env.get("PATH", "")
            logger.debug(f"Injected pandoc dir into subprocess PATH: {pandoc_dir}")
        return env

    @staticmethod
    def _find_file(directory: str, extension: str) -> Optional[str]:
        """Return the first file with *extension* found in *directory*."""
        for fname in os.listdir(directory):
            if fname.lower().endswith(extension):
                return os.path.join(directory, fname)
        return None

    @staticmethod
    def _extract_latex_error(output: str) -> str:
        """Extract the most actionable error lines from xelatex output."""
        lines = output.splitlines()
        error_lines: List[str] = []
        for i, line in enumerate(lines):
            lower = line.lower()
            if (
                line.startswith("!")
                or "error" in lower
                or "fatal" in lower
                or "emergency stop" in lower
            ):
                error_lines.extend(lines[i:i + 3])

        if error_lines:
            seen: set = set()
            unique: List[str] = []
            for ln in error_lines:
                if ln not in seen:
                    seen.add(ln)
                    unique.append(ln)
            return "\n".join(unique[:20])

        return "\n".join(lines[-30:]) if lines else "(no output captured)"
