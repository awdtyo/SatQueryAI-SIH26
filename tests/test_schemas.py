"""Tests for Pydantic schema validation.

Covers:
    - QueryRequest: rejects empty queries, too-long queries, missing fields
    - ModalityConfig: rejects wrong image count for modality type
    - InputImage: rejects invalid formats
    - BoundingBox: rejects invalid coordinates
    - EvidenceItem: validates evidence types
"""

import pytest
from pydantic import ValidationError

from backend.schemas.models import (
    BoundingBox,
    EvidenceItem,
    InputImage,
    InputModality,
    ModalityConfig,
    QueryRequest,
    TaskType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _single_optical() -> ModalityConfig:
    return ModalityConfig(
        type=InputModality.single,
        images=[
            InputImage(data="fake_base64", format="png", bands=3, modality="optical")
        ],
    )


def _optical_sar_pair() -> ModalityConfig:
    return ModalityConfig(
        type=InputModality.optical_sar_pair,
        images=[
            InputImage(data="opt", format="geotiff", bands=4, modality="optical"),
            InputImage(data="sar", format="geotiff", bands=1, modality="sar"),
        ],
    )


def _bi_temporal() -> ModalityConfig:
    return ModalityConfig(
        type=InputModality.bi_temporal,
        images=[
            InputImage(data="t1", format="geotiff", bands=4, modality="optical"),
            InputImage(data="t2", format="geotiff", bands=4, modality="optical"),
        ],
    )


# ---------------------------------------------------------------------------
# QueryRequest validation
# ---------------------------------------------------------------------------


class TestQueryRequest:
    def test_valid_single(self) -> None:
        req = QueryRequest(query="What is in this image?", modality=_single_optical())
        assert req.query == "What is in this image?"

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(query="", modality=_single_optical())

    def test_whitespace_only_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(query="   ", modality=_single_optical())

    def test_long_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 1025, modality=_single_optical())


# ---------------------------------------------------------------------------
# ModalityConfig validation
# ---------------------------------------------------------------------------


class TestModalityConfig:
    def test_single_with_one_image(self) -> None:
        mc = ModalityConfig(
            type=InputModality.single,
            images=[InputImage(data="img", format="png", modality="optical")],
        )
        assert len(mc.images) == 1

    def test_single_with_two_images_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModalityConfig(
                type=InputModality.single,
                images=[
                    InputImage(data="a", format="png", modality="optical"),
                    InputImage(data="b", format="png", modality="optical"),
                ],
            )

    def test_pair_requires_two_images(self) -> None:
        with pytest.raises(ValidationError):
            ModalityConfig(
                type=InputModality.optical_sar_pair,
                images=[InputImage(data="a", format="png", modality="optical")],
            )

    def test_pair_with_two_images_allowed_at_schema_level(self) -> None:
        # Modality-combination validity (one optical + one SAR) is enforced by
        # the controller's validate_input, not the schema (see AGENTS.md).
        mc = ModalityConfig(
            type=InputModality.optical_sar_pair,
            images=[
                InputImage(data="a", format="png", modality="optical"),
                InputImage(data="b", format="png", modality="optical"),
            ],
        )
        assert len(mc.images) == 2

    def test_pair_with_valid_modalities(self) -> None:
        mc = _optical_sar_pair()
        assert mc.type == InputModality.optical_sar_pair

    def test_bi_temporal_requires_two_images(self) -> None:
        with pytest.raises(ValidationError):
            ModalityConfig(
                type=InputModality.bi_temporal,
                images=[InputImage(data="a", format="geotiff", modality="optical")],
            )

    def test_bi_temporal_same_modality(self) -> None:
        mc = _bi_temporal()
        assert mc.type == InputModality.bi_temporal

    def test_bi_temporal_different_modalities_allowed_at_schema_level(self) -> None:
        # Same-modality requirement enforced by controller, not schema.
        mc = ModalityConfig(
            type=InputModality.bi_temporal,
            images=[
                InputImage(data="a", format="geotiff", modality="optical"),
                InputImage(data="b", format="geotiff", modality="sar"),
            ],
        )
        assert len(mc.images) == 2


# ---------------------------------------------------------------------------
# InputImage validation
# ---------------------------------------------------------------------------


class TestInputImage:
    def test_valid_geotiff(self) -> None:
        img = InputImage(
            data="data", format="geotiff", bands=4, modality="multispectral"
        )
        assert img.format == "geotiff"

    def test_format_is_free_string(self) -> None:
        """Format is a plain string; allowed set is enforced by the controller."""
        img = InputImage(data="data", format="bmp", modality="optical")
        assert img.format == "bmp"

    def test_zero_bands_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InputImage(data="data", format="png", bands=0, modality="optical")

    def test_too_many_bands_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InputImage(data="data", format="png", bands=65, modality="optical")


# ---------------------------------------------------------------------------
# BoundingBox validation
# ---------------------------------------------------------------------------


class TestBoundingBox:
    def test_valid_bbox(self) -> None:
        bb = BoundingBox(x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8)
        assert bb.x_min == 0.1

    def test_inverted_x_rejected(self) -> None:
        with pytest.raises(ValueError, match="x_min"):
            BoundingBox(x_min=0.9, y_min=0.1, x_max=0.1, y_max=0.9)

    def test_inverted_y_rejected(self) -> None:
        with pytest.raises(ValueError, match="y_min"):
            BoundingBox(x_min=0.1, y_min=0.9, x_max=0.9, y_max=0.1)

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox(x_min=-0.1, y_min=0.0, x_max=0.5, y_max=0.5)


# ---------------------------------------------------------------------------
# EvidenceItem validation
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_text_evidence(self) -> None:
        e = EvidenceItem(type="text", text="Found a building", confidence=0.9)
        assert e.type == "text"
        assert e.bbox is None

    def test_bbox_evidence(self) -> None:
        e = EvidenceItem(
            type="bbox",
            text="Building",
            bbox=BoundingBox(x_min=0.1, y_min=0.1, x_max=0.5, y_max=0.5),
            confidence=0.85,
        )
        assert e.bbox is not None

    def test_change_mask_evidence(self) -> None:
        e = EvidenceItem(type="change_mask", change_mask_ref="/tmp/mask.tif")
        assert e.change_mask_ref == "/tmp/mask.tif"

    def test_caption_evidence(self) -> None:
        e = EvidenceItem(type="caption", text="An aerial view of a forest")
        assert e.type == "caption"


# ---------------------------------------------------------------------------
# ExecutionTrace validation
# ---------------------------------------------------------------------------


class TestExecutionTrace:
    def test_valid_trace(self) -> None:
        from backend.schemas.models import ExecutionTrace

        trace = ExecutionTrace(
            task=TaskType.vqa,
            selected_models=["vqa_stub"],
            confidence=0.8,
            evidence=[EvidenceItem(type="text", text="test", confidence=0.8)],
        )
        assert trace.task == TaskType.vqa
        assert len(trace.evidence) == 1

    def test_empty_selected_models_rejected(self) -> None:
        from backend.schemas.models import ExecutionTrace

        with pytest.raises(ValidationError):
            ExecutionTrace(
                task=TaskType.vqa,
                selected_models=[],
                confidence=0.8,
            )

    def test_confidence_out_of_range_rejected(self) -> None:
        from backend.schemas.models import ExecutionTrace

        with pytest.raises(ValidationError):
            ExecutionTrace(
                task=TaskType.vqa,
                selected_models=["vqa_stub"],
                confidence=1.5,
            )
