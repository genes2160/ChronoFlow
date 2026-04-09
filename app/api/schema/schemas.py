"""
ChronoFlow — Pydantic schemas
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────

class FileType(str, Enum):
    audio = "audio"
    video = "video"
    captions_and_transcripts = "captions_and_transcripts"
    captions = "captions"
    transcript = "transcript"
    summary = "summary"
    unknown = "unknown"


class PipelineStatus(str, Enum):
    idle = "idle"
    running = "running"
    completed = "completed"
    failed = "failed"


# ── Raw files ───────────────────────────────────────────────────────────────

class RawFile(BaseModel):
    filename: str
    file_type: FileType
    size_bytes: int
    modified_at: datetime
    meeting_id: Optional[str] = None


class RawFilesResponse(BaseModel):
    total: int
    files: List[RawFile]


# ── Organized meetings ──────────────────────────────────────────────────────

class ParticipantScore(BaseModel):
    name: str
    participation: Optional[int] = None
    clarity: Optional[int] = None
    technical: Optional[int] = None
    communication: Optional[int] = None
    leadership: Optional[int] = None
    weighted_score: Optional[float] = None
    rank: Optional[int] = None


class MeetingFile(BaseModel):
    filename: str
    file_type: FileType
    size_bytes: int


class MeetingSummary(BaseModel):
    meeting_id: str
    date: str
    has_summary: bool
    has_captions: bool
    has_audio: bool
    has_video: bool
    has_transcript: bool
    participants: List[str]
    primary_theme: Optional[str] = None
    overall_effectiveness: Optional[float] = None
    duration_minutes: Optional[int] = None
    participant_scores: List[ParticipantScore] = []
    files: List[MeetingFile] = []
    summary_data: Optional[Dict[str, Any]] = None
    meeting_name: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    duration_ms: Optional[int] = None
    attendee_count: Optional[int] = None
    total_words: Optional[int] = None
    avg_confidence: Optional[float] = None

class MeetingsListResponse(BaseModel):
    total_dates: int
    total_meetings: int
    dates: List[str]
    meetings: List[MeetingSummary]


class MeetingDetailResponse(BaseModel):
    meeting: MeetingSummary


# ── Pipeline ────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    mode: str = "organize"        # "organize" | "summarize" | "full"
    target_date: Optional[str] = None   # e.g. "2026-03-26", None = all
    force: bool = False
    meeting_ids: Optional[list[str]] = None  #
    file_paths: Optional[list[str]] = None  #
    file_path: Optional[str] = None  #


class PipelineRunResponse(BaseModel):
    job_id: str
    status: PipelineStatus
    mode: str
    message: str
    started_at: datetime


class PipelineStatusResponse(BaseModel):
    job_id: str
    status: PipelineStatus
    mode: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None
    files_processed: int = 0


# ── Analytics ───────────────────────────────────────────────────────────────

class ParticipantStat(BaseModel):
    name: str
    meetings_attended: int
    avg_weighted_score: float
    avg_participation: float
    total_words_spoken: int


class AnalyticsOverview(BaseModel):
    total_meetings: int
    total_dates: int
    total_raw_files: int
    pending_processing: int
    pending_summarization: int
    avg_effectiveness: float
    top_participants: List[ParticipantStat]
    meetings_by_date: Dict[str, int]
    file_type_breakdown: Dict[str, int]
