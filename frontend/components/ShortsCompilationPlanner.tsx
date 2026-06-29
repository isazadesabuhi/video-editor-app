"use client";

import { useState } from "react";
import {
  createShortsCompilationDraft,
  generateShortsCompilation,
  getApiErrorMessage,
  getShortsLibrary,
  uploadVideo,
  type ShortsLibraryJob,
} from "@/lib/api";

type DraftResult = {
  compilation_id: string;
  selected_count: number;
  selected_dir: string;
  manifest_path: string;
  final_output: string;
};

type Props = {
  onJobStarted: (job: { id: string; label: string }) => void;
};

export default function ShortsCompilationPlanner({ onJobStarted }: Props) {
  const [jobs, setJobs] = useState<ShortsLibraryJob[]>([]);
  const [totalClips, setTotalClips] = useState(0);
  const [clipCount, setClipCount] = useState(5);
  const [minDurationSeconds, setMinDurationSeconds] = useState(45);
  const [maxDurationSeconds, setMaxDurationSeconds] = useState(60);
  const [minClipsPerShort, setMinClipsPerShort] = useState(2);
  const [maxShorts, setMaxShorts] = useState(10);
  const [title, setTitle] = useState("");
  const [dividerFile, setDividerFile] = useState<File | null>(null);
  const [dividerVideoId, setDividerVideoId] = useState<string | null>(null);
  const [dividerUploadMessage, setDividerUploadMessage] = useState<string | null>(null);
  const [isUploadingDivider, setIsUploadingDivider] = useState(false);
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(false);
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [isGeneratingFinals, setIsGeneratingFinals] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftResult | null>(null);

  async function refreshLibrary() {
    setIsLoadingLibrary(true);
    setError(null);

    try {
      const result = await getShortsLibrary();
      setJobs(result.jobs);
      setTotalClips(result.total_clips);
    } catch (requestError) {
      setError(
        getApiErrorMessage(requestError, "Could not load Shorts library")
      );
    } finally {
      setIsLoadingLibrary(false);
    }
  }

  async function createDraft() {
    setIsCreatingDraft(true);
    setError(null);
    setDraft(null);

    try {
      const result = await createShortsCompilationDraft({
        clip_count: clipCount,
        title: title.trim() || undefined,
      });

      setDraft(result);
    } catch (requestError) {
      setError(
        getApiErrorMessage(requestError, "Could not create compilation draft")
      );
    } finally {
      setIsCreatingDraft(false);
    }
  }

  async function generateFinalShorts() {
    setIsGeneratingFinals(true);
    setError(null);

    try {
      const result = await generateShortsCompilation({
        min_duration_seconds: minDurationSeconds,
        max_duration_seconds: maxDurationSeconds,
        min_clips_per_short: minClipsPerShort,
        max_shorts: maxShorts,
        title: title.trim() || undefined,
        divider_video_id: dividerVideoId || undefined,
      });

      onJobStarted({
        id: result.job_id,
        label: "Final Shorts generation",
      });
    } catch (requestError) {
      setError(
        getApiErrorMessage(requestError, "Could not generate final Shorts")
      );
    } finally {
      setIsGeneratingFinals(false);
    }
  }

  function handleDividerFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];

    setDividerFile(selectedFile || null);
    setDividerVideoId(null);
    setDividerUploadMessage(null);
  }

  async function uploadDivider() {
    if (!dividerFile) return;

    setIsUploadingDivider(true);
    setError(null);
    setDividerUploadMessage(null);

    try {
      const result = await uploadVideo(dividerFile);
      setDividerVideoId(result.video_id);
      setDividerUploadMessage(
        result.duplicate
          ? `Already uploaded. Using ${result.filename}`
          : `Uploaded ${result.filename}`
      );
    } catch (requestError) {
      setDividerUploadMessage(
        getApiErrorMessage(requestError, "Could not upload divider video")
      );
    } finally {
      setIsUploadingDivider(false);
    }
  }

  return (
    <section className="space-y-4 rounded border p-4">
      <div>
        <h2 className="text-xl font-semibold">4. Shorts compilation draft</h2>
        <p className="text-sm text-gray-600">
          Randomly combine clips from existing shorts_clips folders into final TikTok/YouTube Shorts.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={refreshLibrary}
          disabled={isLoadingLibrary}
          className="rounded border px-4 py-2 disabled:opacity-50"
        >
          {isLoadingLibrary ? "Refreshing..." : "Refresh Shorts library"}
        </button>

        <button
          onClick={generateFinalShorts}
          disabled={isGeneratingFinals || totalClips === 0}
          className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
        >
          {isGeneratingFinals ? "Generating..." : "Generate final Shorts"}
        </button>

        <button
          onClick={createDraft}
          disabled={isCreatingDraft || totalClips === 0}
          className="rounded border px-4 py-2 disabled:opacity-50"
        >
          {isCreatingDraft ? "Creating..." : "Create random draft"}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <label className="space-y-1">
          <span className="text-sm font-medium">Min seconds</span>
          <input
            type="number"
            min="1"
            max="3600"
            value={minDurationSeconds}
            onChange={(event) =>
              setMinDurationSeconds(Number(event.target.value))
            }
            className="w-full rounded border p-2"
          />
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Max seconds</span>
          <input
            type="number"
            min="1"
            max="3600"
            value={maxDurationSeconds}
            onChange={(event) =>
              setMaxDurationSeconds(Number(event.target.value))
            }
            className="w-full rounded border p-2"
          />
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Min videos per Short</span>
          <input
            type="number"
            min="1"
            max="100"
            value={minClipsPerShort}
            onChange={(event) =>
              setMinClipsPerShort(Number(event.target.value))
            }
            className="w-full rounded border p-2"
          />
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Max Shorts</span>
          <input
            type="number"
            min="1"
            max="100"
            value={maxShorts}
            onChange={(event) => setMaxShorts(Number(event.target.value))}
            className="w-full rounded border p-2"
          />
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Draft clips count</span>
          <input
            type="number"
            min="1"
            max="100"
            value={clipCount}
            onChange={(event) => setClipCount(Number(event.target.value))}
            className="w-full rounded border p-2"
          />
        </label>

        <label className="space-y-1 sm:col-span-2 lg:col-span-5">
          <span className="text-sm font-medium">Draft title</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="w-full rounded border p-2"
            placeholder="Optional"
          />
        </label>
      </div>

      <div className="space-y-3 rounded border border-gray-200 p-3">
        <div>
          <h3 className="font-semibold">Divider between videos</h3>
          <p className="text-sm text-gray-600">
            Upload a very short black video with sound. It will be inserted between every selected clip in generated final Shorts.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept="video/*"
            onChange={handleDividerFileChange}
            className="max-w-full"
          />

          <button
            onClick={uploadDivider}
            disabled={!dividerFile || isUploadingDivider}
            className="rounded border px-4 py-2 disabled:opacity-50"
          >
            {isUploadingDivider ? "Uploading..." : "Upload divider"}
          </button>
        </div>

        {dividerUploadMessage && (
          <p className="text-sm text-gray-600">{dividerUploadMessage}</p>
        )}

        {dividerVideoId && (
          <p className="text-sm text-gray-600">
            Divider ready. It will be used by Generate final Shorts.
          </p>
        )}
      </div>

      <p className="text-sm text-gray-600">
        Library: {jobs.length} job{jobs.length === 1 ? "" : "s"},{" "}
        {totalClips} clip{totalClips === 1 ? "" : "s"}
      </p>

      {jobs.length > 0 && (
        <div className="space-y-2">
          {jobs.map((job) => (
            <div key={job.job_id} className="rounded border p-3 text-sm">
              <p className="font-medium">{job.job_id}</p>
              <p className="text-gray-600">
                {job.clip_count} clip{job.clip_count === 1 ? "" : "s"} in{" "}
                <code className="rounded bg-gray-100 px-1">
                  {job.shorts_output_dir}
                </code>
              </p>
            </div>
          ))}
        </div>
      )}

      {draft && (
        <div className="space-y-1 rounded border border-blue-200 bg-blue-50 p-3 text-sm">
          <p className="font-medium">
            Draft created with {draft.selected_count} clip
            {draft.selected_count === 1 ? "" : "s"}
          </p>
          <p>
            Selected clips:{" "}
            <code className="rounded bg-white px-1">{draft.selected_dir}</code>
          </p>
          <p>
            Manifest:{" "}
            <code className="rounded bg-white px-1">{draft.manifest_path}</code>
          </p>
          <p>
            Future final video:{" "}
            <code className="rounded bg-white px-1">{draft.final_output}</code>
          </p>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
