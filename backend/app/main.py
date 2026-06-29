import json
import random
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from re import sub
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import (
    BatchCutFolderRequest,
    CreateShortsCompilationRequest,
    CutAndPrepareShortsRequest,
    CropRequest,
    CutRequest,
    DetectDynamicCropsRequest,
    DetectClipsRequest,
    DynamicCropRequest,
    GenerateShortsCompilationRequest,
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
    cut_video_without_black_screens,
    detect_black_ranges,
    detect_dynamic_crop_segments,
    detect_scene_clips,
    export_dynamic_crop_video,
    get_video_duration,
    get_video_dimensions,
    process_vertical_short,
    run_command,
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
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Video Editor API is running"}


@app.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed")

    video_id = str(uuid.uuid4())
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    temp_path = UPLOAD_DIR / f"{video_id}.uploading{suffix}"
    saved_path = UPLOAD_DIR / f"{video_id}{suffix}"

    file_hash = save_upload_with_hash(file, temp_path)

    duplicate = find_duplicate_upload(file_hash, temp_path)

    if duplicate:
        temp_path.unlink(missing_ok=True)

        return {
            "video_id": duplicate["video_id"],
            "filename": duplicate["filename"],
            "original_width": duplicate["original_width"],
            "original_height": duplicate["original_height"],
            "duplicate": True,
            "message": "Video already uploaded. Using existing file.",
        }

    temp_path.replace(saved_path)

    try:
        original_width, original_height = get_video_dimensions(saved_path)
    except Exception as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error

    register_uploaded_video(
        video_id=video_id,
        saved_path=saved_path,
        file_hash=file_hash,
        original_width=original_width,
        original_height=original_height,
    )

    return {
        "video_id": video_id,
        "filename": saved_path.name,
        "original_width": original_width,
        "original_height": original_height,
        "duplicate": False,
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
def download_youtube_video(
    payload: YouTubeDownloadRequest,
    background_tasks: BackgroundTasks,
):
    video_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    output_template = str(UPLOAD_DIR / f"{video_id}.%(ext)s")

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "current_step": "Waiting to start YouTube download",
        "video_id": video_id,
        "started_at": utc_now(),
    }

    def progress_hook(status: dict) -> None:
        if status.get("status") == "downloading":
            downloaded = status.get("downloaded_bytes") or 0
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0

            if total:
                progress = max(1, min(90, round((downloaded / total) * 90)))
                set_job_progress(job_id, progress, "Downloading from YouTube")
            else:
                set_job_progress(job_id, 5, "Downloading from YouTube")

        elif status.get("status") == "finished":
            set_job_progress(job_id, 92, "Merging and checking downloaded video")

    def task():
        try:
            try:
                import yt_dlp
            except ImportError as error:
                raise RuntimeError(
                    "yt-dlp is not installed. Run pip install -r requirements.txt."
                ) from error

            ydl_opts = {
                "format": get_youtube_format(payload.quality),
                "outtmpl": output_template,
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [progress_hook],
            }

            set_job_progress(job_id, 1, "Starting YouTube download")

            with yt_dlp.YoutubeDL(ydl_opts) as downloader:
                info = downloader.extract_info(payload.url, download=True)

            saved_path = find_downloaded_youtube_file(video_id)

            if not saved_path:
                raise RuntimeError("Downloaded video was not found")

            original_width, original_height = get_video_dimensions(saved_path)
            file_hash = hash_file(saved_path)
            register_uploaded_video(
                video_id=video_id,
                saved_path=saved_path,
                file_hash=file_hash,
                original_width=original_width,
                original_height=original_height,
            )

            JOBS[job_id]["video_id"] = video_id
            JOBS[job_id]["filename"] = saved_path.name
            JOBS[job_id]["title"] = info.get("title") if isinstance(info, dict) else None
            JOBS[job_id]["original_width"] = original_width
            JOBS[job_id]["original_height"] = original_height
            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "YouTube download finished")
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "YouTube download job started",
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
        "progress": 0,
        "current_step": "Waiting to start crop",
        "started_at": utc_now(),
    }

    def task():
        try:
            set_job_progress(job_id, 10, "Processing crop")

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
            set_job_progress(job_id, 100, "Crop finished")
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
        "progress": 0,
        "current_step": "Waiting to start dynamic crop",
        "started_at": utc_now(),
    }

    def task():
        try:
            set_job_progress(job_id, 10, "Processing dynamic crop")

            export_dynamic_crop_video(
                input_path=input_path,
                output_path=output_path,
                segments=[dump_schema(segment) for segment in payload.segments],
                quality=payload.quality,
                output_width=payload.output_width,
                output_height=payload.output_height,
            )

            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Dynamic crop finished")
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
        "progress": 0,
        "current_step": "Waiting to start cuts",
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()
            total_cuts = len(payload.cuts)
            black_ranges = (
                detect_black_ranges(
                    input_path=input_path,
                    min_duration_seconds=payload.black_min_duration_seconds,
                    pixel_threshold=payload.black_pixel_threshold,
                    picture_threshold=payload.black_picture_threshold,
                    trim_padding_seconds=payload.black_trim_padding_ms / 1000,
                )
                if payload.remove_black_screens
                else None
            )

            for index, cut in enumerate(payload.cuts, start=1):
                safe_name = sanitize_filename(cut.name, f"clip_{index}")
                safe_name = make_unique_name(safe_name, used_names)
                output_path = job_output_dir / f"{safe_name}.mp4"
                set_job_progress(
                    job_id,
                    round(((index - 1) / total_cuts) * 95),
                    f"Cutting clip {index} of {total_cuts}",
                )

                if payload.remove_black_screens:
                    cut_video_without_black_screens(
                        input_path=input_path,
                        output_path=output_path,
                        start=cut.start,
                        end=cut.end,
                        quality=payload.quality,
                        black_ranges=black_ranges,
                        black_min_duration_seconds=payload.black_min_duration_seconds,
                        black_pixel_threshold=payload.black_pixel_threshold,
                        black_picture_threshold=payload.black_picture_threshold,
                        black_trim_padding_ms=payload.black_trim_padding_ms,
                    )
                elif payload.mode == "accurate":
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
                set_job_progress(
                    job_id,
                    round((index / total_cuts) * 95),
                    f"Finished clip {index} of {total_cuts}",
                )

            set_job_progress(job_id, 96, "Creating clip archive")
            zip_path = OUTPUT_DIR / f"{job_id}_clips.zip"
            create_zip_archive(zip_path, [Path(output) for output in JOBS[job_id]["outputs"]])

            JOBS[job_id]["archive"] = str(zip_path)
            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Cut export finished")
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
        "progress": 0,
        "current_step": "Waiting to start cuts",
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()
            total_steps = len(payload.cuts) * 2
            completed_steps = 0
            black_ranges = (
                detect_black_ranges(
                    input_path=input_path,
                    min_duration_seconds=payload.black_min_duration_seconds,
                    pixel_threshold=payload.black_pixel_threshold,
                    picture_threshold=payload.black_picture_threshold,
                    trim_padding_seconds=payload.black_trim_padding_ms / 1000,
                )
                if payload.remove_black_screens
                else None
            )

            for index, cut in enumerate(payload.cuts, start=1):
                safe_name = sanitize_filename(cut.name, f"clip_{index}")
                safe_name = make_unique_name(safe_name, used_names)
                cut_output_path = cut_output_dir / f"{safe_name}.mp4"
                shorts_output_path = shorts_output_dir / f"{safe_name}_short.mp4"
                set_job_progress(
                    job_id,
                    round((completed_steps / total_steps) * 100),
                    f"Cutting clip {index} of {len(payload.cuts)}",
                )

                if payload.remove_black_screens:
                    cut_video_without_black_screens(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=cut.start,
                        end=cut.end,
                        quality=payload.quality,
                        black_ranges=black_ranges,
                        black_min_duration_seconds=payload.black_min_duration_seconds,
                        black_pixel_threshold=payload.black_pixel_threshold,
                        black_picture_threshold=payload.black_picture_threshold,
                        black_trim_padding_ms=payload.black_trim_padding_ms,
                    )
                elif payload.mode == "accurate":
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

                completed_steps += 1
                set_job_progress(
                    job_id,
                    round((completed_steps / total_steps) * 100),
                    f"Preparing Shorts clip {index} of {len(payload.cuts)}",
                )

                process_vertical_short(
                    input_path=cut_output_path,
                    output_path=shorts_output_path,
                    mode=payload.shorts_mode,
                    quality=payload.shorts_quality,
                )

                JOBS[job_id]["cut_outputs"].append(str(cut_output_path))
                JOBS[job_id]["shorts_outputs"].append(str(shorts_output_path))
                completed_steps += 1
                set_job_progress(
                    job_id,
                    round((completed_steps / total_steps) * 100),
                    f"Finished Shorts clip {index} of {len(payload.cuts)}",
                )

            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Cut and Shorts preparation finished")
            JOBS[job_id]["finished_at"] = utc_now()
            write_shorts_job_manifest(
                job_id=job_id,
                input_path=input_path,
                job_output_dir=job_output_dir,
                shorts_output_dir=shorts_output_dir,
                cuts=[dump_schema(cut) for cut in payload.cuts],
                shorts_outputs=[
                    Path(output) for output in JOBS[job_id]["shorts_outputs"]
                ],
                cut_output_dir=cut_output_dir,
                cut_outputs=[Path(output) for output in JOBS[job_id]["cut_outputs"]],
                shorts_mode=payload.shorts_mode,
                shorts_quality=payload.shorts_quality,
            )

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
        "progress": 0,
        "current_step": "Waiting to start Shorts",
        "started_at": utc_now(),
    }

    def task():
        try:
            used_names: set[str] = set()
            total_steps = len(payload.cuts) * 2
            completed_steps = 0
            black_ranges = (
                detect_black_ranges(
                    input_path=input_path,
                    min_duration_seconds=payload.black_min_duration_seconds,
                    pixel_threshold=payload.black_pixel_threshold,
                    picture_threshold=payload.black_picture_threshold,
                    trim_padding_seconds=payload.black_trim_padding_ms / 1000,
                )
                if payload.remove_black_screens
                else None
            )

            with tempfile.TemporaryDirectory(prefix=f"{job_id}_cuts_") as temp_dir:
                temp_path = Path(temp_dir)

                for index, cut in enumerate(payload.cuts, start=1):
                    safe_name = sanitize_filename(cut.name, f"clip_{index}")
                    safe_name = make_unique_name(safe_name, used_names)
                    temp_cut_path = temp_path / f"{safe_name}.mp4"
                    shorts_output_path = shorts_output_dir / f"{safe_name}_short.mp4"
                    set_job_progress(
                        job_id,
                        round((completed_steps / total_steps) * 100),
                        f"Cutting temporary clip {index} of {len(payload.cuts)}",
                    )

                    if payload.remove_black_screens:
                        cut_video_without_black_screens(
                            input_path=input_path,
                            output_path=temp_cut_path,
                            start=cut.start,
                            end=cut.end,
                            quality=payload.quality,
                            black_ranges=black_ranges,
                            black_min_duration_seconds=payload.black_min_duration_seconds,
                            black_pixel_threshold=payload.black_pixel_threshold,
                            black_picture_threshold=payload.black_picture_threshold,
                            black_trim_padding_ms=payload.black_trim_padding_ms,
                        )
                    elif payload.mode == "accurate":
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

                    completed_steps += 1
                    set_job_progress(
                        job_id,
                        round((completed_steps / total_steps) * 100),
                        f"Preparing Shorts clip {index} of {len(payload.cuts)}",
                    )

                    process_vertical_short(
                        input_path=temp_cut_path,
                        output_path=shorts_output_path,
                        mode=payload.shorts_mode,
                        quality=payload.shorts_quality,
                    )

                    JOBS[job_id]["shorts_outputs"].append(str(shorts_output_path))
                    completed_steps += 1
                    set_job_progress(
                        job_id,
                        round((completed_steps / total_steps) * 100),
                        f"Finished Shorts clip {index} of {len(payload.cuts)}",
                    )

            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Shorts-only preparation finished")
            JOBS[job_id]["finished_at"] = utc_now()
            write_shorts_job_manifest(
                job_id=job_id,
                input_path=input_path,
                job_output_dir=job_output_dir,
                shorts_output_dir=shorts_output_dir,
                cuts=[dump_schema(cut) for cut in payload.cuts],
                shorts_outputs=[
                    Path(output) for output in JOBS[job_id]["shorts_outputs"]
                ],
                shorts_mode=payload.shorts_mode,
                shorts_quality=payload.shorts_quality,
            )

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


