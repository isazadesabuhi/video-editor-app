from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class CropRequest(BaseModel):
    video_id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    quality: Literal["high", "very_high", "lossless"] = "high"
    preset: Optional[
        Literal["custom", "reels", "shorts", "tiktok", "vertical_from_crop"]
    ] = None


class DynamicCropSegment(BaseModel):
    start: str
    end: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class DetectDynamicCropsRequest(BaseModel):
    video_id: str
    threshold: float = Field(default=0.35, ge=0.05, le=1)
    min_segment_seconds: float = Field(default=2, ge=0.25, le=300)
    max_segments: int = Field(default=80, ge=1, le=300)


class DynamicCropRequest(BaseModel):
    video_id: str
    segments: List[DynamicCropSegment] = Field(min_length=1, max_length=300)
    quality: Literal["high", "very_high", "lossless"] = "high"
    output_width: int = Field(default=1920, ge=320, le=3840)
    output_height: int = Field(default=1080, ge=320, le=3840)


class YouTubeDownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    quality: Literal["720p", "1080p", "best"] = "1080p"


class CutRange(BaseModel):
    start: str
    end: str
    name: Optional[str] = Field(default=None, max_length=80)


class CutRequest(BaseModel):
    video_id: str
    cuts: List[CutRange] = Field(min_length=1, max_length=500)
    mode: Literal["copy", "accurate"] = "copy"
    quality: Literal["high", "very_high", "lossless"] = "high"


class DetectClipsRequest(BaseModel):
    video_id: str
    threshold: float = Field(default=0.35, ge=0.05, le=1)
    min_clip_seconds: float = Field(default=2, ge=0.25, le=300)
    end_trim_ms: int = Field(default=120, ge=0, le=2000)


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
