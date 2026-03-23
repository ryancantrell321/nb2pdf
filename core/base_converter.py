"""
NB2PDF - Core conversion abstractions.

Defines the ConversionResult dataclass and the BaseConverter abstract
interface that all concrete converters must implement.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ConversionResult:
    """Outcome of a single conversion attempt."""
    success: bool
    output_path: str = ""
    error_message: str = ""
    log_lines: list = field(default_factory=list)

    @classmethod
    def ok(cls, output_path: str, log_lines: list = None) -> "ConversionResult":
        return cls(success=True, output_path=output_path, log_lines=log_lines or [])

    @classmethod
    def fail(cls, error: str, log_lines: list = None) -> "ConversionResult":
        return cls(success=False, error_message=error, log_lines=log_lines or [])


# Signature: progress_callback(percent: int, message: str)
ProgressCallback = Callable[[int, str], None]


class BaseConverter(abc.ABC):
    """
    Abstract base class for notebook → PDF converters.

    All converters must implement :meth:`convert` and :meth:`is_available`.
    """

    #: Human-readable name for UI display
    display_name: str = "Base Converter"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if this converter's dependencies are satisfied."""

    @abc.abstractmethod
    def convert(
        self,
        notebook_path: str,
        output_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> ConversionResult:
        """
        Convert *notebook_path* to a PDF at *output_path*.

        Parameters
        ----------
        notebook_path:
            Absolute path to the source .ipynb file.
        output_path:
            Absolute path for the output .pdf file.
        progress_cb:
            Optional callback invoked with ``(percent, message)`` during conversion.

        Returns
        -------
        ConversionResult
        """
