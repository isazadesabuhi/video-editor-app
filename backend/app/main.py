import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from re import sub
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import (
    CutAndPrepareShortsRequest,
    CropRequest,
    CutRequest,
    DetectDynamicCropsRequest,
    DetectClipsRequest,
    DynamicCropRequest,
    MakeShortResponse,
    ShortMode,
    YouTubeDownloadRequest,
)
from app.services.ffmpeg_service import (
    UPLOAD_DIR,
    OUTPUT_DIR,
    crop_video,
    crop_for_vertical_social,
    crop_selection_for_vertical_social,
    cut_video_copy,
    cut_video_accurate,
    detect_dynamic_crop_segments,
    detect_scene_clips,
    export_dynamic_crop_video,
    get_video_dimensions,
    process_vertical_short,
)


app = FastAPI(title="Video Editor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


JOBS = {}


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Video Editor API is running"}


@app.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed")

    video_id = str(uuid.uuid4())
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    saved_path = UPLOAD_DIR / f"{video_id}{suffix}"

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        original_width, original_height = get_video_dimensions(saved_path)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "video_id": video_id,
        "filename": saved_path.name,
        "original_width": original_width,
        "original_height": original_height,
        "message": "Video uploaded successfully",
    }


@app.post("/videos/make-short", response_model=MakeShortResponse)
async def make_short_video(
    file: UploadFile = File(...),
    mode: ShortMode = Form(...),
    x: int | None = Form(default=None),
    y: int | None = Form(default=None),
    width: int | None = Form(default=None),
    height: int | None = Form(default=None),
):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed")

    video_id = str(uuid.uuid4())
    original_filename = file.filename or "video.mp4"
    suffix = Path(original_filename).suffix or ".mp4"
    input_path = UPLOAD_DIR / f"{video_id}{suffix}"
    output_filename = f"{video_id}_{mode}.mp4"
    output_path = OUTPUT_DIR / output_filename

    with input_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        original_width, original_height = process_vertical_short(
            input_path=input_path,
            output_path=output_path,
            mode=mode,
            x=x,
            y=y,
            width=width,
            height=height,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "original_filename": original_filename,
        "original_width": original_width,
        "original_height": original_height,
        "output_filename": output_filename,
        "output_path": str(output_path),
        "selected_mode": mode,
        "final_size": "1080x1920",
    }


@app.post("/videos/youtube")
def download_youtube_video(payload: YouTubeDownloadRequest):
    video_id = str(uuid.uuid4())
    output_template = str(UPLOAD_DIR / f"{video_id}.%(ext)s")

    try:
        import yt_dlp
    except ImportError as error:
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is not installed. Run pip install -r requirements.txt.",
        ) from error

    ydl_opts = {
        "format": get_youtube_format(payload.quality),
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as downloader:
            info = downloader.extract_info(payload.url, download=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    saved_path = find_downloaded_youtube_file(video_id)

    if not saved_path:
        raise HTTPException(status_code=500, detail="Downloaded video was not found")

    return {
        "video_id": video_id,
        "filename": saved_path.name,
        "title": info.get("title") if isinstance(info, dict) else None,
        "message": "YouTube video downloaded successfully",
    }


@app.get("/videos/{video_id}/preview")
def preview_video(video_id: str):
    input_path = find_uploaded_video(video_id)
    return FileResponse(
        input_path,
        filename=input_path.name,
        media_type=get_video_media_type(input_path),
    )


@app.post("/videos/crop")
def crop_video_endpoint(payload: CropRequest, background_tasks: BackgroundTasks):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{job_id}_cropped.mp4"

    JOBS[job_id] = {
        "status": "processing",
        "output": str(output_path),
        "started_at": utc_now(),
    }

    def task():
        try:
            if payload.preset in [
                "fit_padding",
                "blur_background",
                "crop_fill",
                "manual_crop",
            ]:
                process_vertical_short(
                    input_path=input_path,
                    output_path=output_path,
                    mode=payload.preset,
                    quality=payload.quality,
                    x=payload.x,
                    y=payload.y,
                    width=payload.width,
                    height=payload.height,
                )
            elif payload.preset == "vertical_from_crop":
                crop_selection_for_vertical_social(
                    input_path=input_path,
                    output_path=output_path,
                    x=payload.x,
                    y=payload.y,
                    width=payload.width,
                    height=payload.height,
                    quality=payload.quality,
                )
            elif payload.preset in ["tiktok", "reels", "shorts"]:
                crop_for_vertical_social(
                    input_path=input_path,
                    output_path=output_path,
                    quality=payload.quality,
                )
            else:
                crop_video(
                    input_path=input_path,
                    output_path=output_path,
                    x=payload.x,
                    y=payload.y,
                    width=payload.width,
                    height=payload.height,
                    quality=payload.quality,
                )

            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Crop job started",
    }


@app.post("/videos/detect-dynamic-crops")
def detect_dynamic_crops_endpoint(payload: DetectDynamicCropsRequest):
    input_path = find_uploaded_video(payload.video_id)

    try:
        segments = detect_dynamic_crop_segments(
            input_path=input_path,
            threshold=payload.threshold,
            min_segment_seconds=payload.min_segment_seconds,
            max_segments=payload.max_segments,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "segments": segments,
        "count": len(segments),
    }


@app.post("/videos/dynamic-crop")
def dynamic_crop_endpoint(payload: DynamicCropRequest, background_tasks: BackgroundTasks):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{job_id}_dynamic_cropped.mp4"

    JOBS[job_id] = {
        "status": "processing",
        "output": str(output_path),
        "started_at": utc_now(),
    }

    def task():
        try:
            export_dynamic_crop_video(
                input_path=input_path,
                output_path=output_path,
                segments=[dump_schema(segment) for segment in payload.segments],
                quality=payload.quality,
                output_width=payload.output_width,
                output_height=payload.output_height,
            )

            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Dynamic crop job started",
    }