@app.post("/videos/batch-cut-folder")
def batch_cut_folder_endpoint(
    payload: BatchCutFolderRequest,
    background_tasks: BackgroundTasks,
):
    folder_path = Path(payload.folder_path).expanduser()

    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=400, detail="Folder was not found")

    video_paths = find_video_files_in_folder(
        folder_path,
        recursive=payload.recursive,
        max_videos=payload.max_videos,
    )

    if not video_paths:
        raise HTTPException(status_code=400, detail="No video files were found")

    job_id = str(uuid.uuid4())
    job_output_dir = OUTPUT_DIR / job_id
    cut_output_dir = job_output_dir / "cut_clips"
    shorts_output_dir = job_output_dir / "shorts_clips"

    if payload.output_kind != "shorts_only":
        cut_output_dir.mkdir(parents=True, exist_ok=True)

    if payload.output_kind != "cut_only":
        shorts_output_dir.mkdir(parents=True, exist_ok=True)

    job: dict = {
        "status": "processing",
        "progress": 0,
        "current_step": "Waiting to start batch cut",
        "source_folder": str(folder_path),
        "total_videos": len(video_paths),
        "processed_videos_count": 0,
        "skipped_clips_count": 0,
        "cut_outputs": [],
        "shorts_outputs": [],
        "started_at": utc_now(),
    }

    if payload.output_kind != "shorts_only":
        job["cut_output_dir"] = str(cut_output_dir)

    if payload.output_kind != "cut_only":
        job["shorts_output_dir"] = str(shorts_output_dir)

    JOBS[job_id] = job

    def task():
        skipped_items = []
        source_manifests = []
        used_names: set[str] = set()

        try:
            for video_index, input_path in enumerate(video_paths, start=1):
                set_job_progress(
                    job_id,
                    round(((video_index - 1) / len(video_paths)) * 98),
                    f"Processing {video_index} of {len(video_paths)}: {input_path.name}",
                )

                try:
                    source_manifest = process_batch_source_video(
                        input_path=input_path,
                        cut_output_dir=cut_output_dir,
                        shorts_output_dir=shorts_output_dir,
                        payload=payload,
                        used_names=used_names,
                    )
                except Exception as error:
                    skipped_items.append(
                        {
                            "source_path": str(input_path),
                            "reason": str(error),
                        }
                    )
                    continue

                source_manifests.append(source_manifest)
                skipped_items.extend(source_manifest["skipped_items"])
                JOBS[job_id]["processed_videos_count"] = len(source_manifests)
                JOBS[job_id]["cut_outputs"].extend(
                    output["path"] for output in source_manifest["cut_outputs"]
                )
                JOBS[job_id]["shorts_outputs"].extend(
                    output["path"] for output in source_manifest["shorts_outputs"]
                )

            if not source_manifests:
                raise RuntimeError("No videos were processed successfully")

            manifest = {
                "job_id": job_id,
                "source_folder": str(folder_path),
                "created_at": utc_now(),
                "output_kind": payload.output_kind,
                "cut_output_dir": (
                    str(cut_output_dir) if payload.output_kind != "shorts_only" else None
                ),
                "shorts_output_dir": (
                    str(shorts_output_dir) if payload.output_kind != "cut_only" else None
                ),
                "shorts_mode": payload.shorts_mode,
                "shorts_quality": payload.shorts_quality,
                "sources": source_manifests,
                "skipped_items": skipped_items,
            }
            manifest_path = job_output_dir / "source_info.json"
            write_json_file(manifest_path, manifest)

            JOBS[job_id]["manifest_path"] = str(manifest_path)
            JOBS[job_id]["skipped_clips_count"] = len(skipped_items)
            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Batch cut finished")
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["skipped_items"] = skipped_items
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"Batch cut started for {len(video_paths)} video files",
        "video_count": len(video_paths),
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
            remove_black_screens=payload.remove_black_screens,
            black_min_duration_seconds=payload.black_min_duration_seconds,
            black_pixel_threshold=payload.black_pixel_threshold,
            black_picture_threshold=payload.black_picture_threshold,
            black_trim_padding_ms=payload.black_trim_padding_ms,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "clips": clips,
        "count": len(clips),
    }


