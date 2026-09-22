"""Spectral index package."""

from .registry import INDEX_REGISTRY, get_index_info  # noqa: F401

__all__ = ["INDEX_REGISTRY", "get_index_info"]
