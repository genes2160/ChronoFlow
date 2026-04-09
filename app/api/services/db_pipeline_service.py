# app/api/services/db_pipeline_service.py
"""
ChronoFlow — DB-backed pipeline service
Mirrors pipeline_service.py exactly. Same return types, same schemas.
Jobs persisted to DB instead of in-memory dict.
In-memory dict retained as a fast cache for the current process lifetime.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from llm_runner import run_llm_on_data
from sqlmodel import Session, select

from app.api.schema.schemas import (
    PipelineStatus, PipelineStatusResponse, PipelineRunResponse
)
from app.api.models.model import (
    Job, PipelineStatusEnum,
    Meeting, Summary, ParticipantScore,
    TranscriptTurn, Caption, MediaFile
)
from app.api.core.db import get_session
from app.api.core.db import engine

# Fast cache — avoids a DB hit on every status poll within the same process
_jobs: dict[str, PipelineStatusResponse] = {}


# ── Internal helpers ───────────────────────────────────────────────────────

def _to_schema(job: Job) -> PipelineStatusResponse:
    return PipelineStatusResponse(
        job_id=job.job_id,
        status=PipelineStatus(job.status.value),
        mode=job.mode,
        started_at=job.started_at,
        finished_at=job.finished_at,
        output=job.output,
        error=job.error,
        files_processed=job.files_processed,
    )


def _new_job(mode: str) -> PipelineStatusResponse:
    job_id = str(uuid.uuid4())[:8]

    # Write to DB immediately so it survives process restarts
    with Session(engine) as session:
        db_job = Job(
            job_id=job_id,
            mode=mode,
            status=PipelineStatusEnum.running,
            started_at=datetime.utcnow(),
            files_processed=0,
        )
        session.add(db_job)
        session.commit()
        session.refresh(db_job)
        schema = _to_schema(db_job)

    _jobs[job_id] = schema
    return schema


def _update_job(job_id: str, **kwargs) -> None:
    """Update both the in-memory cache and the DB row."""
    if job_id in _jobs:
        for k, v in kwargs.items():
            setattr(_jobs[job_id], k, v)

    with Session(engine) as session:
        db_job = session.exec(
            select(Job).where(Job.job_id == job_id)
        ).first()
        if not db_job:
            return
        for k, v in kwargs.items():
            # map schema field names to model field names
            if k == "status":
                db_job.status = PipelineStatusEnum(v.value)
            else:
                setattr(db_job, k, v)
        session.add(db_job)
        session.commit()


# ── Public API — mirrors pipeline_service.py exactly ──────────────────────

async def trigger_organize(force: bool = False) -> PipelineRunResponse:
    job = _new_job("organize")

    async def _run():
        try:
            from runner import main as run_organize
            from app.api.services.migration_runner import run_backfill
            statuses = await asyncio.to_thread(run_organize)
            await asyncio.to_thread(run_backfill) # one-time backfill for pre-pipeline data; can be removed after a few runs
            _update_job(
                job.job_id,
                status=PipelineStatus.completed,
                output=f"Organize complete: {statuses}",
                files_processed=statuses.get("total_files", 0),
                finished_at=datetime.utcnow(),
            )
        except Exception as e:
            _update_job(
                job.job_id,
                status=PipelineStatus.failed,
                error=str(e),
                finished_at=datetime.utcnow(),
            )

    asyncio.create_task(_run())
    return PipelineRunResponse(
        job_id=job.job_id,
        status=job.status,
        mode=job.mode,
        message="Organize job started.",
        started_at=job.started_at,
    )


async def get_transcripts():
    with get_session() as session:
        meetings = session.exec(
            select(Meeting)
            .order_by(Meeting.date)
        ).all()
        
        return meetings
    
async def trigger_summarize(
    meeting_ids: Optional[list[str]] = None,
) -> PipelineRunResponse:
    job = _new_job("summarize")

    async def _run():
        from datetime import datetime

        try:
            with get_session() as session:
                meetings = session.exec(
                    select(Meeting)
                    .where(Meeting.meeting_id.in_(meeting_ids)) if meeting_ids else select(Meeting)
                ).all()

            output = ""

            for meeting in meetings:
                with get_session() as session:
                    # Try captions first
                    captions = session.exec(
                        select(Caption)
                        .where(Caption.meeting_id == meeting.id)
                        .order_by(Caption.ts)
                    ).all()

                    if captions:
                        data = {
                            "captions": [
                                {"speaker": c.speaker, "text": c.text, "ts": c.ts}
                                for c in captions
                            ]
                        }
                    else:
                        # fallback to transcript turns
                        turns = session.exec(
                            select(TranscriptTurn)
                            .where(TranscriptTurn.meeting_id == meeting.id)
                            .order_by(TranscriptTurn.turn_id)
                        ).all()

                        if turns:
                            data = {
                                "transcripts": [
                                    {
                                        "id": t.turn_id,
                                        "speaker": t.speaker,
                                        "text": t.text,
                                        "timestamp": t.timestamp,
                                        "relativeTime": t.relative_time,
                                        "confidence": t.confidence,
                                        "wordCount": t.word_count,
                                    }
                                    for t in turns
                                ]
                            }
                        else:
                            # nothing to process
                            output += f"\n⚠ {meeting.meeting_id} → No captions or transcript"
                            continue

                # Run LLM in a thread to avoid blocking
                error = await run_llm_on_data(meeting.meeting_id, meeting.date, data)
                if isinstance(error, dict):
                    output += f"\n✓ {meeting.meeting_id}"
                else:
                    output += f"\n❌ {meeting.meeting_id} → {error}"

            # compute final status
            successes = output.count("✓")
            failures  = output.count("❌")
            final_status = (
                PipelineStatus.failed
                if successes == 0 and failures > 0
                else PipelineStatus.completed
            )

            _update_job(
                job.job_id,
                status=final_status,
                output=output,
                files_processed=successes,
                finished_at=datetime.utcnow(),
            )

        except Exception as e:
            _update_job(
                job.job_id,
                status=PipelineStatus.failed,
                error=str(e),
                finished_at=datetime.utcnow(),
            )

    # Await the background task instead of just creating it
    await _run()
    return PipelineRunResponse(
        job_id=job.job_id,
        status=job.status,
        mode=job.mode,
        message="Summarize job started.",
        started_at=job.started_at,
    )
    
async def trigger_full(
    target_date: Optional[str] = None,
    file_paths: Optional[list[str]] = None,
) -> PipelineRunResponse:
    job = _new_job("full")

    async def _run():
        from pathlib import Path
        from runner import main as run_organize
        from llm_runner import find_transcripts, run_llm_on_file

        try:
            statuses = await asyncio.to_thread(run_organize)
            output = f"Organize complete: {statuses}\n"

            if file_paths:
                selected = [Path(p) for p in file_paths]
            else:
                all_files = find_transcripts()
                selected = [
                    f for f, _ in all_files
                    if not target_date or target_date in str(f)
                ]

            for f in selected:
                error = await asyncio.to_thread(run_llm_on_file, f)
                if error is None:
                    output += f"\n✓ {f.name}"
                else:
                    output += f"\n❌ {f.name} → {error}"

            successes = output.count("✓")
            failures  = output.count("❌")
            final_status = (
                PipelineStatus.failed
                if successes == 0 and failures > 0
                else PipelineStatus.completed
            )

            _update_job(
                job.job_id,
                status=final_status,
                output=output,
                files_processed=successes,
                finished_at=datetime.utcnow(),
            )
        except Exception as e:
            _update_job(
                job.job_id,
                status=PipelineStatus.failed,
                error=str(e),
                finished_at=datetime.utcnow(),
            )

    asyncio.create_task(_run())
    return PipelineRunResponse(
        job_id=job.job_id,
        status=job.status,
        mode=job.mode,
        message="Full pipeline started.",
        started_at=job.started_at,
    )


def get_job_status(job_id: str) -> Optional[PipelineStatusResponse]:
    # Cache hit — no DB round trip needed
    if job_id in _jobs:
        return _jobs[job_id]

    # Cache miss — process restarted, pull from DB
    with Session(engine) as session:
        db_job = session.exec(
            select(Job).where(Job.job_id == job_id)
        ).first()
        if not db_job:
            return None
        schema = _to_schema(db_job)
        _jobs[job_id] = schema
        return schema


def list_jobs() -> list[PipelineStatusResponse]:
    with Session(engine) as session:
        db_jobs = session.exec(
            select(Job).order_by(Job.started_at.desc())
        ).all()
        return [_to_schema(j) for j in db_jobs]