@app.get("/shorts-library")
def list_shorts_library():
    jobs = list_shorts_jobs()

    return {
        "jobs": jobs,
        "total_jobs": len(jobs),
        "total_clips": sum(len(job["clips"]) for job in jobs),
    }


@app.post("/shorts-compilations/draft")
def create_shorts_compilation_draft(payload: CreateShortsCompilationRequest):
    clips = list_shorts_clips(payload.source_job_ids)

    if not clips:
        raise HTTPException(status_code=400, detail="No shorts clips were found")

    selected_count = min(payload.clip_count, len(clips))
    selected_clips = random.sample(clips, selected_count)

    compilation_id = str(uuid.uuid4())
    compilation_dir = OUTPUT_DIR / "compilations" / compilation_id
    selected_dir = compilation_dir / "selected_clips"
    selected_dir.mkdir(parents=True, exist_ok=True)

    manifest_clips = []
    for index, clip in enumerate(selected_clips, start=1):
        source_path = Path(clip["path"])
        output_filename = (
            f"{index:03d}_{sanitize_filename(clip['job_id'], 'job')}_"
            f"{sanitize_filename(source_path.stem, f'clip_{index}')}.mp4"
        )
        output_path = selected_dir / output_filename
        shutil.copy2(source_path, output_path)

        manifest_clips.append(
            {
                "order": index,
                "source_job_id": clip["job_id"],
                "source_filename": source_path.name,
                "source_path": str(source_path),
                "selected_filename": output_filename,
                "selected_path": str(output_path),
            }
        )

    manifest = {
        "compilation_id": compilation_id,
        "title": payload.title or f"shorts_compilation_{compilation_id}",
        "created_at": utc_now(),
        "status": "draft",
        "selected_dir": str(selected_dir),
        "final_output": str(compilation_dir / "final.mp4"),
        "clips": manifest_clips,
    }
    manifest_path = compilation_dir / "manifest.json"
    write_json_file(manifest_path, manifest)

    return {
        "compilation_id": compilation_id,
        "selected_count": selected_count,
        "selected_dir": str(selected_dir),
        "manifest_path": str(manifest_path),
        "final_output": str(compilation_dir / "final.mp4"),
        "clips": manifest_clips,
    }


