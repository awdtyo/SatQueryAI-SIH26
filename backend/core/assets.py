"""Unified SatelliteAsset abstraction — any EO input becomes this.

Both uploaded imagery and live Sentinel-2 retrieval produce SatelliteAsset.
Never hallucinate metadata: unavailable fields remain None/unknown.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceType = Literal["upload", "live"]


class SatelliteAsset(BaseModel):
    """Clean internal representation for any EO input."""

    asset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: SourceType = Field(description='"upload" or "live"')

    # Image reference — PIL, bytes, path, or STAC href
    image: Any | None = Field(default=None, description="PIL.Image | bytes | path | STAC asset href")
    filename: str | None = None
    format: str | None = Field(default=None, description="jpeg/png/geotiff/jp2 etc, lower-case ext without dot")
    width: int | None = None
    height: int | None = None
    channels: int | None = None
    dtype: str | None = None  # e.g. uint8, uint16, float32

    # Band / sensor metadata — only when available
    bands: int | None = None
    band_names: list[str] | None = None
    sensor: str | None = None  # sentinel-2, landsat, etc
    platform: str | None = None

    # Temporal / spatial — only when available, never hallucinated
    acquisition_time: datetime | None = None
    crs: str | None = None  # e.g. EPSG:4326
    resolution: float | None = None  # m per pixel
    geotransform: list[float] | None = None
    cloud_cover: float | None = None
    bounding_box: list[float] | None = None  # [minx, miny, maxx, maxy] or bbox from STAC

    # Generic metadata / provenance
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    # Hash for provenance (optional, computed lazily)
    image_hash: str | None = None

    class Config:
        arbitrary_types_allowed = True

    def compute_hash(self, data: bytes | None = None) -> str | None:
        """Compute sha256 of image bytes if available."""
        try:
            if data is not None:
                h = hashlib.sha256(data).hexdigest()[:16]
                self.image_hash = h
                return h
            if isinstance(self.image, (bytes, bytearray)):
                h = hashlib.sha256(bytes(self.image)).hexdigest()[:16]
                self.image_hash = h
                return h
        except Exception:
            pass
        return None

    @property
    def is_geotiff(self) -> bool:
        return (self.format or "").lower() in ("tif", "tiff", "geotiff")

    @property
    def has_geospatial(self) -> bool:
        return bool(self.crs or self.bounding_box or self.geotransform)

    def to_provenance_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_type": self.source_type,
            "filename": self.filename,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "bands": self.bands,
            "band_names": self.band_names,
            "sensor": self.sensor,
            "platform": self.platform,
            "acquisition_time": self.acquisition_time.isoformat() if self.acquisition_time else None,
            "crs": self.crs,
            "resolution": self.resolution,
            "cloud_cover": self.cloud_cover,
            "bounding_box": self.bounding_box,
            "image_hash": self.image_hash,
        }


def asset_from_live_scene(scene: dict[str, Any] | Any, aoi: dict[str, Any] | None = None) -> SatelliteAsset:
    """Create SatelliteAsset from a live SatelliteScene (CDSE STAC)."""
    if isinstance(scene, dict):
        sid = str(scene.get("id") or scene.get("scene_id") or "live-scene")
        dt_raw = scene.get("datetime")
        try:
            dt = datetime.fromisoformat(str(dt_raw).replace("Z", "+00:00")) if dt_raw else None
        except Exception:
            dt = None
        return SatelliteAsset(
            source_type="live",
            filename=sid,
            format="stac",
            sensor=scene.get("collection") or scene.get("sensor") or "sentinel-2",
            platform=scene.get("platform"),
            acquisition_time=dt,
            crs="EPSG:4326",
            cloud_cover=scene.get("cloud_cover"),
            bounding_box=scene.get("bbox"),
            metadata={"scene": scene, "aoi": aoi},
            provenance={"source": "copernicus_stac", "scene_id": sid},
        )
    # Pydantic SatelliteScene
    try:
        return SatelliteAsset(
            source_type="live",
            filename=str(getattr(scene, "id", "live-scene")),
            format="stac",
            sensor=str(getattr(scene, "collection", "sentinel-2")),
            platform=getattr(scene, "platform", None),
            acquisition_time=getattr(scene, "datetime", None),
            cloud_cover=getattr(scene, "cloud_cover", None),
            bounding_box=getattr(scene, "bbox", None),
            metadata={"scene": scene.model_dump() if hasattr(scene, "model_dump") else {}, "aoi": aoi},
            provenance={"source": "copernicus_stac"},
        )
    except Exception:
        return SatelliteAsset(source_type="live", filename="live-scene", format="stac")


__all__ = ["SatelliteAsset", "asset_from_live_scene"]
