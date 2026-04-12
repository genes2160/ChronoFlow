from fastapi import APIRouter, HTTPException

from app.api.schema.schemas import (
    PromptListResponse,
    PromptResponse,
    PromptCreateRequest,
    PromptUpdateRequest,
)
from app.api.services import prompt_service

router = APIRouter()


@router.get("", response_model=PromptListResponse)
async def list_all_prompts():
    rows = prompt_service.list_prompts()
    return {"items": rows}


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_one_prompt(prompt_id: int):
    row = prompt_service.get_prompt(prompt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return row


@router.post("", response_model=PromptResponse)
async def create_one_prompt(req: PromptCreateRequest):
    return prompt_service.create_prompt(req)


@router.patch("/{prompt_id}", response_model=PromptResponse)
async def update_one_prompt(prompt_id: int, req: PromptUpdateRequest):
    try:
        return prompt_service.update_prompt(prompt_id, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{prompt_id}/activate", response_model=PromptResponse)
async def activate_one_prompt(prompt_id: int):
    try:
        return prompt_service.activate_prompt(prompt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))