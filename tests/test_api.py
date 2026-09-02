"""Integration tests for the FastAPI /query endpoint.

Uses httpx.AsyncClient with the real FastAPI app to test the full HTTP round-trip.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _single_optical_payload() -> dict:
    return {
        "query": "What is in this image?",
        "modality": {
            "type": "single",
            "images": [
                {
                    "data": "fake_base64",
                    "format": "png",
                    "bands": 3,
                    "modality": "optical",
                }
            ],
        },
    }


def _bi_temporal_payload() -> dict:
    return {
        "query": "What has changed?",
        "modality": {
            "type": "bi_temporal",
            "images": [
                {"data": "t1", "format": "geotiff", "bands": 4, "modality": "optical"},
                {"data": "t2", "format": "geotiff", "bands": 4, "modality": "optical"},
            ],
        },
    }


def _optical_sar_pair_payload() -> dict:
    return {
        "query": "Fuse SAR and optical",
        "modality": {
            "type": "optical_sar_pair",
            "images": [
                {"data": "opt", "format": "geotiff", "bands": 4, "modality": "optical"},
                {"data": "sar", "format": "geotiff", "bands": 1, "modality": "sar"},
            ],
        },
    }


@pytest.mark.asyncio
class TestQueryEndpoint:
    async def test_health_check(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_query_single_optical(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/query", json=_single_optical_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert "trace" in body
        assert body["trace"]["task"] == "vqa"
        assert body["trace"]["selected_models"] == ["vqa_stub"]

    async def test_query_bi_temporal(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/query", json=_bi_temporal_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["trace"]["task"] == "change_detection"

    async def test_query_optical_sar_pair(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/query", json=_optical_sar_pair_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["trace"]["task"] == "optical_sar_fusion"

    async def test_empty_query_rejected(self, client: AsyncClient) -> None:
        payload = _single_optical_payload()
        payload["query"] = ""
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 422  # Pydantic validation error

    async def test_invalid_modality_combo_rejected(self, client: AsyncClient) -> None:
        payload = {
            "query": "Compare these",
            "modality": {
                "type": "optical_sar_pair",
                "images": [
                    {
                        "data": "a",
                        "format": "geotiff",
                        "bands": 4,
                        "modality": "optical",
                    },
                    {
                        "data": "b",
                        "format": "geotiff",
                        "bands": 4,
                        "modality": "optical",
                    },
                ],
            },
        }
        resp = await client.post("/api/v1/query", json=payload)
        assert (
            resp.status_code == 400
        )  # controller's validate_input (AGENTS.md) rejects

    async def test_invalid_image_format_rejected(self, client: AsyncClient) -> None:
        payload = _single_optical_payload()
        payload["modality"]["images"][0]["format"] = "bmp"
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 400  # controller's validate_input rejects it

    async def test_change_query_with_single_image_rejected(self, client: AsyncClient) -> None:
        """Change-detection query with only one image must be rejected (400)."""
        payload = _single_optical_payload()
        payload["query"] = "What has changed?"
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 400
        assert "change_detection" in resp.json()["detail"]

    async def test_fusion_query_with_single_image_rejected(self, client: AsyncClient) -> None:
        """Optical-SAR fusion query with only one image must be rejected (400)."""
        payload = _single_optical_payload()
        payload["query"] = "Fuse SAR and optical data"
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 400
        assert "optical_sar_fusion" in resp.json()["detail"]

    async def test_missing_query_field_rejected(self, client: AsyncClient) -> None:
        payload = _single_optical_payload()
        del payload["query"]
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 422

    async def test_missing_modality_field_rejected(self, client: AsyncClient) -> None:
        payload = {"query": "hello"}
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 422
