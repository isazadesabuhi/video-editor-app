"use client";

import { useCallback, useEffect, useState } from "react";
import CutListEditor from "@/components/CutListEditor";
import CropEditor from "@/components/CropEditor";
import JobStatusList from "@/components/JobStatusList";
import { cropVideo, uploadVideo, type JobStatus } from "@/lib/api";

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [cropQuality, setCropQuality] = useState<
    "high" | "very_high" | "lossless"
  >("high");
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [crop, setCrop] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);

  useEffect(() => {
    return () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  const addJob = useCallback((job: { id: string; label: string }) => {
    setJobs((prev) => [
      {
        id: job.id,
        label: job.label,
        status: "processing",
      },
      ...prev,
    ]);
  }, []);

  const updateJob = useCallback((updatedJob: JobStatus) => {
    setJobs((prev) =>
      prev.map((job) => (job.id === updatedJob.id ? updatedJob : job))
    );
  }, []);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];

    if (!selectedFile) return;

    setFile(selectedFile);
    setVideoId(null);
    setCrop(null);
    setUploadMessage(null);
    setVideoUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(selectedFile);
    });
  }

  async function handleUpload() {
    if (!file) return;

    const result = await uploadVideo(file);
    setVideoId(result.video_id);
    setUploadMessage(`Uploaded ${result.filename}`);
  }

  async function handleCropExport() {
    if (!videoId || !crop) return;

    const result = await cropVideo({
      video_id: videoId,
      ...crop,
      quality: cropQuality,
    });

    addJob({
      id: result.job_id,
      label: "Custom crop export",
    });
  }

  async function handleVerticalPreset() {
    if (!videoId) return;

    const result = await cropVideo({
      video_id: videoId,
      x: 0,
      y: 0,
      width: 1,
      height: 1,
      quality: cropQuality,
      preset: "reels",
    });

    addJob({
      id: result.job_id,
      label: "9:16 vertical export",
    });
  }

  const customCropDisabledReason = !videoId
    ? "Upload the video to the backend before exporting."
    : !crop
      ? "Wait for the crop box to load or click Use this crop."
      : null;

  return (
    <main className="mx-auto max-w-6xl space-y-8 p-8">
      <h1 className="text-3xl font-bold">Video Cropper & Cutter</h1>

      <section className="space-y-4 rounded border p-4">
        <h2 className="text-xl font-semibold">1. Upload video</h2>

        <input type="file" accept="video/*" onChange={handleFileChange} />

        <button
          onClick={handleUpload}
          disabled={!file}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Upload to backend
        </button>

        {uploadMessage && (
          <p className="text-sm text-gray-600">{uploadMessage}</p>
        )}
      </section>

      {videoUrl && (
        <section className="space-y-4 rounded border p-4">
          <h2 className="text-xl font-semibold">2. Crop visually</h2>

          <CropEditor videoUrl={videoUrl} onCropReady={setCrop} />

          {crop && (
            <pre className="rounded bg-gray-100 p-4 text-sm">
              {JSON.stringify(crop, null, 2)}
            </pre>
          )}

          <label className="block max-w-sm space-y-1">
            <span className="text-sm font-medium">Crop export quality</span>
            <select
              value={cropQuality}
              onChange={(event) =>
                setCropQuality(
                  event.target.value as "high" | "very_high" | "lossless"
                )
              }
              className="w-full rounded border p-2"
            >
              <option value="high">High, CRF 18</option>
              <option value="very_high">Very high, CRF 16</option>
              <option value="lossless">Lossless</option>
            </select>
          </label>

          <div className="flex gap-4">
            <button
              onClick={handleCropExport}
              disabled={!videoId || !crop}
              title={customCropDisabledReason || undefined}
              className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
            >
              Export custom crop
            </button>

            <button
              onClick={handleVerticalPreset}
              disabled={!videoId}
              className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
            >
              Export 9:16 for Reels/Shorts
            </button>
          </div>

          {customCropDisabledReason && (
            <p className="text-sm text-gray-600">
              {customCropDisabledReason}
            </p>
          )}
        </section>
      )}

      {videoId && (
        <CutListEditor videoId={videoId} onJobStarted={addJob} />
      )}

      <JobStatusList jobs={jobs} onJobUpdate={updateJob} />
    </main>
  );
}