@app.post("/videos/cut")
def cut_video_endpoint(payload: CutRequest, background_tasks: BackgroundTasks):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    job_output_dir = OUTPUT_DIR / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)

    JOBS[job_id] = {
        "status": "processing",
        "outputs": [],
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()

            for index, cut in enumerate(payload.cuts, start=1):
                safe_name = sanitize_filename(cut.name, f"clip_{index}")
                safe_name = make_unique_name(safe_name, used_names)
                output_path = job_output_dir / f"{safe_name}.mp4"

                if payload.mode == "accurate":
                    cut_video_accurate(
                        input_path=input_path,
                        output_path=output_path,
                        start=cut.start,
                        end=cut.end,
                        quality=payload.quality,
                    )
                else:
                    cut_video_copy(
                        input_path=input_path,
                        output_path=output_path,
                        start=cut.start,
                        end=cut.end,
                    )

                JOBS[job_id]["outputs"].append(str(output_path))

            zip_path = OUTPUT_DIR / f"{job_id}_clips.zip"
            create_zip_archive(zip_path, [Path(output) for output in JOBS[job_id]["outputs"]])

            JOBS[job_id]["archive"] = str(zip_path)
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Cut job started",
    }


@app.post("/videos/cut-and-prepare-shorts")
def cut_and_prepare_shorts_endpoint(
    payload: CutAndPrepareShortsRequest,
    background_tasks: BackgroundTasks,
):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    job_output_dir = OUTPUT_DIR / job_id
    cut_output_dir = job_output_dir / "cut_clips"
    shorts_output_dir = job_output_dir / "shorts_clips"
    cut_output_dir.mkdir(parents=True, exist_ok=True)
    shorts_output_dir.mkdir(parents=True, exist_ok=True)

    JOBS[job_id] = {
        "status": "processing",
        "cut_outputs": [],
        "shorts_outputs": [],
        "cut_output_dir": str(cut_output_dir),
        "shorts_output_dir": str(shorts_output_dir),
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()

            for index, cut in enumerate(payload.cuts, start=1):
                safe_name = sanitize_filename(cut.name, f"clip_{index}")
                safe_name = make_unique_name(safe_name, used_names)
                cut_output_path = cut_output_dir / f"{safe_name}.mp4"
                shorts_output_path = shorts_output_dir / f"{safe_name}_short.mp4"

                if payload.mode == "accurate":
                    cut_video_accurate(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=cut.start,
                        end=cut.end,
                        quality=payload.quality,
                    )
                else:
                    cut_video_copy(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=cut.start,
                        end=cut.end,
                    )

                process_vertical_short(
                    input_path=cut_output_path,
                    output_path=shorts_output_path,
                    mode=payload.shorts_mode,
                    quality=payload.shorts_quality,
                )

                JOBS[job_id]["cut_outputs"].append(str(cut_output_path))
                JOBS[job_id]["shorts_outputs"].append(str(shorts_output_path))

            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Cut and Shorts preparation job started",
    }


