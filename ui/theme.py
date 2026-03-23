"""
NB2PDF - UI theme definitions.

Provides a dark and light theme with consistent color tokens,
font specifications, and spacing constants used across all UI components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Theme:
    """Complete UI theme specification."""

    # Background layers
    bg_primary: str      # Main window background
    bg_secondary: str    # Card / panel background
    bg_tertiary: str     # Input fields, sunken areas
    bg_hover: str        # Hover state

    # Accent
    accent: str          # Primary action color
    accent_hover: str    # Hover state of accent
    accent_text: str     # Text on accent backgrounds

    # Text
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_inverse: str    # Text on dark backgrounds when in light mode

    # Status
    color_ok: str
    color_warn: str
    color_error: str
    color_info: str

    # Borders
    border: str
    border_focus: str

    # Fonts
    font_family: str
    font_size_sm: int
    font_size_md: int
    font_size_lg: int
    font_size_xl: int

    # Spacing
    pad_xs: int
    pad_sm: int
    pad_md: int
    pad_lg: int
    corner_radius: int


DARK_THEME = Theme(
    bg_primary="#0f1117",
    bg_secondary="#1a1d27",
    bg_tertiary="#252836",
    bg_hover="#2e3145",

    accent="#5b6ef5",
    accent_hover="#7485f7",
    accent_text="#ffffff",

    text_primary="#e8eaf0",
    text_secondary="#9196a8",
    text_disabled="#555b6e",
    text_inverse="#0f1117",

    color_ok="#3dd68c",
    color_warn="#f0b429",
    color_error="#f56565",
    color_info="#63b3ed",

    border="#2e3145",
    border_focus="#5b6ef5",

    font_family="Segoe UI",
    font_size_sm=9,
    font_size_md=10,
    font_size_lg=12,
    font_size_xl=16,

    pad_xs=4,
    pad_sm=8,
    pad_md=14,
    pad_lg=22,
    corner_radius=8,
)

LIGHT_THEME = Theme(
    bg_primary="#f4f5f9",
    bg_secondary="#ffffff",
    bg_tertiary="#eceef4",
    bg_hover="#dde0ed",

    accent="#4c5de0",
    accent_hover="#3a4bc8",
    accent_text="#ffffff",

    text_primary="#1a1d2e",
    text_secondary="#5a5f75",
    text_disabled="#b0b5c8",
    text_inverse="#ffffff",

    color_ok="#25a96e",
    color_warn="#d4900e",
    color_error="#d94040",
    color_info="#2b7fc4",

    border="#d8dae8",
    border_focus="#4c5de0",

    font_family="Segoe UI",
    font_size_sm=9,
    font_size_md=10,
    font_size_lg=12,
    font_size_xl=16,

    pad_xs=4,
    pad_sm=8,
    pad_md=14,
    pad_lg=22,
    corner_radius=8,
)

THEMES: Dict[str, Theme] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def get_theme(name: str) -> Theme:
    """Return the Theme for *name*, defaulting to dark."""
    return THEMES.get(name, DARK_THEME)
