import axios from "axios";

export const API_URL = "http://localhost:8000";
export const DOWNLOAD_URL = `${API_URL}/download`;

export type JobStatus = {
  id: string;
  label: string;
  status: "processing" | "done" | "failed";
  error?: string;
  output?: string;
  outputs?: string[];
  archive?: string;
  started_at?: string;
  finished_at?: string;
};

export async function uploadVideo(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await axios.post(`${API_URL}/videos/upload`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
}

export async function downloadYouTubeVideo(payload: {
  url: string;
  quality: "720p" | "1080p" | "best";
}) {
  const response = await axios.post(`${API_URL}/videos/youtube`, payload);
  return response.data;
}

export function getVideoPreviewUrl(videoId: string) {
  return `${API_URL}/videos/${videoId}/preview`;
}

export async function cropVideo(payload: {
  video_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  quality: string;
  preset?: string;
}) {
  const response = await axios.post(`${API_URL}/videos/crop`, payload);
  return response.data;
}

export async function cutVideo(payload: {
  video_id: string;
  mode: "copy" | "accurate";
  quality: "high" | "very_high" | "lossless";
  cuts: {
    start: string;
    end: string;
    name?: string;
  }[];
}) {
  const response = await axios.post(`${API_URL}/videos/cut`, payload);
  return response.data;
}

export async function detectClips(payload: {
  video_id: string;
  threshold: number;
  min_clip_seconds: number;
  end_trim_ms: number;
}) {
  const response = await axios.post(`${API_URL}/videos/detect-clips`, payload);
  return response.data;
}

export async function getJob(jobId: string) {
  const response = await axios.get(`${API_URL}/jobs/${jobId}`, {
    params: {
      t: Date.now(),
    },
    headers: {
      "Cache-Control": "no-cache",
    },
  });
  return response.data;
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(String).join(", ");

    return error.message;
  }

  return error instanceof Error ? error.message : fallback;
}

export function getDownloadUrl(jobId: string) {
  return `${DOWNLOAD_URL}/${jobId}`;
}