@app.post("/videos/cut-to-shorts")
def cut_to_shorts_endpoint(
    payload: CutAndPrepareShortsRequest,
    background_tasks: BackgroundTasks,
):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    job_output_dir = OUTPUT_DIR / job_id
    shorts_output_dir = job_output_dir / "shorts_clips"
    shorts_output_dir.mkdir(parents=True, exist_ok=True)

    JOBS[job_id] = {
        "status": "processing",
        "shorts_outputs": [],
        "shorts_output_dir": str(shorts_output_dir),
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()

            with tempfile.TemporaryDirectory(prefix=f"{job_id}_cuts_") as temp_dir:
                temp_path = Path(temp_dir)

                for index, cut in enumerate(payload.cuts, start=1):
                    safe_name = sanitize_filename(cut.name, f"clip_{index}")
                    safe_name = make_unique_name(safe_name, used_names)
                    temp_cut_path = temp_path / f"{safe_name}.mp4"
                    shorts_output_path = shorts_output_dir / f"{safe_name}_short.mp4"

                    if payload.mode == "accurate":
                        cut_video_accurate(
                            input_path=input_path,
                            output_path=temp_cut_path,
                            start=cut.start,
                            end=cut.end,
                            quality=payload.quality,
                        )
                    else:
                        cut_video_copy(
                            input_path=input_path,
                            output_path=temp_cut_path,
                            start=cut.start,
                            end=cut.end,
                        )

                    process_vertical_short(
                        input_path=temp_cut_path,
                        output_path=shorts_output_path,
                        mode=payload.shorts_mode,
                        quality=payload.shorts_quality,
                    )

                    JOBS[job_id]["shorts_outputs"].append(str(shorts_output_path))

            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Shorts-only preparation job started",
    }


@app.post("/videos/detect-clips")
def detect_clips_endpoint(payload: DetectClipsRequest):
    input_path = find_uploaded_video(payload.video_id)

    try:
        clips = detect_scene_clips(
            input_path=input_path,
            threshold=payload.threshold,
            min_clip_seconds=payload.min_clip_seconds,
            end_trim_ms=payload.end_trim_ms,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "clips": clips,
        "count": len(clips),
    }


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    job = JOBS.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    refresh_job_status(job)

    return job


@app.get("/download/{job_id}")
def download_result(job_id: str):
    job = JOBS.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    refresh_job_status(job)

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job is not finished yet")

    if "output" in job:
        return FileResponse(job["output"], filename=Path(job["output"]).name)

    if "archive" in job:
        return FileResponse(job["archive"], filename=Path(job["archive"]).name)

    raise HTTPException(status_code=404, detail="No downloadable output found")


@app.get("/download/{job_id}/raw")
def download_raw_cut_result(job_id: str):
    job = JOBS.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    refresh_job_status(job)

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job is not finished yet")

    raw_archive = job.get("raw_archive")

    if not raw_archive:
        raise HTTPException(status_code=404, detail="No raw cut archive found")

    return FileResponse(raw_archive, filename=Path(raw_archive).name)


def find_uploaded_video(video_id: str) -> Path:
    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))

    if not matches:
        raise HTTPException(status_code=404, detail="Video not found")

    return matches[0]


def dump_schema(schema):
    if hasattr(schema, "model_dump"):
        return schema.model_dump()

    return schema.dict()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_job_status(job: dict) -> None:
    if job.get("status") != "processing":
        return

    output = job.get("output")
    if output and has_stable_output_size(job, Path(output), "output"):
        job["status"] = "done"
        job["finished_at"] = utc_now()
        return

    archive = job.get("archive")
    if archive and has_stable_output_size(job, Path(archive), "archive"):
        job["status"] = "done"
        job["finished_at"] = utc_now()


def has_stable_output_size(job: dict, path: Path, key: str) -> bool:
    if not path.exists() or not path.is_file():
        return False

    size = path.stat().st_size
    size_key = f"{key}_observed_size"
    time_key = f"{key}_observed_at"
    previous_size = job.get(size_key)
    observed_at = job.get(time_key)
    job[size_key] = size

    if previous_size != size:
        job[time_key] = time.monotonic()
        return False

    return size > 0 and isinstance(observed_at, float) and time.monotonic() - observed_at >= 3


def get_youtube_format(quality: str) -> str:
    formats = {
        "720p": "bv*[height<=720]+ba/b[height<=720]/best[height<=720]",
        "1080p": "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]",
        "best": "bv*+ba/best",
    }
    return formats.get(quality, formats["1080p"])


def find_downloaded_youtube_file(video_id: str) -> Path | None:
    matches = sorted(
        UPLOAD_DIR.glob(f"{video_id}.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def get_video_media_type(video_path: Path) -> str:
    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }
    return media_types.get(video_path.suffix.lower(), "application/octet-stream")


def sanitize_filename(name: str | None, fallback: str) -> str:
    base = Path(name or fallback).stem
    safe = sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return safe or fallback


def make_unique_name(name: str, used_names: set[str]) -> str:
    candidate = name
    suffix = 2

    while candidate in used_names:
        candidate = f"{name}_{suffix}"
        suffix += 1

    used_names.add(candidate)
    return candidate


def create_zip_archive(zip_path: Path, files: list[Path]) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for file_path in files:
            if file_path.exists():
                archive.write(file_path, arcname=file_path.name)
