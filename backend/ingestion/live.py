"""Live ingestion — Sentinel-2 STAC scene -> SatelliteAsset."""

from __future__ import annotations

from typing import Any

from backend.core.assets import SatelliteAsset, asset_from_live_scene


def ingest_live_scene(scene: dict[str, Any] | Any, aoi: dict[str, Any] | None = None) -> SatelliteAsset:
    """Convert live scene to SatelliteAsset (no image bytes, just provenance)."""
    return asset_from_live_scene(scene, aoi=aoi)


__all__ = ["ingest_live_scene"]
