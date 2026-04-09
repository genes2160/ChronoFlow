"""
ChronoFlow — Analytics Service
"""

from collections import defaultdict
from typing import Dict

from app.api.schema.schemas import AnalyticsOverview, ParticipantStat, FileType
from app.api.services.meetings_service import list_meetings, get_raw_files


def get_overview() -> AnalyticsOverview:
    meetings_data = list_meetings()
    raw_data = get_raw_files()

    meetings_by_date: Dict[str, int] = defaultdict(int)
    file_type_breakdown: Dict[str, int] = defaultdict(int)
    participant_map: Dict[str, dict] = defaultdict(lambda: {
        "meetings": 0, "score_sum": 0.0, "participation_sum": 0.0,
        "score_count": 0, "words": 0,
    })

    effectiveness_scores = []
    pending_summarization = 0

    for meeting in meetings_data.meetings:
        meetings_by_date[meeting.date] += 1

        if not meeting.has_summary:
            pending_summarization += 1

        if meeting.overall_effectiveness is not None:
            effectiveness_scores.append(meeting.overall_effectiveness)

        for f in meeting.files:
            file_type_breakdown[f.file_type.value] += 1

        for score in meeting.participant_scores:
            p = participant_map[score.name]
            p["meetings"] += 1
            if score.weighted_score is not None:
                p["score_sum"] += score.weighted_score
                p["score_count"] += 1
            if score.participation is not None:
                p["participation_sum"] += score.participation

    # Top participants
    top_participants = []
    for name, stats in participant_map.items():
        top_participants.append(ParticipantStat(
            name=name,
            meetings_attended=stats["meetings"],
            avg_weighted_score=round(stats["score_sum"] / max(stats["score_count"], 1), 2),
            avg_participation=round(stats["participation_sum"] / max(stats["meetings"], 1), 2),
            total_words_spoken=stats["words"],
        ))
    top_participants.sort(key=lambda p: p.avg_weighted_score, reverse=True)

    # Raw pending
    organized_meeting_ids = {m.meeting_id for m in meetings_data.meetings}
    pending_processing = sum(
        1 for f in raw_data.files
        if f.meeting_id not in organized_meeting_ids
    )

    return AnalyticsOverview(
        total_meetings=meetings_data.total_meetings,
        total_dates=meetings_data.total_dates,
        total_raw_files=raw_data.total,
        pending_processing=pending_processing,
        pending_summarization=pending_summarization,
        avg_effectiveness=round(
            sum(effectiveness_scores) / len(effectiveness_scores), 2
        ) if effectiveness_scores else 0.0,
        top_participants=top_participants[:10],
        meetings_by_date=dict(meetings_by_date),
        file_type_breakdown=dict(file_type_breakdown),
    )