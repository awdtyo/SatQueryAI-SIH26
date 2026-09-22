"""Satellite data models — Pydantic, extensible for S1/Landsat."""

from __future__ import annotations

import datetime as _dt
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Supported sensors/products — extensible
SUPPORTED_SENSORS = {"sentinel-2", "sentinel-1", "landsat"}
SUPPORTED_PRODUCTS = {"l2a", "l1c", "l2", "l1"}  # sentinel-2-l2a is primary
# Collection mapping sensor+product -> STAC collection id
COLLECTION_MAP: dict[tuple[str, str], str] = {
    ("sentinel-2", "l2a"): "sentinel-2-l2a",
    ("sentinel-2", "l1c"): "sentinel-2-l1c",
    # future
    ("sentinel-1", "l1"): "sentinel-1-grd",
    ("landsat", "l2"): "landsat-8-l2",
}

SUPPORTED_COLLECTIONS = set(COLLECTION_MAP.values())

# Band hints for spectral-index planning (future asset retrieval)
INDEX_REQUIRED_BANDS: dict[str, list[str]] = {
    "NDVI": ["B04", "B08"],
    "NDWI": ["B03", "B08"],
    "NDBI": ["B08", "B11"],
    "EVI": ["B02", "B04", "B08"],
}


def _validate_geojson_geometry(v: Any) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise ValueError("geometry must be a GeoJSON object")
    gtype = v.get("type")
    if gtype not in ("Polygon", "MultiPolygon", "Point", "Feature", "FeatureCollection"):
        # Also allow raw geometry with coordinates
        if "coordinates" not in v and "geometry" not in v:
            raise ValueError(f"unsupported GeoJSON type: {gtype}")
    # If Feature/FeatureCollection unwrap to geometry check later via shapely
    return v