@app.post("/shorts-compilations/generate")
def generate_shorts_compilations_endpoint(
    payload: GenerateShortsCompilationRequest,
    background_tasks: BackgroundTasks,
):
    if payload.min_duration_seconds > payload.max_duration_seconds:
        raise HTTPException(
            status_code=400,
            detail="Minimum duration cannot be greater than maximum duration",
        )

    clips = list_shorts_clips(payload.source_job_ids)

    if not clips:
        raise HTTPException(status_code=400, detail="No shorts clips were found")

    divider_path = (
        find_uploaded_video(payload.divider_video_id)
        if payload.divider_video_id
        else None
    )

    job_id = str(uuid.uuid4())
    compilation_dir = OUTPUT_DIR / "compilations" / job_id
    compilation_dir.mkdir(parents=True, exist_ok=True)

    JOBS[job_id] = {
        "status": "processing",
        "progress": 0,
        "current_step": "Waiting to generate final Shorts",
        "compilation_dir": str(compilation_dir),
        "final_outputs": [],
        "started_at": utc_now(),
    }

    def task():
        try:
            set_job_progress(job_id, 5, "Reading clip durations")
            divider_duration = (
                get_video_duration(divider_path) if divider_path is not None else 0.0
            )
            eligible_clips, skipped_clips = collect_eligible_shorts_clips(
                clips,
                max_duration_seconds=payload.max_duration_seconds,
            )

            groups, unused_clips = build_random_shorts_groups(
                eligible_clips,
                min_duration_seconds=payload.min_duration_seconds,
                max_duration_seconds=payload.max_duration_seconds,
                min_clips_per_short=payload.min_clips_per_short,
                max_shorts=payload.max_shorts,
                divider_duration_seconds=divider_duration,
            )
            skipped_clips.extend(unused_clips)

            if not groups:
                raise RuntimeError(
                    "Could not build any Shorts with the selected duration and minimum clip rules"
                )

            shorts_dir = compilation_dir / "shorts"
            shorts_dir.mkdir(parents=True, exist_ok=True)
            divider_concat_path = None

            if divider_path is not None:
                divider_concat_path = compilation_dir / "divider_normalized.mp4"
                process_vertical_short(
                    input_path=divider_path,
                    output_path=divider_concat_path,
                    mode="fit_padding",
                    quality="high",
                )

            manifest_shorts = []
            total_groups = len(groups)

            for group_index, group in enumerate(groups, start=1):
                set_job_progress(
                    job_id,
                    10 + round(((group_index - 1) / total_groups) * 85),
                    f"Creating final Short {group_index} of {total_groups}",
                )
                short_dir = shorts_dir / f"short_{group_index:03d}"
                selected_dir = short_dir / "selected_clips"
                selected_dir.mkdir(parents=True, exist_ok=True)
                selected_paths = []
                selected_manifest = []

                for clip_index, clip in enumerate(group["clips"], start=1):
                    source_path = Path(clip["path"])
                    output_filename = (
                        f"{clip_index:03d}_{sanitize_filename(clip['job_id'], 'job')}_"
                        f"{sanitize_filename(source_path.stem, f'clip_{clip_index}')}.mp4"
                    )
                    output_path = selected_dir / output_filename
                    shutil.copy2(source_path, output_path)
                    selected_paths.append(output_path)
                    selected_manifest.append(
                        {
                            "order": clip_index,
                            "source_job_id": clip["job_id"],
                            "source_filename": source_path.name,
                            "source_path": str(source_path),
                            "selected_filename": output_filename,
                            "selected_path": str(output_path),
                            "duration_seconds": clip["duration_seconds"],
                        }
                    )

                    if divider_concat_path is not None and clip_index < len(group["clips"]):
                        divider_filename = f"{clip_index:03d}_divider.mp4"
                        divider_output_path = selected_dir / divider_filename
                        shutil.copy2(divider_concat_path, divider_output_path)
                        selected_paths.append(divider_output_path)
                        selected_manifest.append(
                            {
                                "order": f"{clip_index}.divider",
                                "type": "divider",
                                "source_video_id": payload.divider_video_id,
                                "source_filename": divider_path.name,
                                "source_path": str(divider_path),
                                "selected_filename": divider_filename,
                                "selected_path": str(divider_output_path),
                                "duration_seconds": round(divider_duration, 3),
                            }
                        )

                final_output = short_dir / "final.mp4"
                concatenate_video_files(selected_paths, final_output)
                JOBS[job_id]["final_outputs"].append(str(final_output))
                manifest_shorts.append(
                    {
                        "index": group_index,
                        "duration_seconds": group["duration_seconds"],
                        "clip_count": len(group["clips"]),
                        "selected_dir": str(selected_dir),
                        "final_output": str(final_output),
                        "clips": selected_manifest,
                    }
                )

            manifest = {
                "compilation_id": job_id,
                "title": payload.title or f"shorts_compilation_{job_id}",
                "created_at": utc_now(),
                "status": "generated",
                "rules": {
                    "min_duration_seconds": payload.min_duration_seconds,
                    "max_duration_seconds": payload.max_duration_seconds,
                    "min_clips_per_short": payload.min_clips_per_short,
                    "max_shorts": payload.max_shorts,
                    "divider_video_id": payload.divider_video_id,
                    "divider_duration_seconds": round(divider_duration, 3),
                },
                "compilation_dir": str(compilation_dir),
                "shorts_dir": str(shorts_dir),
                "shorts": manifest_shorts,
                "skipped_clips": skipped_clips,
            }
            manifest_path = compilation_dir / "manifest.json"
            write_json_file(manifest_path, manifest)

            JOBS[job_id]["manifest_path"] = str(manifest_path)
            JOBS[job_id]["shorts_dir"] = str(shorts_dir)
            JOBS[job_id]["generated_shorts_count"] = len(manifest_shorts)
            JOBS[job_id]["skipped_clips_count"] = len(skipped_clips)
            JOBS[job_id]["status"] = "done"
            set_job_progress(job_id, 100, "Final Shorts generated")
            JOBS[job_id]["finished_at"] = utc_now()

        except Exception as error:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(error)
            JOBS[job_id]["finished_at"] = utc_now()

    background_tasks.add_task(task)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Final Shorts generation job started",
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


