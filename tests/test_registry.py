"""Registry wiring tests — no 2B model load, just interface checks."""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _dummy_image():
    return Image.new("RGB", (224, 224), color=(100, 150, 100))


def test_vqa_is_registered():
    from backend import registry

    for task in ["vqa", "captioning", "visual_question_answering", "describe"]:
        mod = registry.get_specialist(task)
        assert mod is not None
        assert hasattr(mod, "predict")
        assert hasattr(mod, "is_real")
        assert hasattr(mod, "get_model_info")


def test_stubs_are_registered():
    from backend import registry

    for task in ["grounding", "change_detection", "optical_sar_fusion"]:
        mod = registry.get_specialist(task)
        assert mod is not None
        assert mod.is_real() is False
        info = mod.get_model_info()
        assert info.get("is_real") is False


def test_unknown_task_raises():
    from backend import registry

    with pytest.raises(KeyError):
        registry.get_specialist("nonexistent_task_xyz")


def test_vqa_predict_interface_mocked():
    """Verify predict(image(s), query, task) -> {answer, evidence, confidence} shape without loading 2B."""
    from backend import registry

    fake_result = {"answer": "Forest and urban fabric visible.", "evidence": [{"type": "image_ref", "description": "mock"}], "confidence": 0.88}

    with patch("backend.models.vqa.predict", return_value=fake_result) as mock_predict:
        # Call via registry so we test the delegation path (controller -> registry -> specialist)
        result = registry.predict([_dummy_image()], "Describe land cover", "vqa")
        mock_predict.assert_called_once()
        assert result["answer"] == fake_result["answer"]
        assert "evidence" in result
        assert "confidence" in result
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


def test_grounding_stub_returns_stub_shape():
    from backend.models import grounding_specialist

    result = grounding_specialist.predict([_dummy_image()], "Where is the building?", "grounding")
    assert "answer" in result
    assert "[STUB]" in result["answer"]
    # Stub flag is stored as _stub (internal) — check either
    assert result.get("_stub") is True or result.get("is_stub") is True or result.get("confidence") == 0.0
    assert "evidence" in result
    assert "confidence" in result


def test_health_shape():
    from backend import registry

    health = registry.health()
    assert "registry" in health
    assert "vqa (real)" in health["registry"]
    assert "grounding (stub)" in health["registry"]
    # Each entry has is_real
    for info in health["registry"].values():
        assert "is_real" in info


def test_task_alias_via_config():
    # config maps "visual_question_answering" -> vqa etc.
    from backend import registry

    # Normalize should route alias to same specialist
    assert registry.get_specialist("visual_question_answering") is registry.get_specialist("vqa")
    assert registry.get_specialist("change") is registry.get_specialist("change_detection")
