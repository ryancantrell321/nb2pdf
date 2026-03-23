"""
NB2PDF - Converter factory.

Selects and instantiates the appropriate converter based on the
user's preferred method and available dependencies.
"""

from __future__ import annotations

from typing import Dict, Type

from config.constants import METHOD_BROWSER, METHOD_LATEX
from core.base_converter import BaseConverter
from core.browser_converter import BrowserConverter
from core.latex_converter import LaTeXConverter
from utils.logger import get_logger

logger = get_logger("converter_factory")

# Registry: method key → converter class
_REGISTRY: Dict[str, Type[BaseConverter]] = {
    METHOD_BROWSER: BrowserConverter,
    METHOD_LATEX: LaTeXConverter,
}


class ConverterFactory:
    """
    Factory for creating converter instances.

    Usage
    -----
    converter = ConverterFactory.create(method="browser")
    result = converter.convert(notebook_path, output_path)
    """

    @staticmethod
    def create(method: str) -> BaseConverter:
        """
        Return a converter instance for the given *method* key.

        Falls back to BrowserConverter if the key is unknown.
        """
        cls = _REGISTRY.get(method)
        if cls is None:
            logger.warning(
                f"Unknown conversion method '{method}'. Falling back to browser."
            )
            cls = BrowserConverter
        return cls()

    @staticmethod
    def available_methods() -> Dict[str, str]:
        """Return {method_key: display_name} for all registered converters."""
        return {
            key: cls().display_name
            for key, cls in _REGISTRY.items()
        }
