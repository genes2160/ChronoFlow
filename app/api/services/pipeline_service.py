"""
ChronoFlow — Pipeline Service
Spawns runner.py / llm_runner.py subprocesses and tracks job state in memory.
Swap in Redis / DB when you're ready to scale.
"""

import asyncio
from pathlib import Path
import re
import uuid
import subprocess
import sys
from datetime import datetime
from typing import Dict, Optional

from app.api.schema.schemas import PipelineStatus, PipelineStatusResponse, PipelineRunResponse
from app.api.core.config import settings

# In-memory job store — replace with DB/Redis for production
_jobs: Dict[str, PipelineStatusResponse] = {}


def _new_job(mode: str) -> PipelineStatusResponse:
    job_id = str(uuid.uuid4())[:8]
    job = PipelineStatusResponse(
        job_id=job_id,
        status=PipelineStatus.running,
        mode=mode,
        started_at=datetime.utcnow(),
        files_processed=0,
    )
    _jobs[job_id] = job
    return job


async def _run_subprocess(job_id: str, cmd: list[str]):
    """Run a subprocess and update the job record when done."""
    job = _jobs[job_id]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        job.output = output
        job.finished_at = datetime.utcnow()
        if proc.returncode == 0:
            job.status = PipelineStatus.completed
            # Rough file-count heuristic from output
            job.files_processed = output.lower().count("process") + output.lower().count("moved")
        else:
            job.status = PipelineStatus.failed
            job.error = output
    except Exception as e:
        job.status = PipelineStatus.failed
        job.error = str(e)
        job.finished_at = datetime.utcnow()

async def get_transcripts():
    from llm_runner import find_transcripts
    files = find_transcripts()
    return {
        "transcripts": [
            {"path": f.as_posix(), "name": f.name, "date": f.parent.name, "size_kb": round(size/1024, 2)}
            for f, size in files
        ]
    }

async def trigger_organize(force: bool = False) -> PipelineRunResponse:
    job = _new_job("organize")

    async def _run():
        try:
            from runner import main as run_organize
            job.status = PipelineStatus.running
            statuses = await asyncio.to_thread(run_organize)
            job.status = PipelineStatus.completed
            job.output = f"Organize complete: {statuses}"
            job.finished_at = datetime.utcnow()
        except Exception as e:
            job.status = PipelineStatus.failed
            job.error = str(e)
            job.finished_at = datetime.utcnow()

    asyncio.create_task(_run())
    return PipelineRunResponse(
        job_id=job.job_id, status=job.status, mode=job.mode,
        message="Organize job started.", started_at=job.started_at,
    )

async def save_jobs(job):
    try:
        from app.processor import save_summary, get_summary
        from pathlib import Path
        JOBS_DIR = Path("data/raw/jobs")
        JOBS_DIR.mkdir(exist_ok=True)
        jobs = get_summary()
        jobs.append(job)
        save_summary(JOBS_DIR, jobs)
    except Exception as err:
        pass


async def trigger_summarize(target_date: Optional[str] = None, file_paths: Optional[list[str]] = None, target_file:Optional[str] = None) -> PipelineRunResponse:
    """Run LLM summarization on specific files."""
    job = _new_job("summarize")

    async def _run():
        from llm_runner import find_transcripts, run_llm_on_file
        
        try:
            if target_file:
                # API told us exactly which file (singular)
                selected = [Path(target_file)]
            elif file_paths:
                # API told us exactly which files
                selected = [Path(p) for p in file_paths]
            else:
                # fallback: all transcripts for the date
                all_files = find_transcripts()
                if target_date:
                    selected = [f for f, _ in all_files if target_date in str(f)]
                else:
                    selected = [f for f, _ in all_files]

            print("settings", settings)
            job.status = PipelineStatus.running
            for f in selected:
                error = await asyncio.to_thread(run_llm_on_file, f)
                if error is None:
                    job.output = (job.output or "") + f"\n✓ {f.name}"
                else:
                    job.output = (job.output or "") + f"\n❌ {f.name} → {error}"

            # set status ONCE after the loop
            successes = (job.output or "").count("✓")
            failures = (job.output or "").count("❌")
            if successes == 0 and failures > 0:
                job.status = PipelineStatus.failed
            else:
                job.status = PipelineStatus.completed

            job.finished_at = datetime.utcnow()
        except Exception as e:
            job.status = PipelineStatus.failed
            job.error = str(e)
            job.finished_at = datetime.utcnow()  # ← missing too
        finally:
            #save the job in a file
            await save_jobs(job=job)

    asyncio.create_task(_run())
    return PipelineRunResponse(
        job_id=job.job_id,
        status=job.status,
        mode=job.mode,
        message=f"Summarize job started.",
        started_at=job.started_at,
    )


async def trigger_full(target_date: Optional[str] = None, file_paths: Optional[list[str]] = None) -> PipelineRunResponse:
    job = _new_job("full")

    async def _run():
        try:
            from runner import main as run_organize
            from llm_runner import find_transcripts, run_llm_on_file
            from pathlib import Path

            job.status = PipelineStatus.running

            # step 1 — organize
            statuses = await asyncio.to_thread(run_organize)
            job.output = f"Organize complete: {statuses}\n"

            # step 2 — summarize
            if file_paths:
                selected = [Path(p) for p in file_paths]
            else:
                all_files = find_transcripts()
                selected = [f for f, _ in all_files if not target_date or target_date in str(f)]

            job.status = PipelineStatus.running
            for f in selected:
                error = await asyncio.to_thread(run_llm_on_file, f)
                if error is None:
                    job.output = (job.output or "") + f"\n✓ {f.name}"
                else:
                    job.output = (job.output or "") + f"\n❌ {f.name} → {error}"

            # set status ONCE after the loop
            successes = (job.output or "").count("✓")
            failures = (job.output or "").count("❌")
            if successes == 0 and failures > 0:
                job.status = PipelineStatus.failed
            else:
                job.status = PipelineStatus.completed

            job.finished_at = datetime.utcnow()
        except Exception as e:
            job.status = PipelineStatus.failed
            job.error = str(e)
            job.finished_at = datetime.utcnow()

        finally:
            #save the job in a file
            await save_jobs(job=job)
    asyncio.create_task(_run())
    return PipelineRunResponse(
        job_id=job.job_id, status=job.status, mode=job.mode,
        message="Full pipeline started.", started_at=job.started_at,
    )


def get_job_status(job_id: str) -> Optional[PipelineStatusResponse]:
    return _jobs.get(job_id)


def list_jobs() -> list[PipelineStatusResponse]:
    return sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)