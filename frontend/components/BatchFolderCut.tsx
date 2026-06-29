"use client";

import { useState } from "react";
import { batchCutFolder, getApiErrorMessage } from "@/lib/api";

type Props = {
  onJobStarted: (job: { id: string; label: string }) => void;
};

type OutputKind = "cut_only" | "cut_and_prepare_shorts" | "shorts_only";
type CutMode = "copy" | "accurate";
type Quality = "high" | "very_high" | "lossless";
type ShortsMode = "fit_padding" | "blur_background" | "crop_fill";

export default function BatchFolderCut({ onJobStarted }: Props) {
  const [folderPath, setFolderPath] = useState(
    "C:\\Users\\sabuh\\Desktop\\Projects\\video-editor-app\\backend\\app\\storage\\uploads"
  );
  const [recursive, setRecursive] = useState(false);
  const [outputKind, setOutputKind] =
    useState<OutputKind>("cut_and_prepare_shorts");
  const [sceneThreshold, setSceneThreshold] = useState(0.35);
  const [minClipSeconds, setMinClipSeconds] = useState(2);
  const [endTrimMs, setEndTrimMs] = useState(120);
  const [mode, setMode] = useState<CutMode>("accurate");
  const [quality, setQuality] = useState<Quality>("very_high");
  const [shortsMode, setShortsMode] = useState<ShortsMode>("blur_background");
  const [shortsQuality, setShortsQuality] = useState<Quality>("high");
  const [removeBlackScreens, setRemoveBlackScreens] = useState(false);
  const [blackMinDurationSeconds, setBlackMinDurationSeconds] = useState(0.08);
  const [blackPixelThreshold, setBlackPixelThreshold] = useState(0.16);
  const [blackPictureThreshold, setBlackPictureThreshold] = useState(0.95);
  const [blackTrimPaddingMs, setBlackTrimPaddingMs] = useState(160);
  const [maxVideos, setMaxVideos] = useState(200);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startBatchCut() {
    if (!folderPath.trim()) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const result = await batchCutFolder({
        folder_path: folderPath.trim(),
        recursive,
        output_kind: outputKind,
        threshold: sceneThreshold,
        min_clip_seconds: minClipSeconds,
        end_trim_ms: endTrimMs,
        mode,
        quality,
        shorts_mode: shortsMode,
        shorts_quality: shortsQuality,
        remove_black_screens: removeBlackScreens,
        black_min_duration_seconds: blackMinDurationSeconds,
        black_pixel_threshold: blackPixelThreshold,
        black_picture_threshold: blackPictureThreshold,
        black_trim_padding_ms: blackTrimPaddingMs,
        max_videos: maxVideos,
      });

      onJobStarted({
        id: result.job_id,
        label: `Batch folder cut (${result.video_count} video${
          result.video_count === 1 ? "" : "s"
        })`,
      });
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not start batch cut"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="space-y-4 rounded border p-4">
      <div>
        <h2 className="text-xl font-semibold">Batch cut local folder</h2>
        <p className="text-sm text-gray-600">
          Process every video in a local folder with auto-detected cuts. Manual one-by-one upload still works above.
        </p>
      </div>

      <label className="block space-y-1">
        <span className="text-sm font-medium">Local folder path</span>
        <input
          value={folderPath}
          onChange={(event) => setFolderPath(event.target.value)}
          className="w-full rounded border p-2"
          placeholder="C:\Users\you\Videos\clips"
        />
      </label>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1">
          <span className="text-sm font-medium">Output</span>
          <select
            value={outputKind}
            onChange={(event) => setOutputKind(event.target.value as OutputKind)}
            className="w-full rounded border p-2"
          >
            <option value="cut_and_prepare_shorts">Cut + prepare Shorts</option>
            <option value="shorts_only">Create only Shorts</option>
            <option value="cut_only">Cut video files only</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Cut mode</span>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as CutMode)}
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
            onChange={(event) => setQuality(event.target.value as Quality)}
            disabled={mode === "copy"}
            className="w-full rounded border p-2 disabled:opacity-50"
          >
            <option value="very_high">Very high, CRF 16</option>
            <option value="high">High, CRF 18</option>
            <option value="lossless">Lossless</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-sm font-medium">Max videos</span>
          <input
            type="number"
            min="1"
            max="1000"
            value={maxVideos}
            onChange={(event) => setMaxVideos(Number(event.target.value))}
            className="w-full rounded border p-2"
          />
        </label>
      </div>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={recursive}
          onChange={(event) => setRecursive(event.target.checked)}
        />
        <span className="text-sm font-medium">Include subfolders</span>
      </label>

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

      {outputKind !== "cut_only" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1">
            <span className="text-sm font-medium">Shorts layout</span>
            <select
              value={shortsMode}
              onChange={(event) => setShortsMode(event.target.value as ShortsMode)}
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
              onChange={(event) => setShortsQuality(event.target.value as Quality)}
              className="w-full rounded border p-2"
            >
              <option value="high">High, CRF 18</option>
              <option value="very_high">Very high, CRF 16</option>
              <option value="lossless">Lossless</option>
            </select>
          </label>
        </div>
      )}

      <div className="space-y-3 rounded border border-gray-200 p-3">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={removeBlackScreens}
            onChange={(event) => setRemoveBlackScreens(event.target.checked)}
          />
          <span className="text-sm font-medium">Remove black dividers</span>
        </label>

        <div className="grid gap-4 sm:grid-cols-4">
          <label className="space-y-1">
            <span className="text-sm font-medium">Minimum black seconds</span>
            <input
              type="number"
              min="0.05"
              max="10"
              step="0.01"
              value={blackMinDurationSeconds}
              onChange={(event) =>
                setBlackMinDurationSeconds(Number(event.target.value))
              }
              disabled={!removeBlackScreens}
              className="w-full rounded border p-2 disabled:opacity-50"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">Darkness tolerance</span>
            <input
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value={blackPixelThreshold}
              onChange={(event) => setBlackPixelThreshold(Number(event.target.value))}
              disabled={!removeBlackScreens}
              className="w-full rounded border p-2 disabled:opacity-50"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">Frame coverage</span>
            <input
              type="number"
              min="0.5"
              max="1"
              step="0.01"
              value={blackPictureThreshold}
              onChange={(event) =>
                setBlackPictureThreshold(Number(event.target.value))
              }
              disabled={!removeBlackScreens}
              className="w-full rounded border p-2 disabled:opacity-50"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">Trim padding ms</span>
            <input
              type="number"
              min="0"
              max="2000"
              step="20"
              value={blackTrimPaddingMs}
              onChange={(event) => setBlackTrimPaddingMs(Number(event.target.value))}
              disabled={!removeBlackScreens}
              className="w-full rounded border p-2 disabled:opacity-50"
            />
          </label>
        </div>
      </div>

      <button
        onClick={startBatchCut}
        disabled={!folderPath.trim() || isSubmitting}
        className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
      >
        {isSubmitting ? "Starting..." : "Batch cut folder"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
