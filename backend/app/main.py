import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from re import sub
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import CropRequest, CutRequest, YouTubeDownloadRequest
from app.services.ffmpeg_service import (
    UPLOAD_DIR,
    OUTPUT_DIR,
    crop_video,
    crop_for_vertical_social,
    crop_selection_for_vertical_social,
    cut_video_copy,
    cut_video_accurate,
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

    return {
        "video_id": video_id,
        "filename": saved_path.name,
        "message": "Video uploaded successfully",
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
            if payload.preset == "vertical_from_crop":
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


def find_uploaded_video(video_id: str) -> Path:
    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))

    if not matches:
        raise HTTPException(status_code=404, detail="Video not found")

    return matches[0]


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
