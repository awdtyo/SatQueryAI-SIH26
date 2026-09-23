"""Selected Satellite Image Query Mode tests.

Covers the active-scene workflows:
1. VQA/describe routes to the VQA specialist using the SELECTED scene's real image.
2. NDVI band math (B04/B08) on the active scene via /api/query (unified trace).
3. NL cover query ("How much vegetation") -> spectral NDVI on the active scene.
4. Count receives the resolved scene image.
5. Scene switch uses the newly selected scene (scene_json changes context).
6. Cleared scene -> frontend-only concern; backend returns instructional trace asking for scene.
7. AOI is passed through and used to clip the analysis.
8. API accepts scene_json WITHOUT uploaded images (Selected Satellite Image mode).
"""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.main import app

BENGALURU_AOI = {
    "type": "Polygon",
    "coordinates": [
        [[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]
    ],
}

FAKE_SCENE_A = {
    "id": "S2A_scene_alpha",
    "collection": "sentinel-2-l2a",
    "datetime": "2026-06-15T05:00:00Z",
    "platform": "sentinel-2a",
    "cloud_cover": 3.0,
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

FAKE_SCENE_B = {**FAKE_SCENE_A, "id": "S2B_scene_beta", "platform": "sentinel-2b"}


def _fake_resolved_image(scene_id="S2A_scene_alpha"):

    return {
        "image": Image.new("RGB", (64, 64), (120, 90, 60)),
        "source": "bands",
        "scene_id": scene_id,
        "collection": "sentinel-2-l2a",
        "bands": ["B04", "B03", "B02"],
        "leaflet_bounds": [[12.85, 77.45], [13.05, 77.75]],
        "profile": {"crs": "EPSG:32643"},
        "trace_steps": [
            f"Active scene selected: {scene_id}",
            "Bands retrieved B04/B03/B02",
        ],
        "latency_ms": 1,
    }


def _scene_json(scene: dict) -> str:
    return json.dumps(scene)


# --- 1. VQA uses the selected scene image + unified trace ---


def test_scene_query_vqa_uses_selected_scene_image():
    client = TestClient(app)
    fake_ans = {
        "answer": "Land cover: dense vegetation, scattered water bodies.",
        "evidence": [{"type": "image_ref", "description": "vqa", "image_index": 0}],
        "confidence": 0.87,
        "_latency_ms": 5,
    }
    with (
        patch("backend.registry.predict", return_value=fake_ans) as mock_predict,
        patch(
            "backend.scene.raster.resolve_scene_rgb",
            return_value=_fake_resolved_image(),
        ) as mock_resolve,
    ):
        r = client.post(
            "/api/query",
            data={
                "query": "Describe the land cover of the selected scene",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_A),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"] == fake_ans["answer"]
        assert body["execution_trace"]["task"] == "vqa"
        # The specialist got the REAL resolved scene image (1 PIL image)
        args, _ = mock_predict.call_args
        assert len(args[0]) == 1
        assert isinstance(args[0][0], Image.Image)
        assert mock_resolve.called
        # Scene context is first-class in the trace
        assert body["scene_context"]["scene_id"] == "S2A_scene_alpha"
        assert body["scene_context"]["aoi"] == BENGALURU_AOI
        assert (
            body["execution_trace"]["parameters"]["scene_context"]["scene_id"]
            == "S2A_scene_alpha"
        )
        # Provenance evidence appended about the resolved image asset
        assert any(
            "S2A_scene_alpha" in e.get("description", "") for e in body["evidence"]
        )


# --- 2. NDVI band math on the active scene via unified /api/query ---


def test_scene_query_ndvi_spectral():
    client = TestClient(app)
    fake_spectral = {
        "answer": "- **NDVI** calculated for **S2A_scene_alpha**",
        "evidence": [
            {"type": "overlay", "description": "NDVI raster overlay", "image_index": 0}
        ],
        "confidence": 0.85,
        "_latency_ms": 3,
        "_spectral": {
            "index": "NDVI",
            "scene_id": "S2A_scene_alpha",
            "required_bands": ["B04", "B08"],
            "preview_b64": "data:image/png;base64,abc",
            "bounds": [[12.85, 77.45], [13.05, 77.75]],
            "stats": {"mean": 0.4, "valid_pct": 99.0},
            "cloud_applied": True,
        },
        "_structured": {"bullets": ["- **NDVI** calculated"], "chart": []},
        "_chart": [],
        "_chart_type": "none",
        "_stub": False,
    }
    with patch("backend.registry.predict", return_value=fake_spectral) as mock_predict:
        r = client.post(
            "/api/query",
            data={
                "query": "Calculate NDVI for the selected scene",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_A),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["execution_trace"]["task"] == "spectral_index"
        assert body["execution_trace"]["parameters"]["index"] == "NDVI"
        # The raster payload (preview_b64 -> map overlay) is carried in `analysis`
        assert body["analysis"]["type"] == "spectral_index"
        assert body["analysis"]["preview_b64"] == "data:image/png;base64,abc"
        assert body["analysis"]["index"] == "NDVI"
        assert body["scene_context"]["scene_id"] == "S2A_scene_alpha"
        # Spectral agent invoked with the scene + AOI JSON
        call_query = mock_predict.call_args.args[1]
        payload = json.loads(call_query)
        assert payload["index"] == "NDVI"
        assert payload["scene"]["id"] == "S2A_scene_alpha"
        assert payload["aoi"] == BENGALURU_AOI


# --- 3. NL cover query routes to spectral NDVI with the active scene ---


def test_scene_query_nl_vegetation_routes_to_spectral():
    client = TestClient(app)
    fake_spectral = {
        "answer": "- **NDVI** calculated",
        "evidence": [],
        "confidence": 0.85,
        "_latency_ms": 3,
        "_spectral": {
            "index": "NDVI",
            "scene_id": "S2A_scene_alpha",
            "required_bands": ["B04", "B08"],
            "preview_b64": "data:image/png;base64,abc",
            "bounds": None,
            "stats": {"mean": 0.4, "valid_pct": 99.0},
            "cloud_applied": True,
        },
        "_structured": None,
        "_chart": None,
        "_chart_type": None,
        "_stub": False,
    }
    with patch("backend.registry.predict", return_value=fake_spectral) as mock_predict:
        r = client.post(
            "/api/query",
            data={
                "query": "How much vegetation is present?",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_A),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["execution_trace"]["task"] == "spectral_index"
        assert body["execution_trace"]["models_used"][0]["role"] == "spectral_index"
        payload = json.loads(mock_predict.call_args.args[1])
        assert payload["index"] == "NDVI"
        # AOI clipped analysis
        assert payload["aoi"] == BENGALURU_AOI


# --- 4. Count receives the resolved scene image ---


def test_scene_query_count_receives_scene_image():
    client = TestClient(app)
    fake_count = {
        "answer": "**12 vehicles** counted in the selected scene AOI.",
        "evidence": [
            {
                "type": "bounding_box",
                "description": "vehicle bbox",
                "coordinates": [[77.5, 12.9], [77.51, 12.91]],
                "image_index": 0,
            }
        ],
        "confidence": 0.9,
        "_latency_ms": 6,
        "_structured": {
            "bullets": ["**12 vehicles** counted"],
            "chart": [{"label": "vehicles", "value": 12}],
        },
        "_chart": [{"label": "vehicles", "value": 12}],
        "_chart_type": "count",
    }
    with (
        patch("backend.registry.predict", return_value=fake_count) as mock_predict,
        patch(
            "backend.scene.raster.resolve_scene_rgb",
            return_value=_fake_resolved_image("S2B_scene_beta"),
        ),
    ):
        r = client.post(
            "/api/query",
            data={
                "query": "How many vehicles are in the selected scene?",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_B),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["execution_trace"]["task"] == "count"
        assert body["chart_type"] == "count"
        args, _ = mock_predict.call_args
        # YOLO received the scene's real RGB image (1 image), not a user upload
        assert len(args[0]) == 1
        assert isinstance(args[0][0], Image.Image)
        # Scene context carried for the SWITCHED scene (B)
        assert body["scene_context"]["scene_id"] == "S2B_scene_beta"
        assert body["analysis"]["scene_id"] == "S2B_scene_beta"
        assert body["analysis"]["source"] == "bands"


# --- 5. Scene switch: a different scene_json updates the scene context ---


def test_scene_query_scene_switch_uses_new_scene():
    client = TestClient(app)
    fake_ans = {
        "answer": "Mocked.",
        "evidence": [],
        "confidence": 0.5,
        "_latency_ms": 2,
    }
    with (
        patch("backend.registry.predict", return_value=fake_ans),
        patch(
            "backend.scene.raster.resolve_scene_rgb",
            return_value=_fake_resolved_image("S2B_scene_beta"),
        ),
    ):
        r = client.post(
            "/api/query",
            data={
                "query": "Describe this scene",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_B),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # After switching footprints the NEW scene (beta) is what gets analyzed
        assert body["scene_context"]["scene_id"] == "S2B_scene_beta"
        assert body["analysis"]["scene_id"] == "S2B_scene_beta"


# --- 6. No scene -> controller returns instructional (needs a selected scene) ---


def test_scene_query_missing_scene_is_instructional():
    client = TestClient(app)
    # No scene_json and no images -> API 400 (mirrors existing missing-image guard when no scene)
    r = client.post(
        "/api/query", data={"query": "Describe the scene", "input_mode": "single"}
    )
    assert r.status_code == 400


# --- 7. AOI restricts analysis (propagation) ---


def test_scene_query_aoi_restricts_analysis():
    client = TestClient(app)
    small_aoi = {
        "type": "Polygon",
        "coordinates": [
            [[77.5, 12.9], [77.55, 12.9], [77.55, 12.95], [77.5, 12.95], [77.5, 12.9]]
        ],
    }
    fake_ans = {
        "answer": "Mocked.",
        "evidence": [],
        "confidence": 0.5,
        "_latency_ms": 2,
    }
    with (
        patch("backend.registry.predict", return_value=fake_ans),
        patch(
            "backend.scene.raster.resolve_scene_rgb",
            return_value=_fake_resolved_image(),
        ) as mock_resolve,
    ):
        r = client.post(
            "/api/query",
            data={
                "query": "Count the fields",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_A),
                "aoi_json": json.dumps(small_aoi),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # AOI is in the scene context + trace parameters + passed to the resolver
        assert body["scene_context"]["aoi"] == small_aoi
        assert (
            body["execution_trace"]["parameters"]["scene_context"]["aoi"] == small_aoi
        )
        _, kwargs = mock_resolve.call_args
        assert kwargs["aoi"] == small_aoi


# --- 8. NL water query -> spectral NDWI with active scene ---


def test_scene_query_nl_water_routes_to_ndwi():
    client = TestClient(app)
    fake_spectral = {
        "answer": "- **NDWI** calculated",
        "evidence": [],
        "confidence": 0.85,
        "_latency_ms": 3,
        "_spectral": {
            "index": "NDWI",
            "scene_id": "S2A_scene_alpha",
            "required_bands": ["B03", "B08"],
            "preview_b64": "data:image/png;base64,wtr",
            "bounds": None,
            "stats": {"mean": 0.2, "valid_pct": 95.0},
            "cloud_applied": True,
        },
        "_structured": None,
        "_chart": None,
        "_chart_type": None,
        "_stub": False,
    }
    with patch("backend.registry.predict", return_value=fake_spectral) as mock_predict:
        r = client.post(
            "/api/query",
            data={
                "query": "Are there any water bodies in the selected scene?",
                "input_mode": "single",
                "scene_json": _scene_json(FAKE_SCENE_A),
                "aoi_json": json.dumps(BENGALURU_AOI),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["execution_trace"]["task"] == "spectral_index"
        payload = json.loads(mock_predict.call_args.args[1])
        assert payload["index"] == "NDWI"
        assert payload["aoi"] == BENGALURU_AOI


# --- Schema: QueryResponse exposes scene_context + analysis (contract) ---


def test_query_response_schema_has_scene_fields():
    from backend.schemas import QueryResponse

    fields = set(QueryResponse.model_fields.keys())
    assert "scene_context" in fields
    assert "analysis" in fields
    # Backward compatible — existing responses (no scene) still construct fine
    resp = QueryResponse(
        answer="x",
        confidence=0.5,
        execution_trace={
            "task": "vqa",
            "models_used": [],
            "parameters": {},
            "confidence": 0.5,
            "evidence_refs": [],
            "total_latency_ms": 0,
        },
        evidence=[],
    )
    assert resp.scene_context is None
    assert resp.analysis is None
