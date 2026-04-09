# app/api/services/db_analytics_service.py
"""
ChronoFlow — DB-backed analytics service
Mirrors analytics_service.py exactly. Same return types, same schemas.
"""

from collections import defaultdict
from sqlmodel import Session, select

from app.api.models.model import (
    Meeting, Summary, ParticipantScore,
    TranscriptTurn, MediaFile
)
from app.api.schema.schemas import (
    AnalyticsOverview, ParticipantStat, FileType
)
from app.api.core.db import get_session


def get_overview() -> AnalyticsOverview:
    with get_session() as session:

        meetings = session.exec(select(Meeting)).all()
        media    = session.exec(select(MediaFile)).all()
        scores   = session.exec(select(ParticipantScore)).all()
        summaries = session.exec(select(Summary)).all()

        # index summaries by meeting_id for O(1) lookup
        summary_map = {s.meeting_id: s for s in summaries}

        # ── aggregations ──────────────────────────────────────────────
        meetings_by_date:   dict[str, int]  = defaultdict(int)
        file_type_breakdown: dict[str, int] = defaultdict(int)
        effectiveness_scores: list[float]   = []
        pending_summarization               = 0

        for m in meetings:
            meetings_by_date[m.date] += 1

            if not m.has_summary:
                pending_summarization += 1

            s = summary_map.get(m.id)
            if s and s.overall_effectiveness is not None:
                effectiveness_scores.append(s.overall_effectiveness)

        # file type breakdown from media_files
        # has_* flags cover audio/video — media_files gives us the exact types
        for mf in media:
            file_type_breakdown[mf.file_type.value] += 1

        # supplement with transcript/caption/summary counts from meeting flags
        for m in meetings:
            if m.has_transcript:
                file_type_breakdown[FileType.transcript.value] += 1
            if m.has_captions:
                file_type_breakdown[FileType.captions.value] += 1
            if m.has_summary:
                file_type_breakdown[FileType.summary.value] += 1

        # ── participant stats ─────────────────────────────────────────
        participant_map: dict[str, dict] = defaultdict(lambda: {
            "meetings": 0,
            "score_sum": 0.0,
            "score_count": 0,
            "participation_sum": 0.0,
        })

        for score in scores:
            p = participant_map[score.name]
            p["meetings"] += 1
            if score.weighted_score is not None:
                p["score_sum"]   += score.weighted_score
                p["score_count"] += 1
            if score.participation is not None:
                p["participation_sum"] += score.participation

        top_participants = sorted(
            [
                ParticipantStat(
                    name=name,
                    meetings_attended=stats["meetings"],
                    avg_weighted_score=round(
                        stats["score_sum"] / max(stats["score_count"], 1), 2
                    ),
                    avg_participation=round(
                        stats["participation_sum"] / max(stats["meetings"], 1), 2
                    ),
                    total_words_spoken=0,   # transcript word counts not yet aggregated
                )
                for name, stats in participant_map.items()
            ],
            key=lambda p: p.avg_weighted_score,
            reverse=True,
        )

        # ── pending processing ────────────────────────────────────────
        # meetings in DB with no transcript = not yet processed by pipeline
        pending_processing = sum(1 for m in meetings if not m.has_transcript)

        # ── raw files still on disk (transition period) ───────────────
        try:
            from app.api.services.meetings_service import get_raw_files
            raw_total = get_raw_files().total
        except Exception:
            raw_total = 0

        return AnalyticsOverview(
            total_meetings=len(meetings),
            total_dates=len(meetings_by_date),
            total_raw_files=raw_total,
            pending_processing=pending_processing,
            pending_summarization=pending_summarization,
            avg_effectiveness=round(
                sum(effectiveness_scores) / len(effectiveness_scores), 2
            ) if effectiveness_scores else 0.0,
            top_participants=top_participants[:10],
            meetings_by_date=dict(meetings_by_date),
            file_type_breakdown=dict(file_type_breakdown),
        )