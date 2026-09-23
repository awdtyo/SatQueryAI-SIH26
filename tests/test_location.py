"""Location-based imagery tests — mocked geocode + STAC, no real network."""

import io
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app


def _png_bytes(size=(224, 224), color=(90, 130, 80)):
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _client():
    return TestClient(app)


def test_location_query_resolves_and_routes():
    client = _client()
    png = _png_bytes()
    with patch("backend.services.geocode.geocode_place") as mock_geo, \
         patch("backend.services.imagery_fetch.fetch_imagery_for_location") as mock_fetch, \
         patch("backend.registry.predict") as mock_predict:
        mock_geo.return_value = {"lat": 12.97, "lon": 77.59, "display_name": "Bengaluru, India"}
        mock_fetch.return_value = ([("location_12.97_77.59.png", png)], [{"scene_id": "S2_123", "collection": "sentinel-2-l2a", "lat": 12.97, "lon": 77.59, "display_name": "Bengaluru, India"}])
        mock_predict.return_value = {"answer": "Vegetation dominates", "evidence": [{"type": "image_ref", "description": "location mock"}], "confidence": 0.82, "_latency_ms": 11}

        r = client.post("/api/query", data={"query": "Describe land cover", "input_mode": "single", "location_query": "Bengaluru, India"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["execution_trace"]["task"] in ("vqa",)
        assert body["execution_trace"]["parameters"].get("location_resolved") is True
        assert body["execution_trace"]["parameters"].get("location_query") == "Bengaluru, India"
        # Resolved images preview should be present for viewer
        assert body.get("resolved_images") is not None
        assert len(body["resolved_images"]) == 1
        assert body["resolved_images"][0]["preview_b64"].startswith("data:image/png;base64,")
        mock_geo.assert_called_once()
        mock_fetch.assert_called_once()


def test_coordinates_direct_bypasses_geocode():
    client = _client()
    png = _png_bytes()
    with patch("backend.services.geocode.geocode_place") as mock_geo, \
         patch("backend.services.imagery_fetch.fetch_imagery_for_location") as mock_fetch, \
         patch("backend.registry.predict") as mock_predict:
        mock_fetch.return_value = ([("loc.png", png)], [{"scene_id": "S1", "collection": "sentinel-2-l2a", "lat": 12.97, "lon": 77.59}])
        mock_predict.return_value = {"answer": "ok", "evidence": [], "confidence": 0.5, "_latency_ms": 5}

        r = client.post("/api/query", data={"query": "Describe", "input_mode": "single", "lat": "12.97", "lon": "77.59"})
        assert r.status_code == 200
        mock_geo.assert_not_called()
        # Lat/lon path uses coordinates in trace
        assert r.json()["execution_trace"]["parameters"]["coordinates"]["lat"] == 12.97


def test_location_not_found_returns_422():
    client = _client()
    with patch("backend.services.geocode.geocode_place") as mock_geo:
        from fastapi import HTTPException
        mock_geo.side_effect = HTTPException(status_code=422, detail="Location not found: 'Atlantis'")
        r = client.post("/api/query", data={"query": "Describe", "input_mode": "single", "location_query": "Atlantis"})
        assert r.status_code == 422
        assert "not found" in r.json()["detail"].lower()


def test_upload_still_works_after_location_feature():
    client = _client()
    png = _png_bytes()
    with patch("backend.registry.predict") as mock_predict:
        mock_predict.return_value = {"answer": "upload ok", "evidence": [], "confidence": 0.77, "_latency_ms": 9}
        r = client.post("/api/query", data={"query": "Describe", "input_mode": "single"}, files=[("images", ("t.png", png, "image/png"))])
        assert r.status_code == 200
        assert r.json()["answer"] == "upload ok"
        # No location trace when using upload
        assert r.json()["execution_trace"]["parameters"].get("location_resolved") is None


def test_bi_temporal_location_fetches_two_dates():
    client = _client()
    png = _png_bytes()
    with patch("backend.services.geocode.geocode_place") as mock_geo, \
         patch("backend.services.imagery_fetch.fetch_imagery_for_location") as mock_fetch, \
         patch("backend.registry.predict") as mock_predict:
        mock_geo.return_value = {"lat": 12.97, "lon": 77.59, "display_name": "Bengaluru"}
        mock_fetch.return_value = ([("T1.png", png), ("T2.png", png)], [{"scene_id": "S1", "display_name": "Bengaluru"}, {"scene_id": "S2", "display_name": "Bengaluru"}])
        mock_predict.return_value = {"answer": "change", "evidence": [{"type": "overlay", "description": "change"}], "confidence": 0.71, "_latency_ms": 12}

        r = client.post("/api/query", data={"query": "What changed?", "input_mode": "bi-temporal", "location_query": "Bengaluru"})
        assert r.status_code == 200
        assert r.json()["execution_trace"]["task"] == "change_detection"
        assert len(r.json()["resolved_images"]) == 2


def test_missing_both_images_and_location_returns_400():
    client = _client()
    r = client.post("/api/query", data={"query": "Describe", "input_mode": "single"})
    assert r.status_code == 400
    assert "images" in r.json()["detail"].lower() or "location" in r.json()["detail"].lower()
