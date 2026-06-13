# Video Cropper & Cutter

A full-stack video editing MVP built with Next.js, FastAPI, and FFmpeg.

## Features

- Upload videos to the backend
- Download a YouTube video into the crop workflow
- Preview videos in the browser
- Draw and export a custom crop
- Export a centered 9:16 crop for Reels, Shorts, and TikTok
- Cut one long video into multiple clips from timestamps
- Fast cut mode with FFmpeg stream copy
- Accurate cut mode with H.264 re-encoding
- Background job status polling
- Download crop output directly
- Download multi-cut output as a ZIP archive

## Requirements

- Node.js 20+
- Python 3.11+
- FFmpeg available on `PATH`

## Run Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`.

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

## Optional Docker Compose

The Compose setup uses stock Node and Python images. FFmpeg is installed into the backend container on startup.

```powershell
docker compose up
```

## Notes

Cutting with mode `copy` preserves quality because it uses `-c copy`, but cuts may align to keyframes instead of exact frames.

Cropping changes the frame, so it must re-encode. The default crop quality is H.264 CRF 18.

Uploaded and exported videos are stored under `backend/app/storage/` and ignored by git.

Only download videos you own or have permission to download.
