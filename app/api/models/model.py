from app.api.models.base import SQLModel, Optional, Field, datetime, JSON, Column, Enum, FileTypeEnum, PipelineStatusEnum, DateTime, func, BigInteger, Float, String,Index, UniqueConstraint, Text, Boolean
import enum


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: str
    # add this to every table
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )

class Meeting(SQLModel, table=True):
    __tablename__ = "meetings"

    __table_args__ = (
        Index("idx_meetings_start_time", "start_time"),
        Index("idx_meetings_attendee_count", "attendee_count"),
        Index("idx_meetings_total_words", "total_words"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    meeting_id: str = Field(unique=True, index=True)  # e.g. hrp-axdm-gqm
    meeting_name: Optional[str] = Field(default=None, index=True)

    date: str = Field(index=True)  # you filter by date constantly

    duration_minutes: Optional[int] = None
    duration_ms: Optional[int] = None

    start_time: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    end_time: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )

    attendee_count: Optional[int] = None
    total_words: Optional[int] = None
    avg_confidence: Optional[float] = None

    has_summary: bool = False
    has_captions: bool = False
    has_transcript: bool = False
    has_audio: bool = False
    has_video: bool = False

    uploaded_by: Optional[int] = Field(default=None, foreign_key="users.id")
    # add this to every table
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class Caption(SQLModel, table=True):
    __tablename__ = "captions"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", index=True)
    speaker: Optional[str] = Field(default=None, index=True)
    text: str
    ts: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True, index=True)  # index goes here
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class TranscriptTurn(SQLModel, table=True):
    __tablename__ = "transcript_turns"

    __table_args__ = (
        Index("idx_transcript_timestamp", "meeting_id", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", index=True)
    turn_id: int
    speaker: Optional[str] = Field(default=None, index=True)
    text: str
    timestamp: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True, index=True)
    )
    relative_time: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    confidence: Optional[float] = None
    word_count: Optional[int] = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class Summary(SQLModel, table=True):
    __tablename__ = "summaries"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", unique=True)
    raw_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    overall_effectiveness: Optional[int] = None
    primary_theme: Optional[str] = None
    # add this to every table
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True)
    mode: str
    status: PipelineStatusEnum = Field(default=PipelineStatusEnum.idle, index=True)
    output: Optional[str] = None
    error: Optional[str] = None
    files_processed: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    triggered_by: Optional[int] = Field(default=None, foreign_key="users.id")
    # add this to every table
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )
    
class ParticipantScore(SQLModel, table=True):
    __tablename__ = "participant_scores"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", index=True)
    name: str = Field(index=True)
    participation: Optional[int] = None
    clarity: Optional[int] = None
    technical: Optional[int] = None
    communication: Optional[int] = None
    leadership: Optional[int] = None
    weighted_score: Optional[float] = None
    rank: Optional[int] = None
    created_at: datetime = Field(                                    # consistent pattern
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )

class MediaFile(SQLModel, table=True):
    __tablename__ = "media_files"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", index=True)
    filename: str
    file_type: FileTypeEnum
    size_bytes: Optional[int] = None
    storage_url: str
    storage_backend: str = "local"
    uploaded_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(                                    # was missing
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )

class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    id: int | None = Field(default=None, primary_key=True)
    name: str  # e.g., "summarize meeting"
    version: str = "1.0"
    text: str  # the prompt template itself
    is_active: bool = False
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(                                    # was missing
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )

class LLMRequestLog(SQLModel, table=True):
    __tablename__ = "llm_request_logs"
    id: int | None = Field(default=None, primary_key=True)
    prompt_id: int = Field(foreign_key="prompts.id")
    meeting_id: str
    provider: str  # e.g., "anthropic"
    model: str     # e.g., "claude_opus_4.5"
    data_hash: str = Field(sa_column=Column(String, index=True))  # hash of the input data
    response: str | None = None
    duration_sec: float | None = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(                                    # was missing
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    
def captions_from_file(meeting_id: int, data: list, uploaded_by: Optional[int] = None):
    return [
        Caption(
            meeting_id=meeting_id,
            speaker=c.get("speaker"),
            text=c["text"],
            ts=c.get("ts"),
            # uploaded_by removed — Caption doesn't track this
        )
        for c in data
    ]


class MediaTranscriptionStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MediaTranscriptionJob(SQLModel, table=True):
    __tablename__ = "media_transcription_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)

    meeting_id: int = Field(foreign_key="meetings.id", index=True)
    media_file_id: Optional[int] = Field(default=None, foreign_key="media_files.id", index=True)

    source_filename: str = Field(index=True)
    source_file_type: str = Field(default="audio", sa_column=Column(String, nullable=False))  # audio | video
    submitted_audio_path: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    original_media_path: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    provider: str = Field(default="whisper", index=True)
    external_job_id: Optional[str] = Field(default=None, index=True)
    callback_token: str = Field(index=True)

    status: MediaTranscriptionStatus = Field(
        default=MediaTranscriptionStatus.queued,
        sa_column=Column(Enum(MediaTranscriptionStatus), nullable=False, index=True)
    )

    transcript_text: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    raw_response: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True)
    )
    

class NotificationType(str, enum.Enum):
    transcription = "transcription"


class NotificationStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, primary_key=True)

    type: NotificationType = Field(sa_column=Column(String, nullable=False, index=True))
    status: NotificationStatus = Field(sa_column=Column(String, nullable=False, index=True))

    title: str = Field(sa_column=Column(String, nullable=False))
    message: str = Field(sa_column=Column(Text, nullable=False))

    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id", index=True)
    transcription_job_id: Optional[int] = Field(default=None, foreign_key="media_transcription_jobs.id", index=True)

    is_read: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, index=True))

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False, index=True)
    )