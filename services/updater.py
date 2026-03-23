"""
NB2PDF - Software update service.

Checks GitHub releases for new versions, downloads updates safely,
and launches an external updater process so the running EXE is
never overwritten in place.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional
from packaging.version import Version, InvalidVersion

from config.constants import APP_NAME, APP_VERSION, UPDATE_REPO_URL
from utils.file_utils import _SUBPROCESS_FLAGS
from utils.logger import get_logger

logger = get_logger("updater")

_GITHUB_RELEASES_API = (
    "https://api.github.com/repos/{owner}/{repo}/releases/latest"
)
_REQUEST_TIMEOUT = 10  # seconds


@dataclass
class UpdateInfo:
    """Information about an available update."""
    current_version: str
    latest_version: str
    download_url: str
    changelog: str
    is_newer: bool


class UpdateChecker:
    """
    Checks for and applies application updates.

    This class is designed to be called from a background thread
    to avoid blocking the UI.
    """

    def __init__(self, repo_url: str = UPDATE_REPO_URL) -> None:
        self._repo_url = repo_url
        self._current_version = APP_VERSION

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        Query the repository for the latest release.

        Returns UpdateInfo if successful, None on failure.
        """
        if "<INSERT" in self._repo_url:
            logger.warning("UPDATE_REPO_URL has not been configured. Skipping update check.")
            return None

        api_url = self._build_api_url()
        if not api_url:
            return None

        try:
            data = self._fetch_json(api_url)
            return self._parse_release(data)
        except urllib.error.URLError as exc:
            logger.warning(f"Network error during update check: {exc}")
        except Exception as exc:
            logger.error(f"Unexpected error during update check: {exc}", exc_info=True)
        return None

    def download_update(self, info: UpdateInfo) -> Optional[str]:
        """
        Download the update binary to a temp directory.

        Returns the path to the downloaded file, or None on failure.
        """
        try:
            tmp_dir = tempfile.mkdtemp(prefix=f"{APP_NAME}_update_")
            filename = os.path.basename(info.download_url.split("?")[0])
            dest = os.path.join(tmp_dir, filename)

            logger.info(f"Downloading update from {info.download_url}")
            urllib.request.urlretrieve(info.download_url, dest)
            logger.info(f"Update downloaded to {dest}")
            return dest
        except Exception as exc:
            logger.error(f"Update download failed: {exc}", exc_info=True)
            return None

    def launch_updater(self, update_path: str) -> bool:
        """
        Launch an external updater process that replaces the EXE after exit.

        On Windows, writes a tiny batch script that waits, copies, and launches.
        On other platforms, writes a shell script.

        Returns True if the updater was started successfully.
        """
        try:
            if sys.platform == "win32":
                return self._launch_windows_updater(update_path)
            return self._launch_posix_updater(update_path)
        except Exception as exc:
            logger.error(f"Failed to launch updater: {exc}", exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_api_url(self) -> Optional[str]:
        """Convert a GitHub repo URL to the releases API URL."""
        try:
            # Support https://github.com/owner/repo or owner/repo
            url = self._repo_url.rstrip("/")
            if url.startswith("https://github.com/"):
                url = url[len("https://github.com/"):]
            parts = url.split("/")
            if len(parts) < 2:
                logger.error("UPDATE_REPO_URL is not a valid GitHub repo path.")
                return None
            owner, repo = parts[0], parts[1]
            return _GITHUB_RELEASES_API.format(owner=owner, repo=repo)
        except Exception as exc:
            logger.error(f"Could not parse repo URL: {exc}")
            return None

    def _fetch_json(self, url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _parse_release(self, data: dict) -> UpdateInfo:
        tag = data.get("tag_name", "").lstrip("v")
        changelog = data.get("body", "No changelog available.")

        # Find a Windows EXE asset
        assets = data.get("assets", [])
        download_url = ""
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".exe") or name.endswith(".zip") or name.endswith(".rar"):
                download_url = asset.get("browser_download_url", "")
                break

        is_newer = self._is_newer_version(tag)
        return UpdateInfo(
            current_version=self._current_version,
            latest_version=tag,
            download_url=download_url,
            changelog=changelog,
            is_newer=is_newer,
        )

    def _is_newer_version(self, latest: str) -> bool:
        try:
            return Version(latest) > Version(self._current_version)
        except InvalidVersion:
            return False

    @staticmethod
    def _launch_windows_updater(update_path: str) -> bool:
        current_exe = sys.executable
        script = (
            "@echo off\n"
            "timeout /t 2 /nobreak > NUL\n"
            f'copy /Y "{update_path}" "{current_exe}"\n'
            f'start "" "{current_exe}"\n'
        )
        script_path = update_path + "_updater.bat"
        with open(script_path, "w") as fh:
            fh.write(script)
        subprocess.Popen(
            ["cmd.exe", "/C", script_path],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        return True

    @staticmethod
    def _launch_posix_updater(update_path: str) -> bool:
        current_exe = sys.executable
        script = (
            "#!/bin/sh\n"
            "sleep 2\n"
            f'cp -f "{update_path}" "{current_exe}"\n'
            f'chmod +x "{current_exe}"\n'
            f'"{current_exe}" &\n'
        )
        script_path = update_path + "_updater.sh"
        with open(script_path, "w") as fh:
            fh.write(script)
        os.chmod(script_path, 0o755)
        subprocess.Popen(["/bin/sh", script_path], close_fds=True)
        return True
