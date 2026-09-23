"""Upload ingestion — JPG/PNG/TIFF/JP2 validation, CPU-safe, no full-raster load."""

from __future__ import annotations

import io
import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from backend import config
from backend.core.assets import SatelliteAsset

_ALLOWED_EXTS = config.SUPPORTED_FORMATS  # {.tif,.tiff,.png,.jpg,.jpeg}
# Add jp2 where rasterio/Pillow supports it (optional)
_ALLOWED_EXTS_WITH_JP2 = set(_ALLOWED_EXTS) | {".jp2", ".j2k"}
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
_MAX_DIM = 20000  # max width/height
_MIN_DIM = 16


def validate_upload(filename: str | None, data: bytes, mime: str | None = None) -> None:
    """Raise ValueError if invalid."""
    ext = Path(filename).suffix.lower() if filename else ""
    if ext and ext not in _ALLOWED_EXTS_WITH_JP2:
        raise ValueError(f"Unsupported extension '{ext}'. Allowed: {sorted(_ALLOWED_EXTS_WITH_JP2)}")
    if len(data) == 0:
        raise ValueError(f"Empty file: {filename}")
    if len(data) > _MAX_FILE_SIZE:
        raise ValueError(f"File too large ({len(data)} bytes > {_MAX_FILE_SIZE}) : {filename}")
    # MIME sanity (best-effort, not strict)
    if mime and "image" not in mime.lower() and "tiff" not in mime.lower() and "jp2" not in mime.lower():
        # allow generic octet-stream for .tif uploads (common)
        if mime != "application/octet-stream":
            raise ValueError(f"Invalid MIME type '{mime}' for image {filename}")


def ingest_uploaded_image(filename: str | None, data: bytes, source_type: str = "upload") -> SatelliteAsset:
    """Create SatelliteAsset from raw upload bytes (JPG/PNG/TIFF/JP2)."""
    validate_upload(filename, data)
    ext = Path(filename).suffix.lower() if filename else ""
    fmt = ext.lstrip(".") or "unknown"
    # Pillow check — handles corrupt image
    try:
        pil = Image.open(io.BytesIO(data))
        pil.load()  # catch truncated
        w, h = pil.size
        mode = pil.mode
        channels = len(mode) if mode not in ("P", "L") else (3 if mode == "P" else 1)
        # Normalize P/RGBA etc but keep original info
        if w < _MIN_DIM or h < _MIN_DIM:
            raise ValueError(f"Image too small ({w}x{h}) — min {_MIN_DIM}")
        if w > _MAX_DIM or h > _MAX_DIM:
            raise ValueError(f"Image too large ({w}x{h}) — max {_MAX_DIM}")
        dtype = "uint8"
        # Try raster path for GeoTIFF/JP2 to extract bands/crs without full load
        bands = channels
        band_names = None
        crs = None
        resolution = None
        geotransform = None
        bounding_box = None
        if ext in (".tif", ".tiff", ".jp2", ".j2k"):
            try:
                from backend.ingestion.raster import extract_raster_metadata

                meta = extract_raster_metadata(data, filename=filename)
                bands = meta.get("bands", bands)
                band_names = meta.get("band_names")
                crs = meta.get("crs")
                resolution = meta.get("resolution")
                geotransform = meta.get("geotransform")
                bounding_box = meta.get("bounding_box")
                dtype = meta.get("dtype", dtype)
                w = meta.get("width", w)
                h = meta.get("height", h)
            except Exception:
                pass
        ihash = hashlib.sha256(data).hexdigest()[:16]
        return SatelliteAsset(
            source_type="upload",  # type: ignore
            image=pil.convert("RGB"),
            filename=filename or f"upload.{fmt}",
            format=fmt,
            width=w,
            height=h,
            channels=channels,
            dtype=dtype,
            bands=bands,
            band_names=band_names,
            crs=crs,
            resolution=resolution,
            geotransform=geotransform,
            bounding_box=bounding_box,
            metadata={"mode": mode, "ext": ext},
            provenance={"ingestion": "upload", "filename": filename},
            image_hash=ihash,
        )
    except UnidentifiedImageError as e:
        raise ValueError(f"Corrupt or unsupported image {filename}: {e}") from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to ingest {filename}: {e}") from e


def ingest_pil_image(pil: Image.Image, filename: str | None = None) -> SatelliteAsset:
    """Create asset from already-loaded PIL (e.g., gradio)."""
    w, h = pil.size
    mode = pil.mode
    channels = len(mode) if mode else 3
    ihash = None
    try:
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        ihash = hashlib.sha256(buf.getvalue()).hexdigest()[:16]
    except Exception:
        pass
    return SatelliteAsset(
        source_type="upload",  # type: ignore
        image=pil.convert("RGB"),
        filename=filename or "upload.png",
        format="png",
        width=w,
        height=h,
        channels=channels,
        dtype="uint8",
        bands=channels,
        metadata={"mode": mode},
        provenance={"ingestion": "pil"},
        image_hash=ihash,
    )


__all__ = ["ingest_uploaded_image", "ingest_pil_image", "validate_upload"]
