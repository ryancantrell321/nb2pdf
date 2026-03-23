"""
NB2PDF - System dependency checker.

Checks for required Python packages, browsers, LaTeX, and Pandoc.
Returns structured results suitable for display in the UI status dashboard.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from config.constants import (
    BROWSER_NAMES, LATEX_EXECUTABLES, REQUIRED_PACKAGES
)
from utils.file_utils import _SUBPROCESS_FLAGS
from utils.logger import get_logger

logger = get_logger("system_checker")


class CheckStatus(Enum):
    """Status of a dependency check."""
    OK      = "ok"
    MISSING = "missing"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    """Result of a single dependency check."""
    name: str
    status: CheckStatus
    detail: str = ""
    fix_action: Optional[str] = None


@dataclass
class SystemCheckReport:
    """Aggregated system check results."""
    python_packages: List[CheckResult] = field(default_factory=list)
    browsers:        List[CheckResult] = field(default_factory=list)
    latex:           List[CheckResult] = field(default_factory=list)
    pandoc:          List[CheckResult] = field(default_factory=list)

    @property
    def browser_available(self) -> bool:
        return any(r.status == CheckStatus.OK for r in self.browsers)

    @property
    def latex_available(self) -> bool:
        return any(r.status == CheckStatus.OK for r in self.latex)

    @property
    def pandoc_available(self) -> bool:
        return any(r.status == CheckStatus.OK for r in self.pandoc)

    @property
    def nbconvert_available(self) -> bool:
        return any(
            r.name == "nbconvert" and r.status == CheckStatus.OK
            for r in self.python_packages
        )

    @property
    def latex_pipeline_ready(self) -> bool:
        """True only when BOTH LaTeX and Pandoc are present (both required)."""
        return self.latex_available and self.pandoc_available


class SystemChecker:
    """
    Runs system dependency checks.

    All checks are designed to be run in a background thread
    to avoid blocking the UI.
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run_all(self) -> SystemCheckReport:
        """Run all dependency checks and return a consolidated report."""
        report = SystemCheckReport()
        report.python_packages = self.check_python_packages()
        report.browsers        = self.check_browsers()
        report.latex           = self.check_latex()
        report.pandoc          = self.check_pandoc()
        return report

    def check_python_packages(self) -> List[CheckResult]:
        """Check that required Python packages are importable."""
        results: List[CheckResult] = []
        for pkg in REQUIRED_PACKAGES:
            version = self._get_package_version(pkg)
            if version:
                results.append(CheckResult(
                    name=pkg,
                    status=CheckStatus.OK,
                    detail=version,
                ))
            else:
                results.append(CheckResult(
                    name=pkg,
                    status=CheckStatus.MISSING,
                    detail="Not installed",
                    fix_action=f"pip install {pkg}",
                ))
        return results

    def check_browsers(self) -> List[CheckResult]:
        """Detect installed Chromium-compatible browsers."""
        results: List[CheckResult] = []
        browser_paths = self._find_browsers()

        if not browser_paths:
            results.append(CheckResult(
                name="Chromium browser",
                status=CheckStatus.MISSING,
                detail="No compatible browser found (Chrome, Edge, Brave)",
                fix_action="Install Google Chrome, Microsoft Edge, or Brave Browser",
            ))
        else:
            for name, path in browser_paths.items():
                results.append(CheckResult(
                    name=name,
                    status=CheckStatus.OK,
                    detail=path,
                ))

        return results

    def check_latex(self) -> List[CheckResult]:
        """Detect LaTeX installations."""
        results: List[CheckResult] = []
        for exe in LATEX_EXECUTABLES:
            path = shutil.which(exe)
            if path:
                version = self._get_latex_version(exe)
                results.append(CheckResult(
                    name=exe,
                    status=CheckStatus.OK,
                    detail=version or path,
                ))

        if not results:
            results.append(CheckResult(
                name="LaTeX",
                status=CheckStatus.MISSING,
                detail="No LaTeX distribution found (xelatex / pdflatex / lualatex)",
                fix_action="Install MiKTeX (Windows) or TeX Live",
            ))

        return results

    def check_pandoc(self) -> List[CheckResult]:
        """
        Detect Pandoc installation.

        Uses _find_pandoc() which searches shutil.which + all known Windows
        install locations, so it works even when the subprocess PATH differs
        from the user's interactive shell PATH.
        """
        pandoc_path = self._find_pandoc()
        if pandoc_path:
            version = self._get_pandoc_version(pandoc_path)
            return [CheckResult(
                name="Pandoc",
                status=CheckStatus.OK,
                detail=f"{version}  ({pandoc_path})" if version else pandoc_path,
            )]
        else:
            logger.warning(
                "Pandoc not found. Searched PATH and known Windows locations."
            )
            return [CheckResult(
                name="Pandoc",
                status=CheckStatus.MISSING,
                detail=(
                    "Required by the LaTeX pipeline to convert Markdown cells. "
                    "Without it, LaTeX conversion will fail."
                ),
                fix_action="https://pandoc.org/installing.html",
            )]

    def install_packages(self, packages: List[str]) -> subprocess.CompletedProcess:
        """Install Python packages via pip."""
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages
        logger.info(f"Installing packages: {packages}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                **_SUBPROCESS_FLAGS)
        if result.returncode == 0:
            logger.info("Package installation succeeded")
        else:
            logger.error(f"Package installation failed:\n{result.stderr}")
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_package_version(package: str) -> str:
        """Return version string, or empty string if not found."""
        try:
            import importlib.metadata as meta
            return meta.version(package)
        except Exception:
            pass
        try:
            mod = importlib.import_module(package)
            v = getattr(mod, "__version__", None)
            if v:
                return str(v)
        except Exception:
            pass
        return ""

    @staticmethod
    def _find_browsers() -> Dict[str, str]:
        """Return {browser_name: executable_path} for all found browsers."""
        import os
        found: Dict[str, str] = {}

        candidates: Dict[str, List[str]] = {
            "Google Chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ],
            "Microsoft Edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                "/usr/bin/microsoft-edge",
            ],
            "Brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                "/usr/bin/brave-browser",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            ],
            "Chromium": [
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
            ],
        }

        for name, paths in candidates.items():
            for p in paths:
                if os.path.isfile(p):
                    found[name] = p
                    break
            else:
                exe = shutil.which(name.lower().replace(" ", "-"))
                if exe:
                    found[name] = exe

        return found

    @staticmethod
    def _get_latex_version(exe: str) -> str:
        try:
            result = subprocess.run(
                [exe, "--version"],
                capture_output=True, text=True, timeout=5,
                **_SUBPROCESS_FLAGS,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            return first_line[:60]
        except Exception:
            return ""

    @staticmethod
    def _find_pandoc() -> Optional[str]:
        """
        Search for the pandoc executable using multiple strategies.

        Strategy 1: shutil.which() with the current process PATH.
        Strategy 2: Rebuild PATH from the Windows registry / environment
                    to include user-level entries that subprocess may miss.
        Strategy 3: Check every known hard-coded install location on Windows.
        """
        import os

        # Strategy 1 — standard PATH search
        found = shutil.which("pandoc")
        if found:
            logger.debug(f"Pandoc found via shutil.which: {found}")
            return found

        # Strategy 2 — on Windows, widen the PATH search manually
        if sys.platform == "win32":
            # Collect additional directories that pandoc installers commonly use
            extra_dirs: List[str] = []

            # LOCALAPPDATA\Pandoc  (default MSI installer location)
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                extra_dirs.append(os.path.join(local_app, "Pandoc"))

            # Chocolatey
            choco = os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey")
            extra_dirs.append(os.path.join(choco, "bin"))

            # Scoop
            scoop_home = os.path.join(os.path.expanduser("~"), "scoop", "shims")
            extra_dirs.append(scoop_home)

            # Winget default
            extra_dirs.append(r"C:\Program Files\Pandoc")
            extra_dirs.append(r"C:\Program Files (x86)\Pandoc")

            # Strategy 3 — try every extra dir
            for d in extra_dirs:
                candidate = os.path.join(d, "pandoc.exe")
                if os.path.isfile(candidate):
                    logger.debug(f"Pandoc found at hard-coded path: {candidate}")
                    return candidate

            # Strategy 2b — rebuild PATH string and search again
            current_path = os.environ.get("PATH", "")
            augmented_path = os.pathsep.join(
                [current_path] + [d for d in extra_dirs if os.path.isdir(d)]
            )
            found = shutil.which("pandoc", path=augmented_path)
            if found:
                logger.debug(f"Pandoc found via augmented PATH: {found}")
                return found

        logger.debug("Pandoc not found after exhaustive search")
        return None

    @staticmethod
    def _get_pandoc_version(pandoc_path: str) -> str:
        """Run pandoc --version using the known absolute path."""
        try:
            result = subprocess.run(
                [pandoc_path, "--version"],
                capture_output=True, text=True, timeout=5,
                **_SUBPROCESS_FLAGS,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            return first_line[:60]
        except Exception:
            return ""
