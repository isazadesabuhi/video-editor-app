"use client";

import { useRef, useState } from "react";
import {
  cutAndPrepareShorts,
  cutToShorts,
  cutVideo,
  detectClips,
  getApiErrorMessage,
} from "@/lib/api";

type Cut = {
  start: string;
  end: string;
  name: string;
};

type ShortsMode = "fit_padding" | "blur_background" | "crop_fill";

type Props = {
  videoId: string;
  videoUrl: string;
  onJobStarted: (job: { id: string; label: string }) => void;
};

export default function CutListEditor({
  videoId,
  videoUrl,
  onJobStarted,
}: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [cuts, setCuts] = useState<Cut[]>([
    {
      start: "00:00:00:000",
      end: "00:00:10:000",
      name: "clip_1",
    },
  ]);
  const [mode, setMode] = useState<"copy" | "accurate">("accurate");
  const [quality, setQuality] = useState<"high" | "very_high" | "lossless">(
    "very_high"
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPreparingShorts, setIsPreparingShorts] = useState(false);
  const [isCreatingShortsOnly, setIsCreatingShortsOnly] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isCutListOpen, setIsCutListOpen] = useState(true);
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);
  const [sceneThreshold, setSceneThreshold] = useState(0.35);
  const [minClipSeconds, setMinClipSeconds] = useState(2);
  const [endTrimMs, setEndTrimMs] = useState(120);
  const [selectedCutIndex, setSelectedCutIndex] = useState(0);
  const [selectionStart, setSelectionStart] = useState("00:00:00:000");
  const [selectionEnd, setSelectionEnd] = useState("00:00:10:000");
  const [shortsMode, setShortsMode] =
    useState<ShortsMode>("blur_background");
  const [shortsQuality, setShortsQuality] = useState<
    "high" | "very_high" | "lossless"
  >("high");

  function formatTime(totalSeconds: number) {
    const totalMilliseconds = Math.max(0, Math.round(totalSeconds * 1000));
    const hours = Math.floor(totalMilliseconds / 3_600_000);
    const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000);
    const seconds = Math.floor((totalMilliseconds % 60_000) / 1000);
    const milliseconds = totalMilliseconds % 1000;

    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
      String(milliseconds).padStart(3, "0"),
    ].join(":");
  }

  function currentVideoTime() {
    return formatTime(videoRef.current?.currentTime ?? 0);
  }

  function updateCut(index: number, field: keyof Cut, value: string) {
    setCuts((prev) =>
      prev.map((cut, i) => (i === index ? { ...cut, [field]: value } : cut))
    );
  }

  function addCut() {
    setCuts((prev) => [
      ...prev,
      {
        start: "00:00:00:000",
        end: "00:00:10:000",
        name: `clip_${prev.length + 1}`,
      },
    ]);
  }

  function addCutFromSelection() {
    const nextIndex = cuts.length;

    setCuts((prev) => [
      ...prev,
      {
        start: selectionStart,
        end: selectionEnd,
        name: `clip_${prev.length + 1}`,
      },
    ]);
    setSelectedCutIndex(nextIndex);
  }

  function removeCut(index: number) {
    setCuts((prev) => prev.filter((_, i) => i !== index));
    setSelectedCutIndex((prev) => Math.max(0, Math.min(prev, cuts.length - 2)));
  }

  function setSelectedCutTime(field: "start" | "end") {
    const time = currentVideoTime();

    updateCut(selectedCutIndex, field, time);

    if (field === "start") {
      setSelectionStart(time);
    } else {
      setSelectionEnd(time);
    }
  }

  function setSelectionTime(field: "start" | "end") {
    const time = currentVideoTime();

    if (field === "start") {
      setSelectionStart(time);
    } else {
      setSelectionEnd(time);
    }
  }

  async function autoDetectClips() {
    setIsDetecting(true);
    setDetectError(null);

    try {
      const result = await detectClips({
        video_id: videoId,
        threshold: sceneThreshold,
        min_clip_seconds: minClipSeconds,
        end_trim_ms: endTrimMs,
      });

      if (!Array.isArray(result.clips) || result.clips.length === 0) {
        setDetectError("No clips were detected. Try a lower threshold.");
        return;
      }

      setCuts(result.clips);
      setSelectedCutIndex(0);
    } catch (error) {
      setDetectError(getApiErrorMessage(error, "Could not detect clips"));
    } finally {
      setIsDetecting(false);
    }
  }

  async function submitCuts() {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const result = await cutVideo({
        video_id: videoId,
        mode,
        quality,
        cuts,
      });

      onJobStarted({
        id: result.job_id,
        label: `Cut export (${cuts.length} clip${cuts.length === 1 ? "" : "s"})`,
      });
    } catch (error) {
      setSubmitError(getApiErrorMessage(error, "Could not start cut job"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitCutAndPrepareShorts() {
    setIsPreparingShorts(true);
    setSubmitError(null);

    try {
      const result = await cutAndPrepareShorts({
        video_id: videoId,
        mode,
        quality,
        shorts_mode: shortsMode,
        shorts_quality: shortsQuality,
        cuts,
      });

      onJobStarted({
        id: result.job_id,
        label: `Cut + Shorts preparation (${cuts.length} clip${
          cuts.length === 1 ? "" : "s"
        })`,
      });
    } catch (error) {
      setSubmitError(
        getApiErrorMessage(error, "Could not start Shorts preparation job")
      );
    } finally {
      setIsPreparingShorts(false);
    }
  }

  async function submitShortsOnly() {
    setIsCreatingShortsOnly(true);
    setSubmitError(null);

    try {
      const result = await cutToShorts({
        video_id: videoId,
        mode,
        quality,
        shorts_mode: shortsMode,
        shorts_quality: shortsQuality,
        cuts,
      });

      onJobStarted({
        id: result.job_id,
        label: `Shorts only (${cuts.length} clip${
          cuts.length === 1 ? "" : "s"
        })`,
      });
    } catch (error) {
      setSubmitError(
        getApiErrorMessage(error, "Could not start Shorts-only job")
      );
    } finally {
      setIsCreatingShortsOnly(false);
    }
  }

  return (
    <div className="space-y-4 rounded border p-4">
      <h2 className="text-xl font-semibold">Cut into multiple clips</h2>
      <p className="text-sm text-gray-600">
        Times support HH:MM:SS or HH:MM:SS:MS. Example: 00:00:01:250 means 1.25 seconds.
      </p>
      <p className="text-sm text-gray-600">
        Best quality mode re-encodes clips for cleaner starts, fewer freezes, and better compatibility.
      </p>

      <div className="space-y-4 rounded border p-3">
        <video ref={videoRef} src={videoUrl} controls className="w-full bg-black" />

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <p className="text-sm font-medium">Set selected clip from player</p>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => setSelectedCutTime("start")}
                className="rounded border px-4 py-2"
              >
                Set start
              </button>
              <button
                onClick={() => setSelectedCutTime("end")}
                className="rounded border px-4 py-2"
              >
                Set end
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Create new clip from player</p>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => setSelectionTime("start")}
                className="rounded border px-4 py-2"
              >
                Mark start
              </button>
              <button
                onClick={() => setSelectionTime("end")}
                className="rounded border px-4 py-2"
              >
                Mark end
              </button>
              <button
                onClick={addCutFromSelection}
                className="rounded bg-black px-4 py-2 text-white"
              >
                Add clip from selection
              </button>
            </div>
            <p className="text-sm text-gray-600">
              Selection: {selectionStart} to {selectionEnd}
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-4 rounded border p-3">
        <div>
          <h3 className="font-semibold">Auto detect clips</h3>
          <p className="text-sm text-gray-600">
            Detect likely clip boundaries from scene changes, then review the generated list before cutting.
          </p>
          <p className="text-sm text-gray-600">
            If exported clips still include frames from the next clip, increase end trim or use accurate cut mode.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <label className="space-y-1">
            <span className="text-sm font-medium">Scene sensitivity</span>
            <input
              type="number"
              min="0.05"
              max="1"
              step="0.05"
              value={sceneThreshold}
              onChange={(event) => setSceneThreshold(Number(event.target.value))}
              className="w-full rounded border p-2"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">Minimum clip seconds</span>
            <input
              type="number"
              min="0.25"
              max="300"
              step="0.25"
              value={minClipSeconds}
              onChange={(event) => setMinClipSeconds(Number(event.target.value))}
              className="w-full rounded border p-2"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">End trim milliseconds</span>
            <input
              type="number"
              min="0"
              max="2000"
              step="20"
              value={endTrimMs}
              onChange={(event) => setEndTrimMs(Number(event.target.value))}
              className="w-full rounded border p-2"
            />
          </label>
        </div>

        <button
          onClick={autoDetectClips}
          disabled={isDetecting}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {isDetecting ? "Detecting..." : "Auto detect clips"}
        </button>

        {detectError && <p className="text-sm text-red-600">{detectError}</p>}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-sm font-medium">Cut mode</span>
          <select
            value={mode}
            onChange={(event) =>
              setMode(event.target.value as "copy" | "accurate")
            }
            className="w-full rounded border p-2"
          >
            <option value="accurate">Best quality, accurate cut</option>
            <option value="copy">Fast copy, original quality</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Encode quality</span>
          <select
            value={quality}
            onChange={(event) =>
              setQuality(
                event.target.value as "high" | "very_high" | "lossless"
              )
            }
            disabled={mode === "copy"}
            className="w-full rounded border p-2 disabled:opacity-50"
          >
            <option value="very_high">Very high, CRF 16</option>
            <option value="high">High, CRF 18</option>
            <option value="lossless">Lossless</option>
          </select>
        </label>
      </div>

      <div className="space-y-4 rounded border border-blue-200 bg-blue-50 p-3">
        <div>
          <h3 className="font-semibold">Prepare cut clips for Shorts</h3>
          <p className="text-sm text-gray-600">
            Create both cut_clips and shorts_clips, or create only the vertical 1080x1920 shorts_clips folder.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1">
            <span className="text-sm font-medium">Shorts layout</span>
            <select
              value={shortsMode}
              onChange={(event) =>
                setShortsMode(event.target.value as ShortsMode)
              }
              className="w-full rounded border p-2"
            >
              <option value="blur_background">Blurred background</option>
              <option value="crop_fill">Full-screen crop</option>
              <option value="fit_padding">Black padding</option>
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">Shorts encode quality</span>
            <select
              value={shortsQuality}
              onChange={(event) =>
                setShortsQuality(
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
        </div>
      </div>

      <div className="space-y-3 rounded border p-3">
        <button
          onClick={() => setIsCutListOpen((prev) => !prev)}
          className="flex w-full items-center justify-between text-left"
        >
          <span>
            <span className="block font-semibold">Cut list</span>
            <span className="block text-sm text-gray-600">
              {cuts.length} clip{cuts.length === 1 ? "" : "s"} selected
            </span>
          </span>
          <span className="text-sm text-gray-600">
            {isCutListOpen ? "Hide" : "Show"}
          </span>
        </button>

        {isCutListOpen && (
          <div className="space-y-3">
            {cuts.map((cut, index) => (
              <div
                key={index}
                className={`grid gap-3 rounded border p-3 md:grid-cols-5 ${
                  selectedCutIndex === index ? "border-black" : ""
                }`}
              >
                <label className="space-y-1">
                  <span className="text-sm font-medium">Start</span>
                  <input
                    value={cut.start}
                    onChange={(e) => updateCut(index, "start", e.target.value)}
                    className="w-full rounded border p-2"
                    placeholder="HH:MM:SS or HH:MM:SS:MS"
                  />
                </label>

                <label className="space-y-1">
                  <span className="text-sm font-medium">End</span>
                  <input
                    value={cut.end}
                    onChange={(e) => updateCut(index, "end", e.target.value)}
                    className="w-full rounded border p-2"
                    placeholder="HH:MM:SS or HH:MM:SS:MS"
                  />
                </label>

                <label className="space-y-1">
                  <span className="text-sm font-medium">Clip name</span>
                  <input
                    value={cut.name}
                    onChange={(e) => updateCut(index, "name", e.target.value)}
                    className="w-full rounded border p-2"
                    placeholder="clip_name"
                  />
                </label>

                <div className="flex items-end gap-2">
                  <button
                    onClick={() => setSelectedCutIndex(index)}
                    className="rounded border px-4 py-2"
                  >
                    {selectedCutIndex === index ? "Selected" : "Select"}
                  </button>
                  <button
                    onClick={() => removeCut(index)}
                    disabled={cuts.length === 1}
                    className="rounded border px-4 py-2 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-4">
        <button onClick={addCut} className="rounded border px-4 py-2">
          Add cut
        </button>

        <button
          onClick={submitCuts}
          disabled={isSubmitting}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {isSubmitting ? "Starting..." : "Cut video"}
        </button>

        <button
          onClick={submitCutAndPrepareShorts}
          disabled={isPreparingShorts}
          className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
        >
          {isPreparingShorts ? "Starting..." : "Cut + prepare Shorts"}
        </button>

        <button
          onClick={submitShortsOnly}
          disabled={isCreatingShortsOnly}
          className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
        >
          {isCreatingShortsOnly ? "Starting..." : "Create only Shorts"}
        </button>
      </div>

      {submitError && <p className="text-sm text-red-600">{submitError}</p>}
    </div>
  );
}
