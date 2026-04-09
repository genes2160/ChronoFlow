# app/api/services/db_meetings_service.py
"""
ChronoFlow — DB-backed meetings service
Mirrors meetings_service.py exactly. Same return types, same schemas.
Swap the import and everything works.
"""

from typing import Optional

from sqlmodel import Session, select, func
from sqlalchemy import or_

from app.api.models.model import (
    LLMRequestLog, Meeting, Summary, ParticipantScore,
    TranscriptTurn, Caption, MediaFile
)
from app.api.schema.schemas import (
    MeetingSummary, MeetingFile, FileType,
    ParticipantScore as ParticipantScoreSchema,
    MeetingsListResponse, RawFile, RawFilesResponse
)
from app.api.core.db import get_session


# ── Internal builders ──────────────────────────────────────────────────────

def _file_type_from_str(s: str) -> FileType:
    try:
        return FileType(s)
    except ValueError:
        return FileType.unknown


def _build_meeting_summary(
    meeting: Meeting,
    session: Session,
) -> MeetingSummary:
    """Build a MeetingSummary schema from DB rows."""

    # Participant scores
    scores = session.exec(
        select(ParticipantScore)
        .where(ParticipantScore.meeting_id == meeting.id)
    ).all()

    score_schemas = [
        ParticipantScoreSchema(
            name=s.name,
            participation=s.participation,
            clarity=s.clarity,
            technical=s.technical,
            communication=s.communication,
            leadership=s.leadership,
            weighted_score=s.weighted_score,
            rank=s.rank,
        )
        for s in scores
    ]

    # Summary raw_json
    summary = session.exec(
        select(Summary).where(Summary.meeting_id == meeting.id)
    ).first()

    # Media files → MeetingFile list
    media = session.exec(
        select(MediaFile).where(MediaFile.meeting_id == meeting.id)
    ).all()

    files = [
        MeetingFile(
            filename=m.filename,
            file_type=_file_type_from_str(m.file_type.value),
            size_bytes=m.size_bytes or 0,
        )
        for m in media
    ]

    # Participants list from summary raw_json
    participants: list[str] = []
    primary_theme = None
    overall_effectiveness = None
    summary_data = None

    if summary and summary.raw_json:
        raw = summary.raw_json
        overview = raw.get("meeting_overview", {})
        participants = overview.get("participants", [])
        primary_theme = summary.primary_theme
        overall_effectiveness = summary.overall_effectiveness
        summary_data = raw

    return MeetingSummary(
        meeting_id=meeting.meeting_id,
        date=meeting.date,
        has_summary=meeting.has_summary,
        has_captions=meeting.has_captions,
        has_audio=meeting.has_audio,
        has_video=meeting.has_video,
        has_transcript=meeting.has_transcript,
        participants=participants,
        primary_theme=primary_theme,
        overall_effectiveness=overall_effectiveness,
        duration_minutes=meeting.duration_minutes,
        participant_scores=score_schemas,
        files=files,
        summary_data=summary_data,
    )


# ── Public API — mirrors meetings_service.py exactly ──────────────────────

def get_raw_files() -> RawFilesResponse:
    """
    Raw files still live on disk during transition.
    Once files are deleted post-migration this returns empty — expected.
    """
    from app.api.services.meetings_service import get_raw_files as _fs_raw
    return _fs_raw()


def list_meetings(
    session,
    date: Optional[str] = None,
    has_summary: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    sort_by: str = "date",
    sort_order: str = "desc",
):
    query = select(Meeting)

    # ✅ FILTERS
    if date:
        query = query.where(Meeting.date == date)

    if has_summary is not None:
        query = query.where(Meeting.has_summary == has_summary)

    # ✅ SEARCH (indexed fields only ideally)
    if search:
        s = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Meeting.meeting_id).like(s),
                func.lower(Meeting.date).like(s)
            )
        )

    # ✅ TOTAL COUNT (before pagination)
    total = session.exec(
        select(func.count()).select_from(query.subquery())
    ).one()

    # ✅ SORTING (safe mapping)
    sort_map = {
        "date": Meeting.date,
        "meeting_id": Meeting.meeting_id,
        "created_at": Meeting.created_at,
        "duration": Meeting.duration_minutes,
    }

    sort_col = sort_map.get(sort_by, Meeting.date)

    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # ✅ PAGINATION
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    meetings = session.exec(query).all()

    # ✅ ONLY build summaries for current page
    meeting_summaries = [
        _build_meeting_summary(m, session)
        for m in meetings
    ]

    # ✅ dates (optional optimization: separate query if large dataset)
    dates = session.exec(
        select(Meeting.date).distinct().order_by(Meeting.date.desc())
    ).all()

    return MeetingsListResponse(
        total_dates=len(dates),
        total_meetings=total,
        dates=dates,
        meetings=meeting_summaries,
    )

def get_meeting_detail(meeting_id: str, date: str) -> MeetingSummary | None:
    with get_session() as session:
        meeting = session.exec(
            select(Meeting).where(
                Meeting.meeting_id == meeting_id,
                Meeting.date == date,
            )
        ).first()

        if not meeting:
            return None

        # single extra query — just the latest log row, no joins needed
        llm_log = session.exec(
            select(LLMRequestLog.provider, LLMRequestLog.model, LLMRequestLog.created_at)
            .where(LLMRequestLog.meeting_id == meeting.meeting_id)
            .order_by(LLMRequestLog.created_at.desc())
            .limit(1)
        ).first()

        summary = _build_meeting_summary(meeting, session)

        if llm_log:
            summary.summary_data = {
                **(summary.summary_data or {}),
                "_llm": {
                    "provider": llm_log.provider,
                    "model":    llm_log.model,
                    "ran_at":   llm_log.created_at.isoformat(),
                }
            }

        return summary


def get_captions(meeting_id: str, date: str) -> list | None:
    with get_session() as session:
        meeting = session.exec(
            select(Meeting).where(
                Meeting.meeting_id == meeting_id,
                Meeting.date == date,
            )
        ).first()

        if not meeting:
            return None

        captions = session.exec(
            select(Caption)
            .where(Caption.meeting_id == meeting.id)
            .order_by(Caption.ts)
        ).all()

        return [
            {"speaker": c.speaker, "text": c.text, "ts": c.ts}
            for c in captions
        ]



