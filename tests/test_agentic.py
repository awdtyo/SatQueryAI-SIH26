"""Tests for new agentic architecture — SatelliteAsset, ingestion, planner, specialists, evidence, provenance."""
import io
import hashlib
from PIL import Image
from unittest.mock import patch

from backend.core.assets import SatelliteAsset
from backend.ingestion import ingest_uploaded_image, validate_upload
from backend.ingestion.raster import extract_raster_metadata
from backend.agents.planner import plan_query
from backend.agents.specialists.registry import get_specialist
from backend.agents.specialists.base import SpecialistResult
from backend.evidence import fuse_evidence, Evidence
from backend.provenance import build_provenance, build_execution_graph
from backend.session.store import get_session, set_assets, append_history


def _png_bytes(size=(64, 64), color=(100, 150, 100)):
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_satellite_asset_creation():
    asset = SatelliteAsset(source_type="upload", filename="test.png", format="png", width=64, height=64, channels=3)
    assert asset.asset_id
    assert asset.source_type == "upload"
    assert asset.width == 64
    assert asset.has_geospatial is False


def test_live_asset_creation_never_hallucinate():
    from backend.core.assets import asset_from_live_scene

    scene = {"id": "S2A_test", "datetime": "2026-06-15T10:00:00Z", "platform": "Sentinel-2A", "cloud_cover": 12.5, "bbox": [77, 12, 78, 13]}
    asset = asset_from_live_scene(scene)
    assert asset.source_type == "live"
    assert asset.sensor
    assert asset.crs == "EPSG:4326"
    # Upload should have unknown sensor
    img_bytes = _png_bytes()
    upload_asset = ingest_uploaded_image("test.png", img_bytes)
    assert upload_asset.sensor is None or upload_asset.crs is None  # never hallucinated as sentinel
    assert upload_asset.acquisition_time is None


def test_image_metadata_extraction():
    img_bytes = _png_bytes(size=(128, 64))
    asset = ingest_uploaded_image("photo.jpg", img_bytes)
    assert asset.width == 128
    assert asset.height == 64
    assert asset.format == "jpg"
    assert asset.channels == 3
    assert asset.image_hash is not None
    assert len(asset.image_hash) == 16


def test_upload_validation():
    img_bytes = _png_bytes()
    # Valid
    validate_upload("test.png", img_bytes, "image/png")
    # Invalid ext
    try:
        validate_upload("test.gif", img_bytes)
        assert False, "should raise"
    except ValueError as e:
        assert "Unsupported extension" in str(e)
    # Empty
    try:
        validate_upload("test.png", b"")
        assert False
    except ValueError:
        pass
    # Corrupt
    try:
        ingest_uploaded_image("bad.png", b"not an image")
        assert False
    except ValueError as e:
        assert "Corrupt" in str(e) or "Failed" in str(e)


def test_planner_routing_vqa():
    img_bytes = _png_bytes()
    asset = ingest_uploaded_image("test.png", img_bytes)
    plan = plan_query("What type of land cover is visible?", [asset])
    assert plan.intent == "vqa"
    assert any(s.specialist == "vqa" for s in plan.steps)


def test_planner_spectral_when_bands_missing():
    img_bytes = _png_bytes()
    asset = ingest_uploaded_image("test.png", img_bytes)  # RGB only
    plan = plan_query("How much vegetation is present?", [asset])
    # Planner should detect spectral intent and flag limitation
    assert "spectral" in plan.intent
    assert any("NIR band unavailable" in lim for lim in plan.limitations)


def test_planner_refuses_ndvi_when_nir_absent_via_specialist():
    img_bytes = _png_bytes()
    asset = ingest_uploaded_image("test.png", img_bytes)
    from backend.agents.specialists.spectral_spec import SpectralSpecialist

    spec = SpectralSpecialist()
    res = spec.run([asset], "Calculate NDVI for this image", index="NDVI")
    assert res.status == "unsupported"
    assert "NIR band unavailable" in res.answer
    assert res.confidence is None


def test_planner_two_image_change():
    img_bytes = _png_bytes()
    a1 = ingest_uploaded_image("a.png", img_bytes)
    a2 = ingest_uploaded_image("b.png", img_bytes)
    plan = plan_query("What changed between these two images?", [a1, a2])
    assert plan.intent == "change_detection"
    assert plan.requires_pair is True
    assert any(s.specialist == "change_detection" for s in plan.steps)


def test_specialist_registry():
    vqa = get_specialist("vqa")
    assert vqa.name == "vqa"
    spec = get_specialist("ndvi")
    assert spec.name == "spectral"
    ch = get_specialist("change_detection")
    assert ch.name == "change_detection"
    cnt = get_specialist("count")
    assert cnt.name == "counting"


def test_evidence_schema():
    ev = Evidence(type="derived_measurement", description="mean NDVI", metric="mean_ndvi", value=0.64, source="spectral")
    d = ev.to_dict()
    assert d["type"] == "derived_measurement"
    assert d["metric"] == "mean_ndvi"
    fused = fuse_evidence([[d]])
    assert fused["count"] == 1
    assert fused["agreement"] == "full"


def test_provenance_generation():
    img_bytes = _png_bytes()
    asset = ingest_uploaded_image("test.png", img_bytes)
    from backend.agents.planner import plan_query

    plan = plan_query("Describe", [asset])
    fused = fuse_evidence([[{"type": "image_ref", "description": "test"}]])
    prov = build_provenance("Describe", [asset], plan, [{"specialist": "vqa", "answer": "forest", "confidence": 0.8}], fused, "forest", None)
    assert prov.run_id
    assert prov.query == "Describe"
    assert len(prov.assets) == 1
    assert prov.answer == "forest"
    graph = build_execution_graph(prov)
    assert any(g["step"] == "INPUT" for g in graph)
    assert any(g["step"] == "ANSWER" for g in graph)


def test_execution_trace_via_controller_mocked():
    """Planner + controller trace generation (mocked VQA)"""
    img_bytes = _png_bytes()
    with patch("backend.registry.predict", return_value={"answer": "Mocked", "evidence": [{"type": "image_ref", "description": "mock", "image_index": 0}], "confidence": 0.9, "_latency_ms": 10}):
        from backend.controller import handle

        # Use handle directly (existing pipeline) — trace should be produced
        resp = handle(query="What is visible?", images=[("test.png", img_bytes)], input_mode="single")
        assert resp.execution_trace.task == "vqa"
        assert len(resp.execution_trace.models_used) >= 1
        assert resp.confidence == 0.9


def test_session_state():
    sid = "test-session-123"
    img_bytes = _png_bytes()
    asset = ingest_uploaded_image("test.png", img_bytes)
    set_assets(sid, [asset])
    sess = get_session(sid)
    assert len(sess["assets"]) == 1
    append_history(sid, "hello", "world")
    assert len(sess["history"]) == 1
    # Second query without upload should reuse session
    from backend.session.store import get_assets

    assets = get_assets(sid)
    assert len(assets) == 1