def find_video_files_in_folder(
    folder_path: Path,
    recursive: bool,
    max_videos: int,
) -> list[Path]:
    candidates = folder_path.rglob("*") if recursive else folder_path.iterdir()
    video_paths = [
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]

    return sorted(video_paths, key=lambda path: path.name.lower())[:max_videos]


def process_batch_source_video(
    input_path: Path,
    cut_output_dir: Path,
    shorts_output_dir: Path,
    payload: BatchCutFolderRequest,
    used_names: set[str],
) -> dict:
    source_name = sanitize_filename(input_path.stem, "video")
    cuts = detect_scene_clips(
        input_path=input_path,
        threshold=payload.threshold,
        min_clip_seconds=payload.min_clip_seconds,
        end_trim_ms=payload.end_trim_ms,
        remove_black_screens=payload.remove_black_screens,
        black_min_duration_seconds=payload.black_min_duration_seconds,
        black_pixel_threshold=payload.black_pixel_threshold,
        black_picture_threshold=payload.black_picture_threshold,
        black_trim_padding_ms=payload.black_trim_padding_ms,
    )
    black_ranges = (
        detect_black_ranges(
            input_path=input_path,
            min_duration_seconds=payload.black_min_duration_seconds,
            pixel_threshold=payload.black_pixel_threshold,
            picture_threshold=payload.black_picture_threshold,
            trim_padding_seconds=payload.black_trim_padding_ms / 1000,
        )
        if payload.remove_black_screens
        else None
    )

    cut_outputs = []
    shorts_outputs = []
    skipped_items = []

    with tempfile.TemporaryDirectory(prefix=f"{source_name}_batch_cuts_") as temp_dir:
        temp_path = Path(temp_dir)

        for cut_index, cut in enumerate(cuts, start=1):
            cut_name = sanitize_filename(cut.get("name"), f"clip_{cut_index}")
            output_name = make_unique_name(f"{source_name}_{cut_name}", used_names)
            cut_output_path = (
                cut_output_dir / f"{output_name}.mp4"
                if payload.output_kind != "shorts_only"
                else temp_path / f"{output_name}.mp4"
            )

            try:
                if payload.remove_black_screens:
                    cut_video_without_black_screens(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=str(cut["start"]),
                        end=str(cut["end"]),
                        quality=payload.quality,
                        black_ranges=black_ranges,
                        black_min_duration_seconds=payload.black_min_duration_seconds,
                        black_pixel_threshold=payload.black_pixel_threshold,
                        black_picture_threshold=payload.black_picture_threshold,
                        black_trim_padding_ms=payload.black_trim_padding_ms,
                    )
                elif payload.mode == "accurate":
                    cut_video_accurate(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=str(cut["start"]),
                        end=str(cut["end"]),
                        quality=payload.quality,
                    )
                else:
                    cut_video_copy(
                        input_path=input_path,
                        output_path=cut_output_path,
                        start=str(cut["start"]),
                        end=str(cut["end"]),
                    )

                if payload.output_kind != "shorts_only":
                    cut_outputs.append(
                        {
                            "filename": cut_output_path.name,
                            "path": str(cut_output_path),
                            "cut": cut,
                        }
                    )

                if payload.output_kind != "cut_only":
                    shorts_output_path = shorts_output_dir / f"{output_name}_short.mp4"
                    process_vertical_short(
                        input_path=cut_output_path,
                        output_path=shorts_output_path,
                        mode=payload.shorts_mode,
                        quality=payload.shorts_quality,
                    )
                    shorts_outputs.append(
                        {
                            "filename": shorts_output_path.name,
                            "path": str(shorts_output_path),
                            "cut": cut,
                            "raw_cut_filename": (
                                cut_output_path.name
                                if payload.output_kind != "shorts_only"
                                else None
                            ),
                            "raw_cut_path": (
                                str(cut_output_path)
                                if payload.output_kind != "shorts_only"
                                else None
                            ),
                        }
                    )
            except Exception as error:
                skipped_items.append(
                    {
                        "source_path": str(input_path),
                        "cut": cut,
                        "reason": str(error),
                    }
                )

    if not cut_outputs and not shorts_outputs:
        raise RuntimeError("No clips were exported")

    return {
        "source_video": str(input_path),
        "source_filename": input_path.name,
        "cuts": cuts,
        "cut_outputs": cut_outputs,
        "shorts_outputs": shorts_outputs,
        "skipped_items": skipped_items,
    }


