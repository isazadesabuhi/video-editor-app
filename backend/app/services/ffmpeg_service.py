import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
OUTPUT_DIR = BASE_DIR / "storage" / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def time_to_seconds(time_str: str) -> float:
    """
    Converts HH:MM:SS or HH:MM:SS:MS to seconds.
    Example: 02:23:44 -> 8624
    Example: 00:00:01:250 -> 1.25
    """
    parts = time_str.split(":")

    if len(parts) not in (3, 4):
        raise ValueError("Time must be in HH:MM:SS or HH:MM:SS:MS format")

    h, m, s = map(int, parts[:3])
    milliseconds = parse_milliseconds(parts[3]) if len(parts) == 4 else 0

    if h < 0 or m < 0 or s < 0 or m >= 60 or s >= 60:
        raise ValueError("Invalid time value")

    return h * 3600 + m * 60 + s + milliseconds / 1000


def parse_milliseconds(value: str) -> int:
    if not value.isdigit() or len(value) > 3:
        raise ValueError("Milliseconds must be 1 to 3 digits")

    return int(value.ljust(3, "0"))


def normalize_time_for_ffmpeg(time_str: str) -> str:
    """
    FFmpeg expects fractional seconds as HH:MM:SS.mmm, not HH:MM:SS:MS.
    """
    parts = time_str.split(":")

    if len(parts) == 3:
        time_to_seconds(time_str)
        return time_str

    if len(parts) != 4:
        raise ValueError("Time must be in HH:MM:SS or HH:MM:SS:MS format")

    h, m, s = map(int, parts[:3])
    milliseconds = parse_milliseconds(parts[3])

    if h < 0 or m < 0 or s < 0 or m >= 60 or s >= 60:
        raise ValueError("Invalid time value")

    return f"{h:02d}:{m:02d}:{s:02d}.{milliseconds:03d}"


def get_crf(quality: str) -> str:
    if quality == "lossless":
        return "0"

    if quality == "very_high":
        return "16"

    return "18"


def run_command(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60 * 60,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("FFmpeg timed out before the export finished") from error
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg is not installed or is not on PATH") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(message) from error


def run_capture_command(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60 * 60,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("FFmpeg timed out before analysis finished") from error
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg/FFprobe is not installed or is not on PATH") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(message) from error

    return f"{result.stdout}\n{result.stderr}"


def seconds_to_time(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours = total_milliseconds // 3_600_000
    minutes = (total_milliseconds % 3_600_000) // 60_000
    whole_seconds = (total_milliseconds % 60_000) // 1000
    milliseconds = total_milliseconds % 1000

    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}:{milliseconds:03d}"


def get_video_duration(input_path: Path) -> float:
    output = run_capture_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
    )

    try:
        return float(output.strip())
    except ValueError as error:
        raise RuntimeError("Could not read video duration") from error


def detect_scene_clips(
    input_path: Path,
    threshold: float = 0.35,
    min_clip_seconds: float = 2,
    end_trim_ms: int = 120,
) -> list[dict[str, str]]:
    duration = get_video_duration(input_path)
    end_trim_seconds = end_trim_ms / 1000

    output = run_capture_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(input_path),
            "-vf",
            f"scale=320:-2,select=gt(scene\\,{threshold}),showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )

    scene_times = sorted(
        {
            float(match)
            for match in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", output)
        }
    )
    boundaries = [0.0]

    for scene_time in scene_times:
        if scene_time - boundaries[-1] >= min_clip_seconds:
            boundaries.append(scene_time)

    if duration - boundaries[-1] >= min_clip_seconds:
        boundaries.append(duration)
    elif len(boundaries) > 1:
        boundaries[-1] = duration

    clips = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        trimmed_end = end

        if end < duration:
            trimmed_end = max(start, end - end_trim_seconds)

        if trimmed_end - start >= min_clip_seconds:
            clips.append(
                {
                    "start": seconds_to_time(start),
                    "end": seconds_to_time(trimmed_end),
                    "name": f"clip_{index}",
                }
            )

    if not clips and duration > 0:
        clips.append(
            {
                "start": seconds_to_time(0),
                "end": seconds_to_time(duration),
                "name": "clip_1",
            }
        )

    return clips


def crop_video(
    input_path: Path,
    output_path: Path,
    x: int,
    y: int,
    width: int,
    height: int,
    quality: str = "high",
) -> None:
    """
    Crop needs re-encoding.
    Width and height should be even numbers for better codec compatibility.
    """
    width = width if width % 2 == 0 else width - 1
    height = height if height % 2 == 0 else height - 1

    if width <= 0 or height <= 0:
        raise ValueError("Crop width and height must be at least 2 pixels")

    crf = get_crf(quality)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"crop={width}:{height}:{x}:{y},setsar=1",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)


def crop_for_vertical_social(
    input_path: Path,
    output_path: Path,
    quality: str = "high",
) -> None:
    """
    Center-crop to 9:16 and scale to 1080x1920.
    Useful for TikTok/Reels/Shorts-style vertical videos.

    Warning:
    If source video is too small, scaling up will not create real extra detail.
    """
    crf = get_crf(quality)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        (
            "crop="
            "'floor(if(gt(iw/ih,9/16),ih*9/16,iw)/2)*2':"
            "'floor(if(gt(iw/ih,9/16),ih,iw*16/9)/2)*2':"
            "(iw-ow)/2:(ih-oh)/2,"
            "scale=1080:1920,setsar=1"
        ),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)


def crop_selection_for_vertical_social(
    input_path: Path,
    output_path: Path,
    x: int,
    y: int,
    width: int,
    height: int,
    quality: str = "high",
) -> None:
    """
    Crop to the selected region, then fill a 1080x1920 vertical canvas.
    This avoids letterboxing for TikTok/Reels/Shorts.
    """
    width = width if width % 2 == 0 else width - 1
    height = height if height % 2 == 0 else height - 1

    if width <= 0 or height <= 0:
        raise ValueError("Crop width and height must be at least 2 pixels")

    crf = get_crf(quality)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        (
            f"crop={width}:{height}:{x}:{y},"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1"
        ),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)


def cut_video_copy(
    input_path: Path,
    output_path: Path,
    start: str,
    end: str,
) -> None:
    """
    Fast cut without re-encoding.
    Best for preserving original quality.
    May not be frame-perfect.
    """
    start_seconds = time_to_seconds(start)
    end_seconds = time_to_seconds(end)

    if end_seconds <= start_seconds:
        raise ValueError(f"Invalid cut range: {start} to {end}")

    ffmpeg_start = normalize_time_for_ffmpeg(start)
    ffmpeg_end = normalize_time_for_ffmpeg(end)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        ffmpeg_start,
        "-to",
        ffmpeg_end,
        "-i",
        str(input_path),
        "-map",
        "0",
        "-c",
        "copy",
        str(output_path),
    ]

    run_command(command)


def cut_video_accurate(
    input_path: Path,
    output_path: Path,
    start: str,
    end: str,
    quality: str = "high",
) -> None:
    """
    More accurate cut, but re-encodes video.
    """
    start_seconds = time_to_seconds(start)
    end_seconds = time_to_seconds(end)

    if end_seconds <= start_seconds:
        raise ValueError(f"Invalid cut range: {start} to {end}")

    crf = get_crf(quality)
    ffmpeg_start = normalize_time_for_ffmpeg(start)
    ffmpeg_end = normalize_time_for_ffmpeg(end)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        ffmpeg_start,
        "-to",
        ffmpeg_end,
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)
