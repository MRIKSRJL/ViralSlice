from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.pipeline.download import is_supported_url


class CommentaryMode(str, Enum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class JobStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    DETECTING_MOMENTS = "detecting_moments"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class Word(BaseModel):
    text: str
    start: float
    end: float


class ViralMoment(BaseModel):
    start: float
    end: float
    title: str
    reason: str
    needs_commentary: bool
    commentary_script: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


class ClipResult(BaseModel):
    index: int
    start: float
    end: float
    title: str
    reason: str
    needs_commentary: bool
    commentary_script: str | None
    has_voiceover: bool
    filename: str
    download_url: str


class ProcessVideoRequest(BaseModel):
    url: HttpUrl
    commentary_mode: CommentaryMode = CommentaryMode.AUTO

    @field_validator("url")
    @classmethod
    def _check_platform(cls, value: HttpUrl) -> HttpUrl:
        if not is_supported_url(str(value)):
            raise ValueError("Seules les URL YouTube et Twitch sont acceptées.")
        return value


class ProcessVideoResponse(BaseModel):
    job_id: str
    status: JobStatus


def _now() -> datetime:
    return datetime.now(UTC)


class JobState(BaseModel):
    job_id: str
    url: str
    commentary_mode: CommentaryMode
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    source_title: str | None = None
    source_duration: float | None = None
    moments: list[ViralMoment] = Field(default_factory=list)
    clips: list[ClipResult] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
