# app/api/services/db_participant_stats_service.py
from collections import defaultdict
from sqlmodel import select, func
from app.api.core.db import get_session
from app.api.models.model import Meeting, ParticipantScore, TranscriptTurn

# Mapping of aliases → canonical names
NAME_MERGE_MAP = {
    "Eugee": "You",
    "You": "You",  # canonical
    # add more if needed in future
}

def get_participant_aggregates():
    stats = defaultdict(lambda: {
        "total_meetings": 0,
        "total_turns": 0,
        "total_words": 0,
        "total_participation": 0,
        "total_leadership": 0,
        "total_clarity": 0,
        "total_technical": 0,
        "total_communication": 0,
    })

    with get_session() as session:
        print("DEBUG: Starting participant aggregates computation...")

        meetings = session.exec(
            select(Meeting).where(Meeting.has_summary == True)
        ).all()
        print(f"DEBUG: Meetings with summary found: {len(meetings)}")
        if not meetings:
            return {}

        meeting_ids = [m.id for m in meetings]

        # Step 1: Aggregate ParticipantScore
        score_rows = session.exec(
            select(
                ParticipantScore.name,
                func.count(ParticipantScore.meeting_id).label("total_meetings"),
                func.coalesce(func.sum(ParticipantScore.participation), 0).label("total_participation"),
                func.coalesce(func.sum(ParticipantScore.leadership), 0).label("total_leadership"),
                func.coalesce(func.sum(ParticipantScore.clarity), 0).label("total_clarity"),
                func.coalesce(func.sum(ParticipantScore.technical), 0).label("total_technical"),
                func.coalesce(func.sum(ParticipantScore.communication), 0).label("total_communication")
            )
            .where(ParticipantScore.meeting_id.in_(meeting_ids))
            .group_by(ParticipantScore.name)
        ).all()

        print(f"DEBUG: ParticipantScore rows found: {len(score_rows)}")

        for row in score_rows:
            canonical_name = NAME_MERGE_MAP.get(row.name, row.name)
            s = stats[canonical_name]
            s["total_meetings"] += row.total_meetings
            s["total_participation"] += row.total_participation
            s["total_leadership"] += row.total_leadership
            s["total_clarity"] += row.total_clarity
            s["total_technical"] += row.total_technical
            s["total_communication"] += row.total_communication

        # Step 2: Aggregate TranscriptTurn
        turn_rows = session.exec(
            select(
                TranscriptTurn.speaker,
                func.count().label("total_turns"),
                func.coalesce(func.sum(func.length(TranscriptTurn.text) - func.length(func.replace(TranscriptTurn.text, ' ', '')) + 1), 0).label("total_words")
            )
            .where(TranscriptTurn.meeting_id.in_(meeting_ids))
            .group_by(TranscriptTurn.speaker)
        ).all()

        print(f"DEBUG: TranscriptTurn rows found: {len(turn_rows)}")

        for row in turn_rows:
            canonical_name = NAME_MERGE_MAP.get(row.speaker, row.speaker)
            s = stats[canonical_name]
            s["total_turns"] += row.total_turns
            s["total_words"] += row.total_words

        # Step 3: Compute averages
        for name, p in stats.items():
            if p["total_meetings"] > 0:
                p["avg_participation"] = p["total_participation"] / p["total_meetings"]
                p["avg_leadership"] = p["total_leadership"] / p["total_meetings"]
                p["avg_clarity"] = p["total_clarity"] / p["total_meetings"]
                p["avg_technical"] = p["total_technical"] / p["total_meetings"]
                p["avg_communication"] = p["total_communication"] / p["total_meetings"]
            else:
                p["avg_participation"] = p["avg_leadership"] = 0
                p["avg_clarity"] = p["avg_technical"] = p["avg_communication"] = 0

    print(f"DEBUG: Completed aggregation. Total participants: {len(stats)}")
    return stats