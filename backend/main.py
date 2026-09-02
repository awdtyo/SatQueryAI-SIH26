"""SatQuery AI — FastAPI application entrypoint.

Run with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.api import router as query_router

app = FastAPI(
    title="SatQuery AI",
    description=(
        "Agentic vision-language assistant for querying remote-sensing "
        "satellite imagery via natural language."
    ),
    version="0.1.0",
)

app.include_router(query_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}
