import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
OUTPUT_DIR = BASE_DIR / "storage" / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def time_to_seconds(time_str: str) -> int:
    """
    Converts HH:MM:SS to seconds.
    Example: 02:23:44 -> 8624
    """
    parts = time_str.split(":")

    if len(parts) != 3:
        raise ValueError("Time must be in HH:MM:SS format")

    h, m, s = map(int, parts)

    if h < 0 or m < 0 or s < 0 or m >= 60 or s >= 60:
        raise ValueError("Invalid time value")

    return h * 3600 + m * 60 + s


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
    Crop to the selected region, then fit it into a 1080x1920 vertical canvas.
    This keeps the chosen crop visible without stretching it.
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
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1"
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

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        start,
        "-to",
        end,
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

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        start,
        "-to",
        end,
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        "slow",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]

    run_command(command)