def save_upload_with_hash(file: UploadFile, output_path: Path) -> str:
    hasher = sha256()

    with output_path.open("wb") as buffer:
        while chunk := file.file.read(1024 * 1024):
            hasher.update(chunk)
            buffer.write(chunk)

    return hasher.hexdigest()


def register_uploaded_video(
    video_id: str,
    saved_path: Path,
    file_hash: str,
    original_width: int,
    original_height: int,
) -> None:
    index = read_upload_index()
    index[file_hash] = {
        "video_id": video_id,
        "filename": saved_path.name,
        "path": str(saved_path),
        "original_width": original_width,
        "original_height": original_height,
        "uploaded_at": utc_now(),
    }
    write_upload_index(index)


def find_duplicate_upload(file_hash: str, new_upload_path: Path) -> dict | None:
    index = read_upload_index()
    indexed_upload = index.get(file_hash)

    if indexed_upload:
        indexed_path = Path(indexed_upload.get("path", ""))

        if indexed_path.exists():
            return indexed_upload

    for upload_path in UPLOAD_DIR.iterdir():
        if (
            not upload_path.is_file()
            or upload_path == new_upload_path
            or upload_path.name == "upload_index.json"
            or ".uploading" in upload_path.name
        ):
            continue

        if hash_file(upload_path) != file_hash:
            continue

        video_id = upload_path.stem

        try:
            original_width, original_height = get_video_dimensions(upload_path)
        except Exception:
            original_width, original_height = 0, 0

        duplicate = {
            "video_id": video_id,
            "filename": upload_path.name,
            "path": str(upload_path),
            "original_width": original_width,
            "original_height": original_height,
            "uploaded_at": utc_now(),
        }
        index[file_hash] = duplicate
        write_upload_index(index)
        return duplicate

    return None


