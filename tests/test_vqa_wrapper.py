"""VQA wrapper tests — mocked model, no 2B download or GPU needed."""

import sys
import types
from unittest.mock import MagicMock, patch

from PIL import Image

# Minimal torch stub if real torch not installed (CI)
try:
    import torch  # type: ignore
except ImportError:  # pragma: no cover
    torch = types.ModuleType("torch")  # type: ignore
    torch.device = lambda x: x  # type: ignore
    class _NoGrad:
        def __enter__(self): return None
        def __exit__(self, *a): return False
    torch.no_grad = lambda: _NoGrad()  # type: ignore
    torch.cuda = types.SimpleNamespace(is_available=lambda: False, get_device_name=lambda _: "cpu", memory_allocated=lambda: 0)  # type: ignore
    torch.float16 = "float16"  # type: ignore
    # Fake Tensor type for isinstance checks — just a marker
    class _FakeTensor:  # type: ignore
        pass
    torch.Tensor = _FakeTensor  # type: ignore
    sys.modules["torch"] = torch  # type: ignore
    try:
        import backend.models.vqa as _vqa
        if getattr(_vqa, "torch", None) is None:
            _vqa.torch = torch  # type: ignore
    except Exception:
        pass


def _dummy_image():
    return Image.new("RGB", (224, 224), color=(80, 120, 80))


class _SimpleTensor:
    """Minimal tensor-like for tests — supports .shape, .to(), and indexing."""

    def __init__(self, data):
        # data is list or list of lists
        self._data = data
        if isinstance(data, list) and data and isinstance(data[0], list):
            self.shape = [len(data), len(data[0])]
            self._is_2d = True
        else:
            self.shape = [1, len(data) if isinstance(data, list) else 1]
            self._is_2d = False

    def __getitem__(self, key):
        if self._is_2d:
            if isinstance(key, int):
                # return 1D row tensor
                return _SimpleTensor(self._data[key])
            if isinstance(key, slice):
                return _SimpleTensor(self._data[key])
        else:
            # 1D
            if isinstance(key, slice):
                return _SimpleTensor(self._data[key])
            return self._data[key]

    def to(self, *_, **__):
        return self

    def __len__(self):
        return len(self._data)


def test_predict_returns_expected_shape_with_mocked_model():
    """Mock _model and _processor so predict() runs without loading 2B weights."""
    from backend.models import vqa as vqa_mod

    fake_processor = MagicMock()
    fake_processor.apply_chat_template.return_value = "<chat>Describe</chat>"
    fake_processor.decode.return_value = "This image shows forest and arable land."

    fake_inputs = {
        "input_ids": _SimpleTensor([[1, 2, 3, 4, 5]]),
        "attention_mask": _SimpleTensor([[1, 1, 1, 1, 1]]),
    }
    fake_processor.return_value = fake_inputs
    fake_processor.__call__ = MagicMock(return_value=fake_inputs)

    fake_model = MagicMock()
    fake_model.device = "cpu"
    mock_param = MagicMock()
    mock_param.device = "cpu"
    fake_model.parameters.return_value = iter([mock_param])
    fake_model.generate.return_value = _SimpleTensor([[1, 2, 3, 4, 5, 101, 102, 103]])
    fake_model.eval.return_value = None

    with patch.object(vqa_mod, "_model", fake_model), patch.object(vqa_mod, "_processor", fake_processor), patch.object(
        vqa_mod, "_is_real", True
    ), patch.object(vqa_mod, "_load_attempted", True), patch.object(vqa_mod, "_load_error", None):
        with patch.object(vqa_mod, "_ensure_loaded", lambda: None):
            result = vqa_mod.predict([_dummy_image()], "Describe the land cover", task="vqa")

    assert "answer" in result
    assert "evidence" in result
    assert "confidence" in result
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0
    assert isinstance(result["evidence"], list)
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert "[STUB]" not in result["answer"]


def test_coerce_images_accepts_pil_and_list():
    from backend.models.vqa import _coerce_images

    img = _dummy_image()
    assert len(_coerce_images(img)) == 1
    assert len(_coerce_images([img, img])) == 2
    assert len(_coerce_images([img])) == 1


def test_coerce_images_rejects_empty():
    from backend.models.vqa import _coerce_images

    import pytest

    with pytest.raises(ValueError):
        _coerce_images([])
    with pytest.raises(ValueError):
        _coerce_images(None)


def test_predict_empty_query_raises():
    from backend.models import vqa as vqa_mod

    fake_model = MagicMock()
    fake_processor = MagicMock()
    with patch.object(vqa_mod, "_model", fake_model), patch.object(vqa_mod, "_processor", fake_processor), patch.object(
        vqa_mod, "_is_real", True
    ), patch.object(vqa_mod, "_load_attempted", True), patch.object(vqa_mod, "_ensure_loaded", lambda: None):
        import pytest

        with pytest.raises(ValueError):
            vqa_mod.predict([_dummy_image()], "", task="vqa")
        with pytest.raises(ValueError):
            vqa_mod.predict([_dummy_image()], "   ", task="vqa")


def test_get_model_info_shape():
    from backend.models import vqa as vqa_mod

    with patch.object(vqa_mod, "_load_attempted", True), patch.object(vqa_mod, "_is_real", False), patch.object(
        vqa_mod, "_load_error", "mock error for test"
    ), patch.object(vqa_mod, "_model", None):
        info = vqa_mod.get_model_info()
        assert "base_model" in info
        assert "adapter_path" in info
        assert "is_real" in info
        assert info["is_real"] is False
