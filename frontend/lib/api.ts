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

export async function getJob(jobId: string) {
  const response = await axios.get(`${API_URL}/jobs/${jobId}`);
  return response.data;
}

export function getDownloadUrl(jobId: string) {
  return `${DOWNLOAD_URL}/${jobId}`;
}
