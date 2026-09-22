"""Spectral index tests — synthetic rasters, no real download per test."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.spectral.calculator import (
    calc_ndvi,
    calc_ndwi,
    calc_ndbi,
    calc_ndmi,
    calc_savi,
    calc_bsi,
    calculate_index,
)
from backend.spectral.stats import calculate_stats
from backend.spectral.masking import mask_from_scl, mask_nodata, apply_masks
from backend.spectral.registry import INDEX_REGISTRY, get_index_info, resolve_index_name

# ---- Helpers ----

BENGALURU_AOI = {
    "type": "Polygon",
    "coordinates": [[[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]],
}

FAKE_SCENE = {
    "id": "S2A_test_scene",
    "collection": "sentinel-2-l2a",
    "datetime": "2026-06-15T05:00:00Z",
    "platform": "sentinel-2a",
    "cloud_cover": 5.0,
    "geometry": BENGALURU_AOI,
    "bbox": [77.45, 12.85, 77.75, 13.05],
    "assets": {
        "B02": "https://example.com/B02.jp2",
        "B03": "https://example.com/B03.jp2",
        "B04": "https://example.com/B04.jp2",
        "B08": "https://example.com/B08.jp2",
        "B11": "https://example.com/B11.jp2",
        "SCL": "https://example.com/SCL.jp2",
        "thumbnail": "https://example.com/thumb.jpg",
    },
    "thumbnail": "https://example.com/thumb.jpg",
}


# ---- 1-6: Formula tests ----

def test_ndvi_formula():
    b08 = np.array([[8000, 4000], [2000, 1000]], dtype=np.float32)
    b04 = np.array([[2000, 2000], [2000, 1000]], dtype=np.float32)
    ndvi = calc_ndvi(b08, b04)
    # (8000-2000)/(10000)=0.6, (4000-2000)/6000=0.333, (2000-2000)/4000=0, (1000-1000)/2000=0
    assert np.isclose(ndvi[0, 0], 0.6, atol=1e-5)
    assert np.isclose(ndvi[0, 1], 0.333333, atol=1e-5)
    assert np.isclose(ndvi[1, 0], 0.0, atol=1e-5)


def test_ndwi_formula():
    b03 = np.array([[6000, 3000]], dtype=np.float32)
    b08 = np.array([[2000, 3000]], dtype=np.float32)
    ndwi = calc_ndwi(b03, b08)
    assert np.isclose(ndwi[0, 0], (6000 - 2000) / (8000), atol=1e-5)
    assert np.isclose(ndwi[0, 1], 0.0, atol=1e-5)


def test_ndbi_formula():
    b11 = np.array([[5000, 2000]], dtype=np.float32)
    b08 = np.array([[3000, 4000]], dtype=np.float32)
    ndbi = calc_ndbi(b11, b08)
    assert np.isclose(ndbi[0, 0], (5000 - 3000) / 8000, atol=1e-5)
    assert np.isclose(ndbi[0, 1], (2000 - 4000) / 6000, atol=1e-5)


def test_ndmi_formula():
    b08 = np.array([[5000]], dtype=np.float32)
    b11 = np.array([[2000]], dtype=np.float32)
    ndmi = calc_ndmi(b08, b11)
    assert np.isclose(ndmi[0, 0], (5000 - 2000) / 7000, atol=1e-5)


def test_savi_formula():
    b08 = np.array([[8000]], dtype=np.float32)
    b04 = np.array([[2000]], dtype=np.float32)
    savi = calc_savi(b08, b04, L=0.5)
    # ((8000-2000)/(10000+0.5))*1.5 ≈ 0.59997
    expected = ((8000 - 2000) / (8000 + 2000 + 0.5)) * 1.5
    assert np.isclose(savi[0, 0], expected, atol=1e-5)


def test_bsi_formula():
    b11 = np.array([[4000]], dtype=np.float32)
    b04 = np.array([[2000]], dtype=np.float32)
    b08 = np.array([[3000]], dtype=np.float32)
    b02 = np.array([[1000]], dtype=np.float32)
    bsi = calc_bsi(b11, b04, b08, b02)
    expected = ((4000 + 2000) - (3000 + 1000)) / ((4000 + 2000) + (3000 + 1000))
    assert np.isclose(bsi[0, 0], expected, atol=1e-5)


# ---- Dispatcher ----

def test_calculate_index_dispatcher():
    bands = {"B08": np.array([[8000]], dtype=np.float32), "B04": np.array([[2000]], dtype=np.float32)}
    ndvi = calculate_index("NDVI", bands)
    assert ndvi.shape == (1, 1)
    with pytest.raises(ValueError):
        calculate_index("UNKNOWN", bands)


# ---- Divide-by-zero handling ----

def test_divide_by_zero():
    b08 = np.array([[0, 1000]], dtype=np.float32)
    b04 = np.array([[0, 1000]], dtype=np.float32)
    ndvi = calc_ndvi(b08, b04)
    assert np.isnan(ndvi[0, 0])  # 0/0 -> nan
    assert np.isclose(ndvi[0, 1], 0.0, atol=1e-6)  # (1000-1000)=0 /2000 =0
    # Explicit 0 denom
    b08z = np.array([[1000]], dtype=np.float32)
    b04z = np.array([[-1000]], dtype=np.float32)  # sum 0
    ndvi2 = calc_ndvi(b08z, b04z)
    assert np.isnan(ndvi2[0, 0])


# ---- Nodata handling ----

def test_nodata_handling():
    b08 = np.array([[8000, np.nan, 5000]], dtype=np.float32)
    b04 = np.array([[2000, 2000, np.nan]], dtype=np.float32)
    ndvi = calc_ndvi(b08, b04)
    # nan propagates? Our calc uses float, nan in input -> nan in output where den nan
    assert np.isnan(ndvi[0, 1])
    assert np.isnan(ndvi[0, 2])
    # Apply nodata mask
    mask = mask_nodata(b08, b04)
    assert not mask[0, 1]
    assert not mask[0, 2]
    masked = apply_masks(ndvi, mask)
    assert np.isnan(masked[0, 1])
    assert np.isnan(masked[0, 2])


def test_band_alignment_via_resample():
    # Simulate 10m vs 20m: B08 4x4, B11 2x2 -> resample B11 to 4x4
    b08 = np.ones((4, 4), dtype=np.float32) * 8000
    b11_small = np.ones((2, 2), dtype=np.float32) * 4000
    # Simulate resample via kron (nearest)
    b11_resampled = np.kron(b11_small, np.ones((2, 2), dtype=np.float32))
    assert b11_resampled.shape == b08.shape
    ndmi = calc_ndmi(b08, b11_resampled)
    assert ndmi.shape == (4, 4)
    # All same value
    assert np.allclose(ndmi, (8000 - 4000) / 12000, atol=1e-5)


# ---- AOI clipping (synthetic) ----

def test_aoi_clipping_shape():
    # AOI smaller than scene should produce smaller window
    # This is tested via processor bounds, but we test helper directly
    from backend.spectral.processor import _get_aoi_bounds_4326

    west, south, east, north = _get_aoi_bounds_4326(BENGALURU_AOI)
    assert west == 77.45
    assert south == 12.85
    assert east == 77.75
    assert north == 13.05


# ---- Cloud masking ----

def test_cloud_mask_scl():
    scl = np.array([[4, 8, 0, 11, 5]], dtype=np.uint8)
    mask = mask_from_scl(scl)
    # 4 vegetation valid, 8 cloud masked, 0 nodata masked, 11 snow masked, 5 valid
    assert mask[0, 0] == True
    assert mask[0, 1] == False
    assert mask[0, 2] == False
    assert mask[0, 3] == False
    assert mask[0, 4] == True


# ---- Unsupported index / missing band / invalid scene ----

def test_unsupported_index():
    client = TestClient(app)
    r = client.post(
        "/api/analysis/spectral-index",
        json={"index": "UNKNOWN", "scene": FAKE_SCENE, "aoi": BENGALURU_AOI},
    )
    assert r.status_code == 422
    assert "Unsupported index" in r.json()["detail"]


def test_missing_band():
    scene_missing = {**FAKE_SCENE, "assets": {"B04": "https://a/B04"}}  # missing B08
    client = TestClient(app)
    r = client.post("/api/analysis/spectral-index", json={"index": "NDVI", "scene": scene_missing, "aoi": BENGALURU_AOI})
    assert r.status_code == 422
    assert "B08" in r.json()["detail"]


def test_invalid_scene():
    client = TestClient(app)
    r = client.post("/api/analysis/spectral-index", json={"index": "NDVI", "scene": {}, "aoi": BENGALURU_AOI})
    assert r.status_code in (422, 500)


def test_invalid_aoi():
    client = TestClient(app)
    r = client.post("/api/analysis/spectral-index", json={"index": "NDVI", "scene": FAKE_SCENE, "aoi": {"type": "Invalid"}})
    assert r.status_code == 422


# ---- API request/response with mocked raster ----

def test_api_spectral_success_mocked():
    client = TestClient(app)
    # Mock process_bands to avoid real download, and preview generation
    fake_arr = np.array([[0.5, 0.6], [0.2, np.nan]], dtype=np.float32)
    fake_profile = {"crs": "EPSG:32643", "transform": [10, 0, 77.45, 0, -10, 13.05], "width": 2, "height": 2}
    fake_proc = {
        "bands": {"B08": np.ones((2, 2), dtype=np.float32) * 8000, "B04": np.ones((2, 2), dtype=np.float32) * 2000},
        "profile": fake_profile,
        "shape": (2, 2),
        "cloud_mask": np.array([[True, True], [True, False]]),
        "cloud_applied": True,
    }
    # Patch process_bands and preview
    with patch("backend.spectral.agent.process_bands", return_value=fake_proc) as mock_proc:
        with patch("backend.spectral.agent.calculate_index", return_value=fake_arr) as mock_calc:
            with patch("backend.spectral.agent._save_geotiff", return_value=None) as mock_save:
                with patch("backend.spectral.agent._generate_preview_png", return_value="data:image/png;base64,abc") as mock_prev:
                    # Need to mock rasterio bounds handling for preview bounds
                    with patch("backend.spectral.agent.rasterio") as mock_raster:
                        # Actually process_spectral_index will call these, but we mock them above, so no need
                        r = client.post(
                            "/api/analysis/spectral-index",
                            json={"index": "NDVI", "scene": FAKE_SCENE, "aoi": BENGALURU_AOI, "cloud_mask": True},
                        )
                        # Since we mocked process_bands and calculate_index, but process_spectral_index still runs stats etc
                        # It should succeed if we mock correctly
                        # Our patch for process_bands is in agent module, but agent.process_spectral_index calls process_bands internally
                        # So patching agent.process_bands should work
                        # However _save_geotiff and _generate_preview are also in agent
                        # Let's check response
                        assert r.status_code == 200, r.text
                        data = r.json()
                        assert data["index"] == "NDVI"
                        assert data["scene_id"] == "S2A_test_scene"
                        assert "stats" in data
                        assert "raster_path" in data
                        assert data["cloud_applied"] is True
                        assert "provenance" in data
                        assert "trace_steps" in data
                        assert len(data["trace_steps"]) > 5


def test_agent_routing():
    from backend.controller import classify_task, parse_spectral_params

    assert classify_task("Calculate NDVI for this area.", "single") == "spectral_index"
    assert classify_task("Show vegetation health.", "single") == "spectral_index"
    assert classify_task("Calculate NDWI.", "single") == "spectral_index"
    assert classify_task("Find built-up areas using NDBI.", "single") == "spectral_index"
    assert classify_task("Show bare soil", "single") == "spectral_index"
    assert parse_spectral_params("Calculate NDVI")["index"] == "NDVI"
    assert parse_spectral_params("Show vegetation health")["index"] == "NDVI"
    assert parse_spectral_params("Find built-up areas")["index"] == "NDBI"


def test_registry_spectral():
    from backend import registry

    mod = registry.get_specialist("spectral_index")
    assert mod is not None
    assert hasattr(mod, "predict")
    info = mod.get_model_info()
    assert info["is_real"] is True
    assert "NDVI" in info["indices"]


def test_map_layer_response():
    # Test that preview_b64 and bounds are correctly formed for map overlay
    client = TestClient(app)
    fake_arr = np.array([[0.2, 0.8], [0.5, 0.6]], dtype=np.float32)
    fake_profile = {"crs": "EPSG:32643", "transform": [10, 0, 77.45, 0, -10, 13.05], "width": 2, "height": 2}
    fake_proc = {
        "bands": {"B08": np.ones((2, 2), dtype=np.float32) * 8000, "B04": np.ones((2, 2), dtype=np.float32) * 2000},
        "profile": fake_profile,
        "shape": (2, 2),
        "cloud_mask": None,
        "cloud_applied": False,
    }
    with patch("backend.spectral.agent.process_bands", return_value=fake_proc):
        with patch("backend.spectral.agent.calculate_index", return_value=fake_arr):
            with patch("backend.spectral.agent._save_geotiff", return_value=None):
                with patch("backend.spectral.agent._generate_preview_png", return_value="data:image/png;base64,xyz"):
                    with patch("rasterio.transform.array_bounds", return_value=(77.45, 12.85, 77.75, 13.05)):
                        with patch("rasterio.warp.transform_bounds", return_value=(77.45, 12.85, 77.75, 13.05)):
                            r = client.post("/api/analysis/spectral-index", json={"index": "NDVI", "scene": FAKE_SCENE, "aoi": BENGALURU_AOI})
                            assert r.status_code == 200, r.text
                            data = r.json()
                            assert data["preview_b64"] is not None
                            assert data["preview_b64"].startswith("data:image/png")
                            assert data["bounds"] is not None  # Leaflet [[south,west],[north,east]]
                            assert len(data["bounds"]) == 2


def test_statistics_valid_pixels():
    arr = np.array([[0.5, 0.6, np.nan], [0.2, np.nan, 0.9]], dtype=np.float32)
    stats = calculate_stats(arr)
    assert stats["valid_pixels"] == 4
    assert stats["masked_pixels"] == 2
    assert 66 < stats["valid_pct"] < 67
    assert 0.2 <= stats["min"] <= 0.5
    assert np.isclose(stats["max"], 0.9, atol=1e-5)
