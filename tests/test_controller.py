"""Tests for the controller's task-classification routing logic.

Given a query string and input modality, does the controller pick the right
task type? Also tests input validation and end-to-end handle_query.
"""

import pytest

from backend.controller import (
    InputValidationError,
    classify_task,
    handle_query,
    validate_input,
    validate_task_modality_compatibility,
)
from backend.registry import get_specialist, list_all
from backend.schemas.models import (
    InputImage,
    InputModality,
    ModalityConfig,
    QueryRequest,
    TaskType,
)

# ---------------------------------------------------------------------------
# Helpers — standard modality configs used across tests
# ---------------------------------------------------------------------------


def _single_optical() -> ModalityConfig:
    return ModalityConfig(
        type=InputModality.single,
        images=[InputImage(data="fake", format="png", bands=3, modality="optical")],
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
# Registry sanity checks
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_stub_specialists_registered(self) -> None:
        all_specs = list_all()
        expected_tasks = {t.value for t in TaskType}
        assert set(all_specs.keys()) == expected_tasks

    def test_each_task_has_at_least_one_specialist(self) -> None:
        for task in TaskType:
            name, fn = get_specialist(task)
            assert callable(fn)
            assert len(name) > 0


# ---------------------------------------------------------------------------
# Task classification — keyword-based
# ---------------------------------------------------------------------------


class TestClassifyTask:
    # --- change detection keywords ---
    def test_change_keyword(self) -> None:
        assert (
            classify_task("What has changed between these images?", _bi_temporal())
            == TaskType.change_detection
        )

    def test_before_after_keyword(self) -> None:
        assert (
            classify_task("Compare before and after the flood", _bi_temporal())
            == TaskType.change_detection
        )

    def test_difference_keyword(self) -> None:
        assert (
            classify_task("Show me the difference", _bi_temporal())
            == TaskType.change_detection
        )

    # --- fusion keywords ---
    def test_fusion_keyword(self) -> None:
        assert (
            classify_task("Fuse the SAR and optical data", _optical_sar_pair())
            == TaskType.optical_sar_fusion
        )

    def test_combine_sar_keyword(self) -> None:
        assert (
            classify_task("Combine SAR with optical imagery", _optical_sar_pair())
            == TaskType.optical_sar_fusion
        )

    # --- grounding keywords ---
    def test_locate_keyword(self) -> None:
        assert (
            classify_task("Locate the buildings in this image", _single_optical())
            == TaskType.grounding
        )

    def test_where_is_keyword(self) -> None:
        assert (
            classify_task("Where is the river?", _single_optical())
            == TaskType.grounding
        )

    def test_find_keyword(self) -> None:
        assert (
            classify_task("Find the parking lot", _single_optical())
            == TaskType.grounding
        )

    # --- captioning keywords ---
    def test_describe_keyword(self) -> None:
        assert (
            classify_task("Describe this scene", _single_optical())
            == TaskType.captioning
        )

    def test_caption_keyword(self) -> None:
        assert (
            classify_task("Caption this satellite image", _single_optical())
            == TaskType.captioning
        )

    def test_overview_keyword(self) -> None:
        assert (
            classify_task("Give me an overview of this area", _single_optical())
            == TaskType.captioning
        )

    # --- VQA keywords ---
    def test_what_keyword(self) -> None:
        assert (
            classify_task("What type of land use is visible?", _single_optical())
            == TaskType.vqa
        )

    def test_how_many_keyword(self) -> None:
        assert (
            classify_task("How many buildings are there?", _single_optical())
            == TaskType.vqa
        )

    def test_is_there_keyword(self) -> None:
        assert (
            classify_task("Is there a road visible?", _single_optical()) == TaskType.vqa
        )

    def test_which_keyword(self) -> None:
        assert (
            classify_task("Which season was this image taken in?", _single_optical())
            == TaskType.vqa
        )

    # --- default fallback ---
    def test_unrecognised_query_defaults_to_vqa(self) -> None:
        assert classify_task("hello", _single_optical()) == TaskType.vqa


# ---------------------------------------------------------------------------
# Task classification — modality-implied defaults
# ---------------------------------------------------------------------------


class TestModalityDefaults:
    def test_optical_sar_pair_defaults_to_fusion(self) -> None:
        """No keywords but optical+SAR pair -> fusion."""
        assert (
            classify_task("analyse this", _optical_sar_pair())
            == TaskType.optical_sar_fusion
        )

    def test_bi_temporal_defaults_to_change_detection(self) -> None:
        """No keywords but bi-temporal -> change detection."""
        assert (
            classify_task("interpret the pair", _bi_temporal())
            == TaskType.change_detection
        )

    def test_single_optical_defaults_to_vqa(self) -> None:
        """Single optical with no keywords -> VQA."""
        assert classify_task("hello", _single_optical()) == TaskType.vqa


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_valid_single_passes(self) -> None:
        validate_input(_single_optical())

    def test_valid_pair_passes(self) -> None:
        validate_input(_optical_sar_pair())

    def test_invalid_format_rejected(self) -> None:
        mc = ModalityConfig(
            type=InputModality.single,
            images=[InputImage(data="x", format="bmp", modality="optical")],
        )
        with pytest.raises(InputValidationError, match="format"):
            validate_input(mc)

    def test_pair_with_two_opticals_rejected(self) -> None:
        mc = ModalityConfig(
            type=InputModality.optical_sar_pair,
            images=[
                InputImage(data="a", format="geotiff", modality="optical"),
                InputImage(data="b", format="geotiff", modality="optical"),
            ],
        )
        with pytest.raises(InputValidationError, match="optical.*sar"):
            validate_input(mc)

    def test_bi_temporal_with_mixed_modalities_rejected(self) -> None:
        mc = ModalityConfig(
            type=InputModality.bi_temporal,
            images=[
                InputImage(data="a", format="geotiff", modality="optical"),
                InputImage(data="b", format="geotiff", modality="sar"),
            ],
        )
        with pytest.raises(InputValidationError, match="same modality"):
            validate_input(mc)


# ---------------------------------------------------------------------------
# Task ↔ modality compatibility
# ---------------------------------------------------------------------------


class TestTaskModalityCompatibility:
    def test_change_detection_requires_bi_temporal(self) -> None:
        with pytest.raises(InputValidationError, match="change_detection"):
            validate_task_modality_compatibility(TaskType.change_detection, _single_optical())

    def test_change_detection_requires_bi_temporal_not_pair(self) -> None:
        with pytest.raises(InputValidationError, match="change_detection"):
            validate_task_modality_compatibility(
                TaskType.change_detection, _optical_sar_pair()
            )

    def test_change_detection_with_bi_temporal_passes(self) -> None:
        validate_task_modality_compatibility(TaskType.change_detection, _bi_temporal())

    def test_fusion_requires_optical_sar_pair(self) -> None:
        with pytest.raises(InputValidationError, match="optical_sar_fusion"):
            validate_task_modality_compatibility(
                TaskType.optical_sar_fusion, _single_optical()
            )

    def test_fusion_with_pair_passes(self) -> None:
        validate_task_modality_compatibility(
            TaskType.optical_sar_fusion, _optical_sar_pair()
        )

    def test_single_image_tasks_have_no_hard_constraint(self) -> None:
        # VQA / captioning / grounding don't impose a hard modality requirement.
        for task in (TaskType.vqa, TaskType.captioning, TaskType.grounding):
            validate_task_modality_compatibility(task, _single_optical())


# ---------------------------------------------------------------------------
# End-to-end handle_query
# ---------------------------------------------------------------------------


class TestHandleQuery:
    def test_vqa_end_to_end(self) -> None:
        req = QueryRequest(query="What is in this image?", modality=_single_optical())
        resp = handle_query(req)
        assert resp.answer.startswith("[VQA stub]")
        assert resp.trace.task == TaskType.vqa
        assert resp.trace.confidence > 0

    def test_change_detection_end_to_end(self) -> None:
        req = QueryRequest(query="What has changed?", modality=_bi_temporal())
        resp = handle_query(req)
        assert resp.trace.task == TaskType.change_detection
        assert resp.trace.selected_models == ["change_detection_stub"]

    def test_fusion_end_to_end(self) -> None:
        req = QueryRequest(query="Fuse SAR and optical", modality=_optical_sar_pair())
        resp = handle_query(req)
        assert resp.trace.task == TaskType.optical_sar_fusion
        assert resp.trace.selected_models == ["fusion_stub"]

    def test_grounding_end_to_end(self) -> None:
        req = QueryRequest(query="Locate the buildings", modality=_single_optical())
        resp = handle_query(req)
        assert resp.trace.task == TaskType.grounding
        assert len(resp.trace.evidence) > 0
        assert resp.trace.evidence[0].type == "bbox"

    def test_captioning_end_to_end(self) -> None:
        req = QueryRequest(query="Describe this scene", modality=_single_optical())
        resp = handle_query(req)
        assert resp.trace.task == TaskType.captioning
        assert resp.trace.selected_models == ["captioning_stub"]

    def test_invalid_input_raises(self) -> None:
        mc = ModalityConfig(
            type=InputModality.single,
            images=[InputImage(data="x", format="bmp", modality="optical")],
        )
        req = QueryRequest(query="What is here?", modality=mc)
        with pytest.raises(InputValidationError):
            handle_query(req)

    def test_change_query_with_single_image_rejected(self) -> None:
        """A change-detection query implies two images; reject single-image input."""
        req = QueryRequest(
            query="What has changed?",
            modality=_single_optical(),
        )
        with pytest.raises(InputValidationError, match="change_detection"):
            handle_query(req)

    def test_change_query_with_bi_temporal_accepted(self) -> None:
        req = QueryRequest(
            query="What has changed?",
            modality=_bi_temporal(),
        )
        resp = handle_query(req)
        assert resp.trace.task == TaskType.change_detection

    def test_fusion_query_with_single_image_rejected(self) -> None:
        """An optical-SAR fusion query implies a pair; reject single-image input."""
        req = QueryRequest(
            query="Fuse SAR and optical",
            modality=_single_optical(),
        )
        with pytest.raises(InputValidationError, match="optical_sar_fusion"):
            handle_query(req)
