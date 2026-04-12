"""
ChronoFlow — /api/pipeline routes
"""

from app.api.services.payload_simulation_service import simulate_summary_payload
from fastapi import APIRouter, HTTPException
from typing import List

from app.api.schema.schemas import (
    PipelineRunRequest, PipelineRunResponse, PipelineStatusResponse, SummaryPayloadSimulationRequest, SummaryPayloadSimulationResponse
)
from app.api.services import pipeline_service
from app.api.services import db_pipeline_service

router = APIRouter()

@router.get("/transcripts")
async def list_transcripts():
    # return await pipeline_service.get_transcripts()
    return await db_pipeline_service.get_transcripts()


@router.post("/run", response_model=PipelineRunResponse, summary="Trigger pipeline run")
async def run_pipeline(req: PipelineRunRequest):
    """
    Modes:
    - `organize` — move raw files into dated folders (runner.py)
    - `summarize` — generate LLM summaries (llm_runner.py)
    - `full` — organize then summarize sequentially
    """
    if req.mode == "organize":
        # return await pipeline_service.trigger_organize(force=req.force)
        return await db_pipeline_service.trigger_organize(force=req.force, target_date=req.target_date)
    elif req.mode == "summarize":
        # return await pipeline_service.trigger_summarize(target_date=req.target_date, file_paths=req.file_paths, target_file=req.file_path)
        return await db_pipeline_service.trigger_summarize(
            meeting_ids=req.meeting_ids,
            source_preference=req.source_preference or "caption"
        )
    elif req.mode == "full":
        # return await db_pipeline_service.trigger_full(target_date=req.target_date, file_paths=req.file_paths)
        return await pipeline_service.trigger_full(target_date=req.target_date, file_paths=req.file_paths)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {req.mode}")


@router.get("/jobs", response_model=List[PipelineStatusResponse], summary="List all pipeline jobs")
def list_jobs():
    return db_pipeline_service.list_jobs()
    # return pipeline_service.list_jobs()


@router.get("/jobs/{job_id}", response_model=PipelineStatusResponse, summary="Get job status")
def get_job(job_id: str):
    job = db_pipeline_service.get_job_status(job_id)
    # job = pipeline_service.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post(
    "/simulate-summary-payload",
    response_model=SummaryPayloadSimulationResponse,
    summary="Simulate summary payload without sending to LLM",
)
async def simulate_summary_payload_endpoint(req: SummaryPayloadSimulationRequest):
    try:
        return simulate_summary_payload(req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))