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


class YouTubeDownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    quality: Literal["720p", "1080p", "best"] = "1080p"


class CutRange(BaseModel):
    start: str
    end: str
    name: Optional[str] = Field(default=None, max_length=80)


class CutRequest(BaseModel):
    video_id: str
    cuts: List[CutRange] = Field(min_length=1, max_length=100)
    mode: Literal["copy", "accurate"] = "copy"
    quality: Literal["high", "very_high", "lossless"] = "high"


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
