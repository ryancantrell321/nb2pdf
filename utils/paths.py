"""
NB2PDF - Path utilities.
"""

from __future__ import annotations

import os
import sys
import tempfile


def get_app_root() -> str:
    """Return the application root directory (directory containing main.py)."""
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_resource_path(relative_path: str) -> str:
    """Return the absolute path to a resource relative to the app root."""
    return os.path.join(get_app_root(), relative_path)


def get_user_config_dir(app_name: str) -> str:
    """
    Return the platform-appropriate user config directory.

    Windows : %APPDATA%/<app_name>
    macOS   : ~/Library/Application Support/<app_name>
    Linux   : ~/.config/<app_name>
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config")

    path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def get_logs_dir(app_name: str) -> str:
    """Return directory for log files."""
    logs_dir = os.path.join(get_user_config_dir(app_name), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def get_temp_dir(app_name: str) -> str:
    """Return a dedicated temp directory for conversion artefacts."""
    tmp = os.path.join(tempfile.gettempdir(), app_name)
    os.makedirs(tmp, exist_ok=True)
    return tmp
