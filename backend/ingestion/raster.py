"""Raster metadata extraction — rasterio with safe fallback, no huge load."""

from __future__ import annotations

from typing import Any

from backend.core.assets import SatelliteAsset


def extract_raster_metadata(data: bytes, filename: str | None = None) -> dict[str, Any]:
    """Extract raster metadata via rasterio MemoryFile without loading full array.

    Returns dict with width, height, bands, dtype, crs, resolution, bounding_box, etc.
    Raises if rasterio unavailable or file unreadable.
    """
    try:
        import rasterio  # type: ignore
        from rasterio.io import MemoryFile  # type: ignore
    except ImportError as e:
        raise ImportError("rasterio not installed — cannot extract GeoTIFF/JP2 metadata") from e

    with MemoryFile(data) as mem:
        with mem.open() as ds:
            crs = str(ds.crs) if ds.crs else None
            transform = ds.transform
            geotransform = [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f] if transform else None
            # resolution: pixel size (approx)
            resolution = abs(transform.a) if transform else None
            bbox = None
            try:
                b = ds.bounds
                bbox = [float(b.left), float(b.bottom), float(b.right), float(b.top)]
            except Exception:
                pass
            # band names from tags if available
            band_names = None
            try:
                # attempt to read band descriptions
                descs = ds.descriptions
                if descs and any(descs):
                    band_names = [d or f"B{i+1}" for i, d in enumerate(descs)]
            except Exception:
                pass
            return {
                "width": int(ds.width),
                "height": int(ds.height),
                "bands": int(ds.count),
                "dtype": str(ds.dtypes[0]) if ds.dtypes else "unknown",
                "crs": crs,
                "geotransform": geotransform,
                "resolution": float(resolution) if resolution else None,
                "bounding_box": bbox,
                "band_names": band_names,
                "driver": ds.driver,
            }


def raster_to_asset(data: bytes, filename: str | None = None) -> SatelliteAsset:
    """Full ingestion for GeoTIFF/JP2 using raster metadata + PIL preview."""
    from backend.ingestion.image import ingest_uploaded_image

    # Reuse image ingestion which already tries raster metadata
    return ingest_uploaded_image(filename, data)