def hash_file(path: Path) -> str:
    hasher = sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            hasher.update(chunk)

    return hasher.hexdigest()


def read_upload_index() -> dict:
    return read_json_file(UPLOAD_DIR / "upload_index.json")


def write_upload_index(index: dict) -> None:
    write_json_file(UPLOAD_DIR / "upload_index.json", index)


def dump_schema(schema):
    if hasattr(schema, "model_dump"):
        return schema.model_dump()

    return schema.dict()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_job_progress(job_id: str, progress: int, current_step: str) -> None:
    job = JOBS.get(job_id)

    if not job:
        return

    job["progress"] = max(0, min(100, progress))
    job["current_step"] = current_step


def write_shorts_job_manifest(
    job_id: str,
    input_path: Path,
    job_output_dir: Path,
    shorts_output_dir: Path,
    cuts: list[dict],
    shorts_outputs: list[Path],
    shorts_mode: str,
    shorts_quality: str,
    cut_output_dir: Path | None = None,
    cut_outputs: list[Path] | None = None,
) -> None:
    clips = []

    for index, shorts_output in enumerate(shorts_outputs, start=1):
        clip = {
            "index": index,
            "filename": shorts_output.name,
            "path": str(shorts_output),
        }

        if index - 1 < len(cuts):
            clip["cut"] = cuts[index - 1]

        if cut_outputs and index - 1 < len(cut_outputs):
            clip["raw_cut_filename"] = cut_outputs[index - 1].name
            clip["raw_cut_path"] = str(cut_outputs[index - 1])

        clips.append(clip)

    manifest = {
        "job_id": job_id,
        "source_video": str(input_path),
        "created_at": utc_now(),
        "shorts_mode": shorts_mode,
        "shorts_quality": shorts_quality,
        "cut_output_dir": str(cut_output_dir) if cut_output_dir else None,
        "shorts_output_dir": str(shorts_output_dir),
        "cuts": cuts,
        "clips": clips,
    }
    manifest_path = job_output_dir / "source_info.json"
    write_json_file(manifest_path, manifest)

    if job_id in JOBS:
        JOBS[job_id]["manifest_path"] = str(manifest_path)


def list_shorts_jobs() -> list[dict]:
    jobs = []

    if not OUTPUT_DIR.exists():
        return jobs

    for job_dir in sorted(OUTPUT_DIR.iterdir(), key=lambda path: path.name):
        if not job_dir.is_dir() or job_dir.name == "compilations":
            continue

        shorts_output_dir = job_dir / "shorts_clips"

        if not shorts_output_dir.exists():
            continue

        clips = []
        manifest_path = job_dir / "source_info.json"
        manifest = read_json_file(manifest_path) if manifest_path.exists() else {}
        manifest_clips = {
            clip.get("filename"): clip
            for clip in manifest.get("clips", [])
            if isinstance(clip, dict)
        }

        for clip_path in sorted(shorts_output_dir.glob("*.mp4")):
            manifest_clip = manifest_clips.get(clip_path.name, {})
            clips.append(
                {
                    "job_id": job_dir.name,
                    "filename": clip_path.name,
                    "path": str(clip_path),
                    "cut": manifest_clip.get("cut"),
                }
            )

        jobs.append(
            {
                "job_id": job_dir.name,
                "shorts_output_dir": str(shorts_output_dir),
                "manifest_path": str(manifest_path) if manifest_path.exists() else None,
                "source_video": manifest.get("source_video"),
                "shorts_mode": manifest.get("shorts_mode"),
                "clip_count": len(clips),
                "clips": clips,
            }
        )

    return jobs


