"""Exceptions package."""

from .errors import (
    DocumentProcessorError,
    UnsupportedFileTypeError,
    FileNotFoundError as DocFileNotFoundError,
    ExtractError,
    OCRError,
    NormalizationError,
    SplitterError,
    ValidationError,
)

__all__ = [
    "DocumentProcessorError",
    "UnsupportedFileTypeError",
    "DocFileNotFoundError",
    "ExtractError",
    "OCRError",
    "NormalizationError",
    "SplitterError",
    "ValidationError",
]
