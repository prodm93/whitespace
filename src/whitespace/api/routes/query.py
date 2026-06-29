import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from whitespace.api.models import QueryRequest, QueryResponse
from whitespace.middleware.auth import get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.orchestration.pipeline import Pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def graph_query(
    body: QueryRequest,
    request: Request,
    user=Depends(get_current_user),
    _usage=Depends(check_usage),
) -> QueryResponse:
    """Graph-grounded Q&A — runs synchronously (fast read-only traversal)."""
    logger.info("Query from user=%s: %.80s", user.user_id, body.query)
    pipeline: Pipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline not initialised — run an ingest first",
        )
    answer = await pipeline.query(body.query)
    return QueryResponse(answer=answer)
