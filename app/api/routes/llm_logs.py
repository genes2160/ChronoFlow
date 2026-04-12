from fastapi import APIRouter, HTTPException, Query

from app.api.schema.schemas import (
    LLMRequestLogListResponse,
    LLMRequestLogSavedResponse,
    LLMRequestLogDetailResponse,
)
from app.api.services import llm_log_service

router = APIRouter()


@router.get("", response_model=LLMRequestLogListResponse)
async def list_logs(limit: int = Query(default=50, ge=1, le=200)):
    return {"items": llm_log_service.list_llm_logs(limit=limit)}


@router.get("/{log_id}", response_model=LLMRequestLogDetailResponse)
async def get_log(log_id: int):
    row = llm_log_service.get_llm_log_detail(log_id)
    if not row:
        raise HTTPException(status_code=404, detail="LLM log not found")
    return row