def list_shorts_clips(source_job_ids: list[str] | None = None) -> list[dict]:
    allowed_job_ids = set(source_job_ids or [])
    clips = []

    for job in list_shorts_jobs():
        if allowed_job_ids and job["job_id"] not in allowed_job_ids:
            continue

        clips.extend(job["clips"])

    return clips


def collect_eligible_shorts_clips(
    clips: list[dict],
    max_duration_seconds: int,
) -> tuple[list[dict], list[dict]]:
    eligible_clips = []
    skipped_clips = []

    for clip in clips:
        clip_path = Path(clip["path"])

        if not clip_path.exists():
            skipped_clips.append({**clip, "reason": "file_missing"})
            continue

        try:
            duration = get_video_duration(clip_path)
        except Exception:
            skipped_clips.append({**clip, "reason": "duration_unreadable"})
            continue

        clip_with_duration = {
            **clip,
            "duration_seconds": round(duration, 3),
        }

        if duration <= 0:
            skipped_clips.append({**clip_with_duration, "reason": "empty_clip"})
            continue

        if duration > max_duration_seconds:
            skipped_clips.append(
                {**clip_with_duration, "reason": "longer_than_max_duration"}
            )
            continue

        eligible_clips.append(clip_with_duration)

    random.shuffle(eligible_clips)
    return eligible_clips, skipped_clips


def build_random_shorts_groups(
    clips: list[dict],
    min_duration_seconds: int,
    max_duration_seconds: int,
    min_clips_per_short: int,
    max_shorts: int,
    divider_duration_seconds: float = 0.0,
) -> tuple[list[dict], list[dict]]:
    remaining_clips = clips[:]
    groups = []
    unused_clips = []

    while remaining_clips and len(groups) < max_shorts:
        group_clips = []
        group_duration = 0.0

        while remaining_clips and (
            len(group_clips) < min_clips_per_short
            or group_duration < min_duration_seconds
        ):
            fit_index = next(
                (
                    index
                    for index, clip in enumerate(remaining_clips)
                    if duration_with_added_clip(
                        group_duration,
                        len(group_clips),
                        clip["duration_seconds"],
                        divider_duration_seconds,
                    )
                    <= max_duration_seconds
                ),
                None,
            )

            if fit_index is None:
                break

            clip = remaining_clips.pop(fit_index)
            group_clips.append(clip)
            group_duration = duration_with_added_clip(
                group_duration,
                len(group_clips) - 1,
                clip["duration_seconds"],
                divider_duration_seconds,
            )

        if (
            len(group_clips) >= min_clips_per_short
            and group_duration >= min_duration_seconds
            and group_duration <= max_duration_seconds
        ):
            groups.append(
                {
                    "clips": group_clips,
                    "duration_seconds": round(group_duration, 3),
                }
            )
        else:
            unused_clips.extend(
                {**clip, "reason": "could_not_fit_rules"} for clip in group_clips
            )
            break

    unused_clips.extend(
        {**clip, "reason": "left_over_after_grouping"} for clip in remaining_clips
    )

    return groups, unused_clips


def duration_with_added_clip(
    current_duration: float,
    current_clip_count: int,
    clip_duration: float,
    divider_duration_seconds: float,
) -> float:
    divider_duration = max(0.0, divider_duration_seconds)
    added_divider_duration = divider_duration if current_clip_count > 0 else 0.0

    return current_duration + added_divider_duration + clip_duration


def concatenate_video_files(input_paths: list[Path], output_path: Path) -> None:
    if not input_paths:
        raise RuntimeError("No input videos were provided for concatenation")

    input_args = []
    for input_path in input_paths:
        input_args.extend(["-i", str(input_path)])

    video_audio_filters = []
    video_audio_inputs = []
    video_only_filters = []
    video_only_inputs = []

    for index in range(len(input_paths)):
        video_audio_filters.append(
            f"[{index}:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        video_audio_filters.append(
            f"[{index}:a]aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS[a{index}]"
        )
        video_audio_inputs.append(f"[v{index}][a{index}]")
        video_only_filters.append(
            f"[{index}:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        video_only_inputs.append(f"[v{index}]")

    command = [
        "ffmpeg",
        "-y",
        *input_args,
        "-filter_complex",
        (
            ";".join(video_audio_filters)
            + ";"
            + "".join(video_audio_inputs)
            + f"concat=n={len(input_paths)}:v=1:a=1[outv][outa]"
        ),
        "-map",
        "[outv]",
        "-map",
        "[outa]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        run_command(command)
    except RuntimeError:
        run_command(
            [
                "ffmpeg",
                "-y",
                *input_args,
                "-filter_complex",
                (
                    ";".join(video_only_filters)
                    + ";"
                    + "".join(video_only_inputs)
                    + f"concat=n={len(input_paths)}:v=1:a=0[outv]"
                ),
                "-map",
                "[outv]",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "veryfast",
                "-an",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )


def write_json_file(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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
