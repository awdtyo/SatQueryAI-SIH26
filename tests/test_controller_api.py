"""Controller validation + API /query tests (mocked specialist, no model load)."""

import io
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app


def _png_bytes(size=(224, 224), color=(100, 150, 100)):
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_client():
    return TestClient(app)


def test_health_endpoint():
    client = _make_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "specialists" in data
    assert "base_model" in data
    assert "adapter_path" in data


def test_query_rejects_missing_image():
    client = _make_client()
    r = client.post("/api/query", data={"query": "Describe", "input_mode": "single"})
    # FastAPI will complain about missing images field or controller will 400
    assert r.status_code in (400, 422)


def test_query_rejects_wrong_image_count_for_mode():
    client = _make_client()
    png = _png_bytes()
    # single expects 1, we send 2
    r = client.post(
        "/api/query",
        data={"query": "Describe", "input_mode": "single"},
        files=[("images", ("a.png", png, "image/png")), ("images", ("b.png", png, "image/png"))],
    )
    assert r.status_code == 422
    assert "expects 1" in r.json()["detail"]


def test_query_rejects_unsupported_format():
    client = _make_client()
    png = _png_bytes()
    r = client.post(
        "/api/query",
        data={"query": "Describe", "input_mode": "single"},
        files=[("images", ("a.gif", png, "image/gif"))],
    )
    assert r.status_code == 422
    assert "unsupported format" in r.json()["detail"].lower()


def test_query_success_mocked_vqa():
    """Mock registry.predict so we don't need the 2B model; verify full trace shape."""
    client = _make_client()
    png = _png_bytes()

    fake_vqa = {"answer": "Mocked model answer: forest and water bodies visible.", "evidence": [{"type": "image_ref", "description": "mock", "image_index": 0}], "confidence": 0.81, "_latency_ms": 123}

    with patch("backend.registry.predict", return_value=fake_vqa) as mock:
        r = client.post(
            "/api/query",
            data={"query": "Describe the land cover", "input_mode": "single"},
            files=[("images", ("test.png", png, "image/png"))],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"] == fake_vqa["answer"]
        assert 0.0 <= body["confidence"] <= 1.0
        assert "execution_trace" in body
        trace = body["execution_trace"]
        assert trace["task"] in ("vqa", "captioning", "visual_question_answering")
        assert len(trace["models_used"]) == 1
        assert "evidence" in body
        assert len(body["evidence"]) >= 1
        # Confidence heuristic TODO is exposed via placeholder but valid
        mock.assert_called_once()


def test_query_bi_temporal_routes_to_change_stub():
    client = _make_client()
    png = _png_bytes()

    with patch("backend.registry.predict") as mock_predict:
        mock_predict.return_value = {"answer": "[STUB] change", "evidence": [{"type": "overlay", "description": "stub", "image_index": 1}], "confidence": 0.0, "_stub": True, "_latency_ms": 0}
        r = client.post(
            "/api/query",
            data={"query": "What changed?", "input_mode": "bi-temporal"},
            files=[("images", ("t1.png", png, "image/png")), ("images", ("t2.png", png, "image/png"))],
        )
        assert r.status_code == 200
        body = r.json()
        # bi-temporal + change keyword should route to change_detection
        assert body["execution_trace"]["task"] == "change_detection"
        # Should call change stub (we mocked registry.predict, so just check it was called)
        assert mock_predict.called
        # Check that the task passed to predict was change_detection
        _, kwargs = mock_predict.call_args
        # call args are (images, query, task)
        args, kwargs = mock_predict.call_args
        assert args[2] == "change_detection" or kwargs.get("task") == "change_detection"
