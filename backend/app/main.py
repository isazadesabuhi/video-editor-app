import shutil
import uuid
from pathlib import Path
from re import sub
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import CropRequest, CutRequest
from app.services.ffmpeg_service import (
    UPLOAD_DIR,
    OUTPUT_DIR,
    crop_video,
    crop_for_vertical_social,
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


@app.post("/videos/crop")
def crop_video_endpoint(payload: CropRequest, background_tasks: BackgroundTasks):
    input_path = find_uploaded_video(payload.video_id)

    job_id = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{job_id}_cropped.mp4"

    JOBS[job_id] = {
        "status": "processing",
        "output": str(output_path),
    }

    def task():
        try:
            if payload.preset in ["tiktok", "reels", "shorts"]:
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

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)

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

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)

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

    return job


@app.get("/download/{job_id}")
def download_result(job_id: str):
    job = JOBS.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
