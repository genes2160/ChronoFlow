# app/api/models/base.py
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, DateTime, func, BigInteger, Float, String
from sqlalchemy import JSON, Enum
from enum import Enum as PyEnum


class FileTypeEnum(str, PyEnum):
    audio = "audio"
    video = "video"
    captions = "captions"
    transcript = "transcript"
    summary = "summary"
    unknown = "unknown"


class PipelineStatusEnum(str, PyEnum):
    idle = "idle"
    running = "running"
    completed = "completed"
    failed = "failed"