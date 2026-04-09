"""
ChronoFlow — Meetings Service
Reads the data/organized directory and hydrates meeting objects.
"""

import os
import json
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from app.api.schema.schemas import (
    MeetingSummary, MeetingFile, FileType, ParticipantScore,
    MeetingsListResponse, RawFile, RawFilesResponse
)
from app.api.core.config import settings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _detect_file_type(filename: str) -> FileType:
    name = filename.lower()
    if "summary" in name and name.endswith(".json"):
        return FileType.summary
    if "caption" in name and "transcript" in name  and name.endswith(".json"):
        return FileType.captions_and_transcripts
    if "caption" in name and name.endswith(".json"):
        return FileType.captions
    if "transcript" in name and name.endswith(".json"):
        return FileType.transcript
    if "audio" in name and name.endswith(".webm"):
        return FileType.audio
    if "video" in name and name.endswith(".webm"):
        return FileType.video
    return FileType.unknown


def _extract_meeting_id(filename: str) -> str:
    import hashlib

    # Format 1: xxx-xxxx-xxx  e.g. hrp-axdm-gqm
    match = re.search(r'([a-z]{3}-[a-z]{4}-[a-z]{3})', filename)
    if match:
        return match.group(1)

    # Format 3: meet_captions_<ts> or meet_transcript_<ts> — check BEFORE Format 2
    # Must come before Meet– check or the Meet prefix in these names confuses it
    match = re.search(r'^meet[_-](?:captions|transcript|recording)[_-](\d+)', filename, re.IGNORECASE)
    if match:
        h = hashlib.md5(match.group(1).encode()).hexdigest()[:8]
        return f"ts-{h}"

    # Format 2: meet-transcript-Meet– or Meet_ prefix — extract just the Meet... part
    match = re.search(r'(Meet(?:\u2013|_)[^-]+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback
    h = hashlib.md5(filename.encode()).hexdigest()[:8]
    return f"unk-{h}"


def _parse_summary_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise the nested summary JSON into flat fields."""
    response = data.get("response", data)
    overview = response.get("meeting_overview", {})
    scoring = response.get("scoring", {})
    theme = response.get("meeting_theme", {})
    overall = response.get("overall_summary", {})

    participants = overview.get("participants", [])
    scores: List[ParticipantScore] = []
    for name, s in scoring.get("participants", {}).items():
        scores.append(ParticipantScore(
            name=name,
            participation=s.get("participation"),
            clarity=s.get("clarity"),
            technical=s.get("technical"),
            communication=s.get("communication"),
            leadership=s.get("leadership"),
            weighted_score=s.get("weighted_score"),
            rank=s.get("rank"),
        ))

    return {
        "participants": participants,
        "primary_theme": theme.get("primary_theme"),
        "overall_effectiveness": overall.get("overall_effectiveness"),
        "duration_minutes": overview.get("duration_minutes"),
        "participant_scores": scores,
        "raw": response,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def get_organized_root() -> str:
    return settings.ORGANIZED_DATA_DIR


def get_raw_files() -> RawFilesResponse:
    raw_dir = settings.RAW_DATA_DIR
    files = []
    
    # Check if the raw directory exists
    if not os.path.exists(raw_dir):
        return RawFilesResponse(total=0, files=[])

    for fname in os.listdir(raw_dir):
        fpath = os.path.join(raw_dir, fname)
        
        # Check if it's a file and meets the criteria for filename
        if os.path.isfile(fpath) and fname.startswith("meet") and (fname.endswith(".webm") or fname.endswith(".json")):
            stat = os.stat(fpath)
            
            # Create a RawFile object and append to files list
            files.append(RawFile(
                filename=fname,
                file_type=_detect_file_type(fname),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                meeting_id=_extract_meeting_id(fname),
            ))

    # Return the total count of files and the list of files
    return RawFilesResponse(total=len(files), files=files)


def list_meetings() -> MeetingsListResponse:
    organized_dir = settings.ORGANIZED_DATA_DIR
    meetings: List[MeetingSummary] = []
    dates: List[str] = []

    if not os.path.exists(organized_dir):
        return MeetingsListResponse(total_dates=0, total_meetings=0, dates=[], meetings=[])

    for date_folder in sorted(os.listdir(organized_dir), reverse=True):
        date_path = os.path.join(organized_dir, date_folder)
        if not os.path.isdir(date_path):
            continue
        dates.append(date_folder)

        # Group files by meeting_id
        meeting_map: Dict[str, List[str]] = {}
        for fname in os.listdir(date_path):
            mid = _extract_meeting_id(fname)
            meeting_map.setdefault(mid, []).append(fname)

        for mid, fnames in meeting_map.items():
            summary_data = None
            mfiles = []
            for fname in fnames:
                fpath = os.path.join(date_path, fname)
                stat = os.stat(fpath)
                ft = _detect_file_type(fname)
                mfiles.append(MeetingFile(filename=fname, file_type=ft, size_bytes=stat.st_size))
                if ft == FileType.summary and summary_data is None:
                    try:
                        with open(fpath) as f:
                            summary_data = json.load(f)
                    except Exception:
                        pass

            parsed = _parse_summary_json(summary_data) if summary_data else {}
            file_types = {f.file_type for f in mfiles}

            meetings.append(MeetingSummary(
                meeting_id=mid,
                date=date_folder,
                has_summary=FileType.summary in file_types,
                has_captions=FileType.captions in file_types,
                has_audio=FileType.audio in file_types,
                has_video=FileType.video in file_types,
                has_transcript=FileType.transcript in file_types,
                participants=parsed.get("participants", []),
                primary_theme=parsed.get("primary_theme"),
                overall_effectiveness=parsed.get("overall_effectiveness"),
                duration_minutes=parsed.get("duration_minutes"),
                participant_scores=parsed.get("participant_scores", []),
                files=mfiles,
                summary_data=parsed.get("raw") if summary_data else None,
            ))

    return MeetingsListResponse(
        total_dates=len(dates),
        total_meetings=len(meetings),
        dates=dates,
        meetings=meetings,
    )


def get_meeting_detail(meeting_id: str, date: str) -> Optional[MeetingSummary]:
    all_meetings = list_meetings()
    for m in all_meetings.meetings:
        if m.meeting_id == meeting_id and m.date == date:
            return m
    return None

def get_captions(meeting_id: str, date: str) -> list | None:
    """Find and return the captions JSON for a given meeting."""
    date_path = os.path.join(settings.ORGANIZED_DATA_DIR, date)
    if not os.path.exists(date_path):
        return None

    for fname in os.listdir(date_path):
        # match captions file for this meeting_id, excluding summary files
        if (
            meeting_id in fname
            and "caption" in fname.lower()
            and "summary" not in fname.lower()
            and fname.endswith(".json")
        ):
            fpath = os.path.join(date_path, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                # captions files are either a plain list or {"captions": [...]}
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("captions") or data.get("transcript") or []
            except Exception:
                return None

    return None