class RetrievalRequest(BaseModel):
    """Validated request for live CDSE STAC search."""

    sensor: str = Field(default="sentinel-2", description="sensor name, e.g. sentinel-2")
    product: str = Field(default="l2a", description="product level, e.g. l2a")
    geometry: dict[str, Any] = Field(description="GeoJSON geometry (Polygon/MultiPolygon) AOI in EPSG:4326")
    start_date: date = Field(description="start date inclusive")
    end_date: date = Field(description="end date inclusive")
    max_cloud_cover: float = Field(default=20.0, ge=0, le=100, description="max eo:cloud_cover %")
    max_results: int = Field(default=10, ge=1, le=100, description="max STAC results to fetch")
    # Optional future band-aware hints
    required_bands: list[str] | None = Field(default=None, description="e.g. NDVI -> [B04,B08]")
    required_analysis: str | None = Field(default=None, description="e.g. NDVI, NDWI, NDBI")

    @field_validator("sensor")
    @classmethod
    def _sensor_ok(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in SUPPORTED_SENSORS:
            raise ValueError(f"unsupported sensor '{v}' — supported: {sorted(SUPPORTED_SENSORS)}")
        return s

    @field_validator("product")
    @classmethod
    def _product_ok(cls, v: str) -> str:
        p = v.strip().lower()
        if p not in SUPPORTED_PRODUCTS:
            raise ValueError(f"unsupported product '{p}' — supported: {sorted(SUPPORTED_PRODUCTS)}")
        return p

    @field_validator("geometry")
    @classmethod
    def _geom_ok(cls, v: Any) -> Any:
        return _validate_geojson_geometry(v)

    @model_validator(mode="after")
    def _dates_and_combo(self) -> "RetrievalRequest":
        if self.start_date > self.end_date:
            raise ValueError(f"start_date {self.start_date} must be <= end_date {self.end_date}")
        # Validate sensor/product combo maps to a collection, else warn but allow if known product
        key = (self.sensor, self.product)
        if key not in COLLECTION_MAP:
            # If sentinel-2 + l2a is only supported in MVP, reject others explicitly
            if self.sensor == "sentinel-2" and self.product not in ("l2a", "l1c"):
                raise ValueError(f"unsupported sentinel-2 product '{self.product}' — use l2a or l1c")
            # For other sensors, keep extensible but log — don't hard-fail for sentinel-2/l2a MVP
            if self.sensor != "sentinel-2":
                raise ValueError(f"sensor/product combo {key} not yet supported (MVP: sentinel-2/l2a only)")
        # Auto-populate required_bands from analysis if not supplied
        if self.required_analysis and not self.required_bands:
            bands = INDEX_REQUIRED_BANDS.get(self.required_analysis.upper())
            if bands:
                self.required_bands = bands
        # Validate geometry is shapely-parseable (lightweight check, no heavy import at validation)
        try:
            # Defer shapely import
            from shapely.geometry import shape as _shape

            # Support Feature / FeatureCollection unwrapping
            geom = self.geometry
            if geom.get("type") == "Feature":
                geom = geom.get("geometry", geom)
            elif geom.get("type") == "FeatureCollection":
                feats = geom.get("features", [])
                if not feats:
                    raise ValueError("FeatureCollection has no features")
                geom = feats[0].get("geometry", feats[0])
            shp = _shape(geom)  # type: ignore[arg-type]
            if not shp.is_valid:
                raise ValueError("geometry is not valid (self-intersecting or degenerate)")
            if shp.is_empty:
                raise ValueError("geometry is empty")
        except ImportError:
            # shapely not installed — skip deep validation (endpoint will warn)
            pass
        return self

    @property
    def collection(self) -> str:
        return COLLECTION_MAP.get((self.sensor, self.product), "sentinel-2-l2a")

    def stac_datetime(self) -> str:
        # CDSE expects RFC3339 interval: YYYY-MM-DD/YYYY-MM-DD (inclusive)
        return f"{self.start_date.isoformat()}/{self.end_date.isoformat()}"


class SatelliteScene(BaseModel):
    """Internal scene representation — STAC-agnostic, extensible."""

    id: str = Field(description="STAC item id / scene id")
    collection: str = Field(description="STAC collection, e.g. sentinel-2-l2a")
    datetime: Optional[_dt.datetime] = Field(default=None, description="acquisition datetime (UTC)")
    platform: Optional[str] = Field(default=None, description="platform, e.g. sentinel-2a")
    processing_level: Optional[str] = Field(default=None, description="e.g. L2A")
    cloud_cover: Optional[float] = Field(default=None, description="eo:cloud_cover % 0-100")
    geometry: Optional[dict[str, Any]] = Field(default=None, description="GeoJSON geometry footprint")
    bbox: Optional[list[float]] = Field(default=None, description="[minx,miny,maxx,maxy] in EPSG:4326")
    coverage: Optional[float] = Field(default=None, description="AOI coverage % 0-100")
    selection_score: Optional[float] = Field(default=None, description="heuristic 0-1 ranking score")
    thumbnail: Optional[str] = Field(default=None, description="preview/thumbnail href if available")
    assets: dict[str, str] = Field(default_factory=dict, description="asset name -> href")
    metadata: dict[str, Any] = Field(default_factory=dict, description="useful STAC properties passthrough")

    # Extensibility: provider, constellation, instrument etc.
    provider: str = Field(default="CDSE", description="provider key")

    @field_validator("cloud_cover")
    @classmethod
    def _cloud_ok(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if not (0 <= v <= 100):
            raise ValueError("cloud_cover must be 0-100")
        return float(v)


class SatelliteSearchResponse(BaseModel):
    """API response for POST /api/satellite/search."""

    count: int
    scenes: list[SatelliteScene]
    # Trace metadata (mirrors ExecutionTrace pattern but lightweight)
    provider: str = "CDSE"
    collection: str = "sentinel-2-l2a"
    query: Optional[dict[str, Any]] = None
    # Optional best scene shortcut
    best_scene: Optional[SatelliteScene] = None


class RetrievalTrace(BaseModel):
    """Lightweight retrieval trace entry for ExecutionTrace.models_used expansion."""

    agent: str = "satellite_retrieval"
    operation: str = "search"
    provider: str = "CDSE"
    collection: str = "sentinel-2-l2a"
    results_found: int
    results_after_filtering: int
    selected_scene: Optional[str] = None
    latency_ms: int
    parameters: dict[str, Any] = Field(default_factory=dict)
