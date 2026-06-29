from pydantic import BaseModel, Field
from typing import List, Literal, Optional


ShortMode = Literal["fit_padding", "blur_background", "crop_fill", "manual_crop"]


class CropRequest(BaseModel):
    video_id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    quality: Literal["high", "very_high", "lossless"] = "high"
    preset: Optional[
        Literal[
            "custom",
            "reels",
            "shorts",
            "tiktok",
            "vertical_from_crop",
            "fit_padding",
            "blur_background",
            "crop_fill",
            "manual_crop",
        ]
    ] = None


class MakeShortResponse(BaseModel):
    original_filename: str
    original_width: int
    original_height: int
    output_filename: str
    output_path: str
    selected_mode: ShortMode
    final_size: str = "1080x1920"


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
    remove_black_screens: bool = False
    black_min_duration_seconds: float = Field(default=0.15, ge=0.05, le=10)
    black_pixel_threshold: float = Field(default=0.10, ge=0.01, le=1)
    black_picture_threshold: float = Field(default=0.98, ge=0.50, le=1)
    black_trim_padding_ms: int = Field(default=120, ge=0, le=2000)


class CutAndPrepareShortsRequest(CutRequest):
    shorts_mode: Literal["fit_padding", "blur_background", "crop_fill"] = (
        "blur_background"
    )
    shorts_quality: Literal["high", "very_high", "lossless"] = "high"


class BatchCutFolderRequest(BaseModel):
    folder_path: str = Field(min_length=1, max_length=4096)
    recursive: bool = False
    output_kind: Literal["cut_only", "cut_and_prepare_shorts", "shorts_only"] = (
        "cut_and_prepare_shorts"
    )
    threshold: float = Field(default=0.35, ge=0.05, le=1)
    min_clip_seconds: float = Field(default=2, ge=0.25, le=300)
    end_trim_ms: int = Field(default=120, ge=0, le=2000)
    mode: Literal["copy", "accurate"] = "accurate"
    quality: Literal["high", "very_high", "lossless"] = "very_high"
    shorts_mode: Literal["fit_padding", "blur_background", "crop_fill"] = (
        "blur_background"
    )
    shorts_quality: Literal["high", "very_high", "lossless"] = "high"
    remove_black_screens: bool = False
    black_min_duration_seconds: float = Field(default=0.15, ge=0.05, le=10)
    black_pixel_threshold: float = Field(default=0.10, ge=0.01, le=1)
    black_picture_threshold: float = Field(default=0.98, ge=0.50, le=1)
    black_trim_padding_ms: int = Field(default=120, ge=0, le=2000)
    max_videos: int = Field(default=200, ge=1, le=1000)


class CreateShortsCompilationRequest(BaseModel):
    clip_count: int = Field(default=5, ge=1, le=100)
    source_job_ids: Optional[List[str]] = None
    title: Optional[str] = Field(default=None, max_length=120)


class GenerateShortsCompilationRequest(BaseModel):
    min_duration_seconds: int = Field(default=15, ge=1, le=3600)
    max_duration_seconds: int = Field(default=60, ge=1, le=3600)
    min_clips_per_short: int = Field(default=2, ge=1, le=100)
    max_shorts: int = Field(default=10, ge=1, le=100)
    source_job_ids: Optional[List[str]] = None
    title: Optional[str] = Field(default=None, max_length=120)
    divider_video_id: Optional[str] = None


class DetectClipsRequest(BaseModel):
    video_id: str
    threshold: float = Field(default=0.35, ge=0.05, le=1)
    min_clip_seconds: float = Field(default=2, ge=0.25, le=300)
    end_trim_ms: int = Field(default=120, ge=0, le=2000)
    remove_black_screens: bool = False
    black_min_duration_seconds: float = Field(default=0.15, ge=0.05, le=10)
    black_pixel_threshold: float = Field(default=0.10, ge=0.01, le=1)
    black_picture_threshold: float = Field(default=0.98, ge=0.50, le=1)
    black_trim_padding_ms: int = Field(default=120, ge=0, le=2000)


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
