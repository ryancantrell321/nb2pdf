"""
NB2PDF - Application settings with JSON persistence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

from config.constants import (
    APP_NAME, SETTINGS_FILENAME, METHOD_BROWSER
)
from utils.paths import get_user_config_dir


@dataclass
class Settings:
    """Persisted application settings."""

    # Paths
    last_input_dir: str = ""
    last_output_dir: str = ""

    # Conversion
    preferred_method: str = METHOD_BROWSER
    open_pdf_after_conversion: bool = True

    # Updates
    check_updates_on_startup: bool = True

    # UI
    log_level: str = "INFO"
    theme: str = "dark"

    # Internal
    _config_path: str = field(default="", init=False, repr=False)

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from disk, returning defaults if not found."""
        config_dir = get_user_config_dir(APP_NAME)
        config_path = os.path.join(config_dir, SETTINGS_FILENAME)

        instance = cls()
        instance._config_path = config_path

        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                for key, value in data.items():
                    if hasattr(instance, key) and not key.startswith("_"):
                        setattr(instance, key, value)
            except (json.JSONDecodeError, OSError):
                pass  # Fall back to defaults silently

        return instance

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def save(self) -> None:
        """Persist settings to disk."""
        if not self._config_path:
            config_dir = get_user_config_dir(APP_NAME)
            self._config_path = os.path.join(config_dir, SETTINGS_FILENAME)

        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

        data = {
            k: v for k, v in asdict(self).items()
            if not k.startswith("_")
        }
        with open(self._config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
