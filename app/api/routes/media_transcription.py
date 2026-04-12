"""
ChronoFlow — /api/media-transcription routes
"""

from fastapi import APIRouter, HTTPException
from typing import List

from app.api.schema.schemas import (
    PipelineRunRequest, PipelineRunResponse, PipelineStatusResponse
)
from app.api.services import pipeline_service
from app.api.services import db_pipeline_service
from app.api.schema.schemas import (
    CreateMediaTranscriptionJobRequest,
    MediaTranscriptionJobResponse,
    WhisperWebhookRequest,
)
from app.api.services.media_transcription_service import (
    create_media_transcription_job,
    complete_media_transcription_job,
    list_media_transcription_jobs,
)


router = APIRouter()


@router.post(
    "/{meeting_id}",
    response_model=MediaTranscriptionJobResponse,
    summary="Submit a meeting media file for Whisper transcription",
)
def create_transcription_job(meeting_id: str, payload: CreateMediaTranscriptionJobRequest):
    try:
        job = create_media_transcription_job(meeting_id=meeting_id, filename=payload.filename)
        return MediaTranscriptionJobResponse(
            id=job.id,
            meeting_id=job.meeting_id,
            source_filename=job.source_filename,
            source_file_type=job.source_file_type,
            provider=job.provider,
            external_job_id=job.external_job_id,
            status=job.status.value,
            created_at=job.created_at,
            completed_at=job.completed_at,
            transcript_text=job.transcript_text,
            error=job.error,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get(
    "/{meeting_id}",
    response_model=list[MediaTranscriptionJobResponse],
    summary="List media transcription jobs for a meeting",
)
def get_transcription_jobs(meeting_id: str):
    try:
        jobs = list_media_transcription_jobs(meeting_id=meeting_id)
        return [
            MediaTranscriptionJobResponse(
                id=job.id,
                meeting_id=job.meeting_id,
                source_filename=job.source_filename,
                source_file_type=job.source_file_type,
                provider=job.provider,
                external_job_id=job.external_job_id,
                status=job.status.value,
                created_at=job.created_at,
                completed_at=job.completed_at,
                transcript_text=job.transcript_text,
                error=job.error,
            )
            for job in jobs
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post(
    "/webhooks/whisper",
    summary="Receive Whisper transcription completion webhook",
)
def whisper_webhook(payload: WhisperWebhookRequest):
    try:
        job = complete_media_transcription_job(
            external_job_id=payload.external_job_id,
            callback_token=payload.callback_token,
            status=payload.status,
            transcript_text=payload.transcript_text,
            raw_response=payload.raw_response,
            error=payload.error,
        )
        return {
            "ok": True,
            "job_id": job.id,
            "status": job.status.value,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

        