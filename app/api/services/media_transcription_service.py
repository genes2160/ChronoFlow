import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import requests
from sqlmodel import select

from app.api.core.config import settings
from app.api.core.db import get_session
from app.api.models.model import (
    Meeting,
    MediaFile,
    MediaTranscriptionJob,
    MediaTranscriptionStatus,
)


def _convert_video_to_audio(input_path: Path) -> Path:
    output_path = settings.MEDIA_TMP_DIR / f"{input_path.stem}.wav"

    print(f"🎬 [TRANSCRIBE] converting video to audio -> input={input_path} output={output_path}")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed in the container")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print(f"✅ [TRANSCRIBE] video converted to audio -> {output_path}")
    return output_path


def _build_callback_url() -> str:
    return f"{settings.WHISPER_CALLBACK_BASE_URL}"


def create_media_transcription_job(meeting_id: str, filename: str) -> MediaTranscriptionJob:
    print(f"\n🎤 [TRANSCRIBE] create job -> meeting_id={meeting_id} filename={filename}")

    with get_session() as session:
        meeting = session.exec(
            select(Meeting).where(Meeting.meeting_id == meeting_id)
        ).first()

        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        media_file = session.exec(
            select(MediaFile).where(
                MediaFile.meeting_id == meeting.id,
                MediaFile.filename == filename,
            )
        ).first()

        if not media_file:
            raise ValueError(f"Media file not found for meeting: {filename}")

        existing_active_job = session.exec(
            select(MediaTranscriptionJob).where(
                MediaTranscriptionJob.meeting_id == meeting.id,
                MediaTranscriptionJob.source_filename == media_file.filename,
                MediaTranscriptionJob.status.in_([
                    MediaTranscriptionStatus.queued,
                    MediaTranscriptionStatus.processing,
                    MediaTranscriptionStatus.completed,
                ])
            )
        ).first()

        if existing_active_job:
            print(
                f"⏭ [TRANSCRIBE] active job already exists "
                f"-> local_id={existing_active_job.id} "
                f"status={existing_active_job.status} "
                f"filename={media_file.filename}"
            )
            raise ValueError(
                f"An active transcription already exists for this file "
                f"({existing_active_job.status})."
            )

        original_media_path = Path(media_file.storage_url)
        if not original_media_path.exists():
            raise ValueError(f"Media file missing on disk: {original_media_path}")

        source_file_type = "video" if media_file.file_type.value == "video" else "audio"

        submitted_audio_path = original_media_path
        if source_file_type == "video":
            submitted_audio_path = _convert_video_to_audio(original_media_path)

        callback_token = secrets.token_urlsafe(32)

        job = MediaTranscriptionJob(
            meeting_id=meeting.id,
            media_file_id=media_file.id,
            source_filename=media_file.filename,
            source_file_type=source_file_type,
            submitted_audio_path=str(submitted_audio_path),
            original_media_path=str(original_media_path),
            provider="whisper",
            callback_token=callback_token,
            status=MediaTranscriptionStatus.queued,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        print(f"🧾 [TRANSCRIBE] local job created -> id={job.id}")

        callback_url = _build_callback_url()
        print(f"🔗 [TRANSCRIBE] callback_url={callback_url}")

        with open(submitted_audio_path, "rb") as fh:
            response = requests.post(
                f"{settings.WHISPER_SERVICE_URL.rstrip('/')}/v1/transcribe",
                files={"file": (submitted_audio_path.name, fh, "audio/wav")},
                data={
                    "callback_url": callback_url,
                    "callback_token": callback_token,
                    "local_job_id": str(job.id),
                },
                timeout=120,
            )

        response.raise_for_status()
        payload = response.json()

        print(f"📨 [TRANSCRIBE] whisper accepted job -> payload={payload}")

        job.external_job_id = payload.get("job_id")
        job.status = MediaTranscriptionStatus.processing
        job.raw_response = payload
        session.add(job)
        session.commit()
        session.refresh(job)
        from app.api.services.notification_service import create_notification
        from app.api.models.model import NotificationType, NotificationStatus

        create_notification(
            type=NotificationType.transcription,
            status=NotificationStatus.processing,
            title="Whisper transcription started",
            message=f"{job.source_filename} was submitted for transcription.",
            meeting_id=meeting.id,
            transcription_job_id=job.id,
        )
        print(f"✅ [TRANSCRIBE] job updated -> local_id={job.id} external_job_id={job.external_job_id}")

        return job


def complete_media_transcription_job(
    external_job_id: str,
    callback_token: str,
    status: str,
    transcript_text: str | None = None,
    raw_response: dict | None = None,
    error: str | None = None,
) -> MediaTranscriptionJob:
    print(f"\n📥 [WHISPER WEBHOOK] incoming -> external_job_id={external_job_id} status={status}")

    with get_session() as session:
        job = session.exec(
            select(MediaTranscriptionJob).where(
                MediaTranscriptionJob.external_job_id == external_job_id
            )
        ).first()

        if not job:
            raise ValueError(f"Transcription job not found: {external_job_id}")

        if job.callback_token != callback_token:
            raise ValueError("Invalid callback token")

        if job.status == MediaTranscriptionStatus.completed:
            print(f"⏭ [WHISPER WEBHOOK] already completed -> local_id={job.id}")
            return job

        if status.lower() == "completed":
            job.status = MediaTranscriptionStatus.completed
            job.transcript_text = transcript_text
            job.raw_response = raw_response
            job.completed_at = datetime.utcnow()
            from app.api.services.notification_service import create_notification
            from app.api.models.model import NotificationType, NotificationStatus

            create_notification(
                type=NotificationType.transcription,
                status=NotificationStatus.completed,
                title="Whisper transcription completed",
                message=f"{job.source_filename} finished transcription successfully.",
                meeting_id=job.meeting_id,
                transcription_job_id=job.id,
            )
            print(f"✅ [WHISPER WEBHOOK] transcript stored -> local_id={job.id}")
        else:
            job.status = MediaTranscriptionStatus.failed
            job.error = error or "Whisper job failed"
            job.raw_response = raw_response
            job.completed_at = datetime.utcnow()
            from app.api.services.notification_service import create_notification
            from app.api.models.model import NotificationType, NotificationStatus

            create_notification(
                type=NotificationType.transcription,
                status=NotificationStatus.failed,
                title="Whisper transcription failed",
                message=f"{job.source_filename} failed transcription.",
                meeting_id=job.meeting_id,
                transcription_job_id=job.id,
            )
            print(f"❌ [WHISPER WEBHOOK] job failed -> local_id={job.id} error={job.error}")

        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def list_media_transcription_jobs(meeting_id: str) -> list[MediaTranscriptionJob]:
    print(f"\n📚 [TRANSCRIBE] list jobs -> meeting_id={meeting_id}")

    with get_session() as session:
        meeting = session.exec(
            select(Meeting).where(Meeting.meeting_id == meeting_id)
        ).first()

        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        jobs = session.exec(
            select(MediaTranscriptionJob)
            .where(MediaTranscriptionJob.meeting_id == meeting.id)
            .order_by(MediaTranscriptionJob.created_at.desc())
        ).all()

        print(f"📦 [TRANSCRIBE] jobs found -> count={len(jobs)}")
        return jobs
    

