"""FastAPI routes for SatQuery AI.

POST /query — accepts a QueryRequest, runs it through the controller, and
returns a QueryResponse with the full execution trace.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.controller import InputValidationError, handle_query
from backend.schemas.models import QueryRequest, QueryResponse

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query satellite imagery",
    description=(
        "Send a natural-language query along with one or more satellite images. "
        "The system validates input, classifies the task, routes to the "
        "appropriate specialist model, and returns an answer with a full "
        "execution trace."
    ),
)
async def query_satellite_imagery(request: QueryRequest) -> QueryResponse:
    """Handle a satellite imagery query.

    Returns:
        QueryResponse with answer text and mandatory execution trace.

    Raises:
        400: Invalid input (bad modality combo, unsupported format, wrong image count).
        422: Request body fails Pydantic validation (handled automatically by FastAPI).
        500: Internal error (e.g. no specialist registered for classified task).
    """
    try:
        response = handle_query(request)
    except InputValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input validation failed: {exc}",
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal routing error: {exc}",
        )
    return response
