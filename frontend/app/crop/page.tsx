"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CropEditor from "@/components/CropEditor";
import JobStatusList from "@/components/JobStatusList";
import VideoUploadStep from "@/components/VideoUploadStep";
import {
  cropVideo,
  detectDynamicCrops,
  downloadYouTubeVideo,
  exportDynamicCrop,
  getApiErrorMessage,
  getVideoPreviewUrl,
  uploadVideo,
  type DynamicCropSegment,
  type JobStatus,
} from "@/lib/api";

type Crop = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export default function CropPage() {
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeQuality, setYoutubeQuality] = useState<"720p" | "1080p" | "best">(
    "1080p"
  );
  const [youtubeError, setYoutubeError] = useState<string | null>(null);
  const [isDownloadingYoutube, setIsDownloadingYoutube] = useState(false);
  const [crop, setCrop] = useState<Crop | null>(null);
  const [cropQuality, setCropQuality] = useState<
    "high" | "very_high" | "lossless"
  >("high");
  const [dynamicCropSegments, setDynamicCropSegments] = useState<
    DynamicCropSegment[]
  >([]);
  const [dynamicThreshold, setDynamicThreshold] = useState(0.35);
  const [dynamicMinSeconds, setDynamicMinSeconds] = useState(2);
  const [dynamicMaxSegments, setDynamicMaxSegments] = useState(80);
  const [isDetectingDynamicCrop, setIsDetectingDynamicCrop] = useState(false);
  const [dynamicCropError, setDynamicCropError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);

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

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];

    if (!selectedFile) return;

    setFile(selectedFile);
    setVideoId(null);
    setCrop(null);
    setDynamicCropSegments([]);
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

  async function handleYouTubeDownload() {
    if (!youtubeUrl.trim()) return;

    setIsDownloadingYoutube(true);
    setYoutubeError(null);
    setVideoId(null);
    setCrop(null);
    setDynamicCropSegments([]);

    try {
      const result = await downloadYouTubeVideo({
        url: youtubeUrl.trim(),
        quality: youtubeQuality,
      });

      setFile(null);
      setVideoId(result.video_id);
      setVideoUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return getVideoPreviewUrl(result.video_id);
      });
      setUploadMessage(
        result.title
          ? `Downloaded ${result.title}`
          : `Downloaded ${result.filename}`
      );
    } catch (error) {
      setYoutubeError(
        error instanceof Error
          ? error.message
          : "Could not download the YouTube video"
      );
    } finally {
      setIsDownloadingYoutube(false);
    }
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

  async function handleVerticalFromFullVideo() {
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
      label: "TikTok/Shorts export from full video",
    });
  }

  async function handleVerticalFromSelectedCrop() {
    if (!videoId || !crop) return;

    const result = await cropVideo({
      video_id: videoId,
      ...crop,
      quality: cropQuality,
      preset: "vertical_from_crop",
    });

    addJob({
      id: result.job_id,
      label: "TikTok/Shorts export from selected crop",
    });
  }

  async function handleDetectDynamicCrops() {
    if (!videoId) return;

    setIsDetectingDynamicCrop(true);
    setDynamicCropError(null);

    try {
      const result = await detectDynamicCrops({
        video_id: videoId,
        threshold: dynamicThreshold,
        min_segment_seconds: dynamicMinSeconds,
        max_segments: dynamicMaxSegments,
      });

      if (!Array.isArray(result.segments) || result.segments.length === 0) {
        setDynamicCropError("No dynamic crop segments were detected.");
        return;
      }

      setDynamicCropSegments(result.segments);
    } catch (error) {
      setDynamicCropError(
        getApiErrorMessage(error, "Could not detect dynamic crops")
      );
    } finally {
      setIsDetectingDynamicCrop(false);
    }
  }

  function updateDynamicSegment(
    index: number,
    field: keyof DynamicCropSegment,
    value: string
  ) {
    setDynamicCropSegments((prev) =>
      prev.map((segment, i) =>
        i === index
          ? {
              ...segment,
              [field]:
                field === "start" || field === "end" ? value : Number(value),
            }
          : segment
      )
    );
  }

  function removeDynamicSegment(index: number) {
    setDynamicCropSegments((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleDynamicCropExport() {
    if (!videoId || dynamicCropSegments.length === 0) return;

    const result = await exportDynamicCrop({
      video_id: videoId,
      segments: dynamicCropSegments,
      quality: cropQuality,
      output_width: 1920,
      output_height: 1080,
    });

    addJob({
      id: result.job_id,
      label: `Dynamic crop export (${dynamicCropSegments.length} segments)`,
    });
  }

  const customCropDisabledReason = !videoId
    ? "Upload the video to the backend before exporting."
    : !crop
      ? "Wait for the crop box to load or click Use this crop."
      : null;

  return (
    <main className="mx-auto max-w-6xl space-y-8 p-8">
      <div className="space-y-2">
        <Link href="/" className="text-sm text-blue-700">
          Back to tools
        </Link>
        <h1 className="text-3xl font-bold">Crop video</h1>
      </div>

      <VideoUploadStep
        file={file}
        uploadMessage={uploadMessage}
        onFileChange={handleFileChange}
        onUpload={handleUpload}
      />

      <section className="space-y-4 rounded border p-4">
        <h2 className="text-xl font-semibold">Or download from YouTube</h2>

        <label className="block space-y-1">
          <span className="text-sm font-medium">YouTube URL</span>
          <input
            value={youtubeUrl}
            onChange={(event) => setYoutubeUrl(event.target.value)}
            className="w-full rounded border p-2"
            placeholder="https://www.youtube.com/watch?v=..."
          />
        </label>

        <label className="block max-w-sm space-y-1">
          <span className="text-sm font-medium">Download quality</span>
          <select
            value={youtubeQuality}
            onChange={(event) =>
              setYoutubeQuality(event.target.value as "720p" | "1080p" | "best")
            }
            className="w-full rounded border p-2"
          >
            <option value="1080p">Good quality, up to 1080p</option>
            <option value="720p">Smaller file, up to 720p</option>
            <option value="best">Best available</option>
          </select>
        </label>

        <button
          onClick={handleYouTubeDownload}
          disabled={!youtubeUrl.trim() || isDownloadingYoutube}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {isDownloadingYoutube ? "Downloading..." : "Download from YouTube"}
        </button>

        {youtubeError && <p className="text-sm text-red-600">{youtubeError}</p>}

        <p className="text-sm text-gray-600">
          Use this only for videos you own or have permission to download.
        </p>
      </section>

      {videoUrl && (
        <section className="space-y-4 rounded border p-4">
          <h2 className="text-xl font-semibold">2. Choose crop</h2>

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

          <div className="flex flex-wrap gap-4">
            <button
              onClick={handleCropExport}
              disabled={!videoId || !crop}
              title={customCropDisabledReason || undefined}
              className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
            >
              Export custom crop
            </button>

            <button
              onClick={handleVerticalFromFullVideo}
              disabled={!videoId}
              className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
            >
              Make full video for TikTok/Shorts
            </button>

            <button
              onClick={handleVerticalFromSelectedCrop}
              disabled={!videoId || !crop}
              title={
                !videoId
                  ? "Upload the video to the backend before exporting."
                  : !crop
                    ? "Choose a crop area first."
                    : undefined
              }
              className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
            >
              Make selected crop for TikTok/Shorts
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
        <section className="space-y-4 rounded border p-4">
          <div>
            <h2 className="text-xl font-semibold">Auto dynamic crop</h2>
            <p className="text-sm text-gray-600">
              Detect scene changes, find likely black padding per segment, then export one joined video.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="space-y-1">
              <span className="text-sm font-medium">Scene sensitivity</span>
              <input
                type="number"
                min="0.05"
                max="1"
                step="0.05"
                value={dynamicThreshold}
                onChange={(event) =>
                  setDynamicThreshold(Number(event.target.value))
                }
                className="w-full rounded border p-2"
              />
            </label>

            <label className="space-y-1">
              <span className="text-sm font-medium">Minimum segment seconds</span>
              <input
                type="number"
                min="0.25"
                max="300"
                step="0.25"
                value={dynamicMinSeconds}
                onChange={(event) =>
                  setDynamicMinSeconds(Number(event.target.value))
                }
                className="w-full rounded border p-2"
              />
            </label>

            <label className="space-y-1">
              <span className="text-sm font-medium">Max segments</span>
              <input
                type="number"
                min="1"
                max="300"
                step="1"
                value={dynamicMaxSegments}
                onChange={(event) =>
                  setDynamicMaxSegments(Number(event.target.value))
                }
                className="w-full rounded border p-2"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-4">
            <button
              onClick={handleDetectDynamicCrops}
              disabled={isDetectingDynamicCrop}
              className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
            >
              {isDetectingDynamicCrop
                ? "Detecting..."
                : "Detect dynamic crops"}
            </button>

            <button
              onClick={handleDynamicCropExport}
              disabled={dynamicCropSegments.length === 0}
              className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
            >
              Export dynamic crop
            </button>
          </div>

          {dynamicCropError && (
            <p className="text-sm text-red-600">{dynamicCropError}</p>
          )}

          {dynamicCropSegments.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">
                Review these suggestions before exporting. Adjust crop values if a logo or border remains.
              </p>

              {dynamicCropSegments.map((segment, index) => (
                <div
                  key={`${segment.start}-${index}`}
                  className="grid gap-3 rounded border p-3 lg:grid-cols-8"
                >
                  {(["start", "end"] as const).map((field) => (
                    <label key={field} className="space-y-1">
                      <span className="text-sm font-medium">{field}</span>
                      <input
                        value={segment[field]}
                        onChange={(event) =>
                          updateDynamicSegment(index, field, event.target.value)
                        }
                        className="w-full rounded border p-2"
                      />
                    </label>
                  ))}

                  {(["x", "y", "width", "height"] as const).map((field) => (
                    <label key={field} className="space-y-1">
                      <span className="text-sm font-medium">{field}</span>
                      <input
                        type="number"
                        min="0"
                        value={segment[field]}
                        onChange={(event) =>
                          updateDynamicSegment(index, field, event.target.value)
                        }
                        className="w-full rounded border p-2"
                      />
                    </label>
                  ))}

                  <div className="flex items-end lg:col-span-2">
                    <button
                      onClick={() => removeDynamicSegment(index)}
                      className="rounded border px-4 py-2"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <JobStatusList jobs={jobs} onJobUpdate={updateJob} />
    </main>
  );
}
