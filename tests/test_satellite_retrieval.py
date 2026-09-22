"""Satellite retrieval tests — mocked CDSE, no internet."""

import datetime as _dt
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.satellite.coverage import compute_aoi_coverage
from backend.satellite.models import RetrievalRequest, SatelliteScene
from backend.satellite.ranking import compute_selection_score, rank_scenes

# ---- Helpers ----

_BENGALURU_GEO = {
    "type": "Polygon",
    "coordinates": [[[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]],
}

_SCENE_GEOM_FULL = _BENGALURU_GEO  # same as AOI -> 100% coverage
_SCENE_GEOM_HALF = {
    "type": "Polygon",
    "coordinates": [[[77.45, 12.85], [77.60, 12.85], [77.60, 13.05], [77.45, 13.05], [77.45, 12.85]]],
}  # approx 50% width


def _valid_req(**over):
    base = dict(
        sensor="sentinel-2",
        product="l2a",
        geometry=_BENGALURU_GEO,
        start_date="2026-06-01",
        end_date="2026-06-30",
        max_cloud_cover=20,
        max_results=10,
    )
    base.update(over)
    return RetrievalRequest(**base)


def _make_scene(id="S2A_20260615", cloud=5.0, coverage=95.0, dt="2026-06-15T05:00:00Z", collection="sentinel-2-l2a"):
    from datetime import datetime

    s = dt.replace("Z", "+00:00")
    return SatelliteScene(
        id=id,
        collection=collection,
        datetime=datetime.fromisoformat(s),
        platform="sentinel-2a",
        processing_level="L2A",
        cloud_cover=cloud,
        geometry=_SCENE_GEOM_FULL,
        bbox=[77.45, 12.85, 77.75, 13.05],
        coverage=coverage,
        thumbnail="https://example.com/thumb.jpg",
        assets={"B02": "https://example.com/B02.jp2", "B04": "https://example.com/B04.jp2", "visual": "https://example.com/visual.jpg"},
    )


# ---- Model validation ----

def test_retrieval_request_valid():
    r = _valid_req()
    assert r.collection == "sentinel-2-l2a"
    assert r.stac_datetime() == "2026-06-01/2026-06-30"


def test_invalid_dates():
    with pytest.raises(Exception) as e:
        _valid_req(start_date="2026-06-30", end_date="2026-06-01")
    assert "start_date" in str(e.value).lower()


def test_invalid_cloud_cover():
    with pytest.raises(Exception):
        _valid_req(max_cloud_cover=150)
    with pytest.raises(Exception):
        _valid_req(max_cloud_cover=-5)


def test_invalid_geometry():
    with pytest.raises(Exception):
        _valid_req(geometry={"type": "Invalid", "coordinates": []})
    with pytest.raises(Exception):
        RetrievalRequest(
            sensor="sentinel-2",
            product="l2a",
            geometry={"type": "Polygon", "coordinates": []},  # empty will be invalid shapely
            start_date="2026-06-01",
            end_date="2026-06-30",
        )


def test_invalid_sensor_product():
    with pytest.raises(Exception):
        _valid_req(sensor="unknown-sensor")
    with pytest.raises(Exception):
        _valid_req(sensor="sentinel-2", product="l9")


def test_required_bands_auto_from_analysis():
    r = RetrievalRequest(
        sensor="sentinel-2",
        product="l2a",
        geometry=_BENGALURU_GEO,
        start_date="2026-06-01",
        end_date="2026-06-30",
        required_analysis="NDVI",
    )
    assert r.required_bands == ["B04", "B08"]


# ---- Coverage ----

def test_coverage_full():
    # Use shapely if available; fallback returns 100
    cov = compute_aoi_coverage(_SCENE_GEOM_FULL, _BENGALURU_GEO)
    assert 99 <= cov <= 100


def test_coverage_half():
    cov = compute_aoi_coverage(_SCENE_GEOM_HALF, _BENGALURU_GEO)
    # Approx 50% (+/-5 due to planar)
    assert 40 <= cov <= 60


def test_coverage_no_overlap():
    far = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    cov = compute_aoi_coverage(far, _BENGALURU_GEO)
    assert cov == 0.0


def test_coverage_none_geometry():
    cov = compute_aoi_coverage(None, _BENGALURU_GEO)
    assert cov == 0.0


# ---- Ranking ----

def test_ranking_coverage_dominates():
    s1 = _make_scene(id="low_cloud_high_cov", cloud=5, coverage=95)
    s2 = _make_scene(id="high_cloud_low_cov", cloud=40, coverage=60)
    ranked = rank_scenes([s2, s1], start_date=_dt.date(2026, 6, 1), end_date=_dt.date(2026, 6, 30))
    assert ranked[0].id == s1.id
    assert ranked[0].selection_score > ranked[1].selection_score  # type: ignore


def test_ranking_cloud_tie_break():
    s1 = _make_scene(id="s1", cloud=5, coverage=80, dt="2026-06-10T00:00:00Z")
    s2 = _make_scene(id="s2", cloud=15, coverage=80, dt="2026-06-10T00:00:00Z")
    ranked = rank_scenes([s2, s1], start_date=_dt.date(2026, 6, 1), end_date=_dt.date(2026, 6, 30))
    assert ranked[0].id == "s1"


def test_ranking_temporal_recent_preferred():
    s_old = _make_scene(id="old", cloud=10, coverage=80, dt="2026-06-02T00:00:00Z")
    s_new = _make_scene(id="new", cloud=10, coverage=80, dt="2026-06-28T00:00:00Z")
    ranked = rank_scenes([s_old, s_new], start_date=_dt.date(2026, 6, 1), end_date=_dt.date(2026, 6, 30))
    # New should rank higher due to temporal score
    assert ranked[0].id == "new"


def test_selection_score_formula_clamped():
    s = _make_scene(cloud=0, coverage=100, dt="2026-06-15T00:00:00Z")
    score = compute_selection_score(s, start_date=_dt.date(2026, 6, 1), end_date=_dt.date(2026, 6, 30))
    assert 0 <= score <= 1
    # Perfect cloud+coverage should be high (>0.85)
    assert score > 0.85


# ---- STAC parsing ----

def test_stac_item_parsing():
    from backend.satellite.client import _parse_stac_item  # type: ignore

    item = {
        "id": "S2B_20260618",
        "collection": "sentinel-2-l2a",
        "geometry": _BENGALURU_GEO,
        "bbox": [77.45, 12.85, 77.75, 13.05],
        "properties": {
            "datetime": "2026-06-18T05:12:34Z",
            "platform": "sentinel-2b",
            "eo:cloud_cover": 4.2,
            "processing:level": "L2A",
        },
        "assets": {
            "B04": {"href": "https://example.com/B04.jp2", "type": "image/jp2"},
            "thumbnail": {"href": "https://example.com/thumb.jpg", "type": "image/jpeg"},
        },
    }
    sc = _parse_stac_item(item)
    assert sc is not None
    assert sc.id == "S2B_20260618"
    assert sc.cloud_cover == 4.2
    assert sc.thumbnail == "https://example.com/thumb.jpg"
    assert "B04" in sc.assets


def test_stac_item_missing_assets():
    from backend.satellite.client import _parse_stac_item

    item = {
        "id": "empty",
        "collection": "sentinel-2-l2a",
        "geometry": _BENGALURU_GEO,
        "properties": {"datetime": "2026-06-10T00:00:00Z", "eo:cloud_cover": 10},
        "assets": {},
    }
    sc = _parse_stac_item(item)
    assert sc is not None
    assert sc.assets == {}


# ---- Agent ----

def test_agent_search_mocked():
    mock_scenes = [_make_scene(id="A", cloud=10, coverage=100), _make_scene(id="B", cloud=5, coverage=80)]

    # Patch search_cdse to return mock scenes without geometry (agent computes coverage)
    with patch("backend.satellite.agent.search_cdse", return_value=mock_scenes):
        from backend.satellite.agent import search_satellite_data

        params = {
            "sensor": "sentinel-2",
            "product": "l2a",
            "geometry": _BENGALURU_GEO,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "max_cloud_cover": 20,
            "max_results": 2,
        }
        result = search_satellite_data(params)
        assert result["count"] == 2
        assert result["best_scene"] is not None
        # coverage computed
        for s in result["scenes"]:
            assert s.coverage is not None
            assert s.selection_score is not None
        assert result["trace"]["results_found"] == 2
        assert result["trace"]["provider"] == "CDSE"


def test_agent_caching():
    from backend.satellite import cache as sat_cache

    sat_cache.clear_cache()
    mock_scenes = [_make_scene(id="cached1")]

    with patch("backend.satellite.agent.search_cdse", return_value=mock_scenes) as mock_search:
        from backend.satellite.agent import search_satellite_data

        params = {
            "sensor": "sentinel-2",
            "product": "l2a",
            "geometry": _BENGALURU_GEO,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "max_cloud_cover": 20,
            "max_results": 5,
        }
        r1 = search_satellite_data(params)
        r2 = search_satellite_data(params)
        # Second call uses cache, so search_cdse called once
        assert mock_search.call_count == 1
        assert r1["count"] == r2["count"] == 1
    sat_cache.clear_cache()


# ---- API endpoint (mocked) ----

def test_api_satellite_search_success():
    client = TestClient(app)
    mock_scenes = [_make_scene(id="api_scene", cloud=4.2, coverage=98.7)]

    with patch("backend.satellite.agent.search_cdse", return_value=mock_scenes):
        # Also patch coverage + ranking already handled; mock_scenes will be enriched
        payload = {
            "geometry": _BENGALURU_GEO,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "max_cloud_cover": 20,
            "sensor": "sentinel-2",
            "product": "l2a",
            "max_results": 10,
        }
        r = client.post("/api/satellite/search", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] >= 1
        assert "scenes" in data
        assert data["scenes"][0]["id"] == "api_scene"
        assert data["best_scene"] is not None
        assert data["trace"]["provider"] == "CDSE"
        assert data["execution_trace"]["task"] == "satellite_retrieval"


def test_api_satellite_search_empty():
    client = TestClient(app)
    with patch("backend.satellite.agent.search_cdse", return_value=[]):
        payload = {
            "geometry": _BENGALURU_GEO,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "max_cloud_cover": 5,
        }
        r = client.post("/api/satellite/search", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["scenes"] == []
        assert data["best_scene"] is None


def test_api_invalid_dates():
    client = TestClient(app)
    payload = {
        "geometry": _BENGALURU_GEO,
        "start_date": "2026-06-30",
        "end_date": "2026-06-01",
        "max_cloud_cover": 20,
    }
    r = client.post("/api/satellite/search", json=payload)
    assert r.status_code == 422


def test_api_provider_failure():
    client = TestClient(app)
    # Clear cache so search_cdse is actually called
    from backend.satellite import cache as _sat_cache

    _sat_cache.clear_cache()
    with patch("backend.satellite.agent.search_cdse", side_effect=RuntimeError("CDSE down")):
        payload = {
            "geometry": _BENGALURU_GEO,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        }
        r = client.post("/api/satellite/search", json=payload)
        assert r.status_code == 502
        assert "temporarily unavailable" in r.json()["detail"].lower()


def test_api_invalid_geometry():
    client = TestClient(app)
    payload = {
        "geometry": {"type": "Invalid", "coordinates": []},
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
    }
    r = client.post("/api/satellite/search", json=payload)
    assert r.status_code == 422


def test_api_satellite_health():
    client = TestClient(app)
    r = client.get("/api/satellite/health")
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "CDSE"
    assert "stac_url" in data


# ---- Planner / controller routing ----

def test_controller_classify_retrieval():
    from backend.controller import classify_task, parse_retrieval_params

    assert classify_task("Find Sentinel-2 imagery for this region from June 2026.", "single") == "satellite_retrieval"
    assert classify_task("Find a Sentinel-2 image with less than 10% cloud cover.", "single") == "satellite_retrieval"
    assert classify_task("Get the best satellite image for this AOI between June 1 and June 30.", "single") == "satellite_retrieval"
    assert classify_task("Find satellite imagery of this area suitable for vegetation analysis.", "single") == "satellite_retrieval"
    # VQA should not be misclassified
    assert classify_task("Describe the land cover", "single") == "vqa"
    assert classify_task("How many buildings?", "single") == "count"


def test_parse_retrieval_params_dates_and_cloud():
    from backend.controller import parse_retrieval_params

    p = parse_retrieval_params("Find Sentinel-2 imagery from 2026-06-01 to 2026-06-30 with less than 10% cloud cover.")
    assert p["sensor"] == "sentinel-2"
    assert p["max_cloud_cover"] == 10.0
    assert p["start_date"] == "2026-06-01"
    assert p["end_date"] == "2026-06-30"

    p2 = parse_retrieval_params("Find Sentinel-2 imagery for June 2026")
    assert p2["start_date"] == "2026-06-01"
    assert p2["end_date"] == "2026-06-30"


def test_registry_has_satellite():
    from backend import registry

    mod = registry.get_specialist("satellite_retrieval")
    assert mod is not None
    assert hasattr(mod, "search_satellite_data") or hasattr(mod, "predict")
    info = mod.get_model_info()
    assert info["is_real"] is True


def test_controller_handle_retrieval_graceful_no_geometry():
    from backend.controller import handle

    # Retrieval query without geometry should return instructional answer, not crash
    resp = handle("Find Sentinel-2 imagery from 2026-06-01 to 2026-06-30", [], "single")
    assert resp.execution_trace.task == "satellite_retrieval"
    assert "AOI" in resp.answer


# ---- Asset discovery ----

def test_asset_discovery_dynamic():
    from backend.satellite.client import _parse_stac_item

    item = {
        "id": "asset_test",
        "collection": "sentinel-2-l2a",
        "geometry": _BENGALURU_GEO,
        "properties": {"datetime": "2026-06-15T00:00:00Z", "eo:cloud_cover": 5},
        "assets": {
            "B02": {"href": "https://a/B02.jp2"},
            "B03": {"href": "https://a/B03.jp2"},
            "B04": {"href": "https://a/B04.jp2"},
            "B08": {"href": "https://a/B08.jp2"},
            "thumbnail": {"href": "https://a/thumb.jpg"},
            "custom_band": {"href": "https://a/custom.tif"},
        },
    }
    sc = _parse_stac_item(item)
    assert sc is not None
    assert set(["B02", "B03", "B04", "B08", "custom_band"]).issubset(set(sc.assets.keys()))
    assert sc.thumbnail is not None
