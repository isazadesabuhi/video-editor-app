"use client";

import { useState } from "react";
import { cutVideo } from "@/lib/api";

type Cut = {
  start: string;
  end: string;
  name: string;
};

type Props = {
  videoId: string;
  onJobStarted: (job: { id: string; label: string }) => void;
};

export default function CutListEditor({ videoId, onJobStarted }: Props) {
  const [cuts, setCuts] = useState<Cut[]>([
    {
      start: "00:00:00",
      end: "00:00:10",
      name: "clip_1",
    },
  ]);
  const [mode, setMode] = useState<"copy" | "accurate">("copy");
  const [quality, setQuality] = useState<"high" | "very_high" | "lossless">(
    "high"
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateCut(index: number, field: keyof Cut, value: string) {
    setCuts((prev) =>
      prev.map((cut, i) => (i === index ? { ...cut, [field]: value } : cut))
    );
  }

  function addCut() {
    setCuts((prev) => [
      ...prev,
      {
        start: "00:00:00",
        end: "00:00:10",
        name: `clip_${prev.length + 1}`,
      },
    ]);
  }

  function removeCut(index: number) {
    setCuts((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitCuts() {
    setIsSubmitting(true);

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
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-4 rounded border p-4">
      <h2 className="text-xl font-semibold">Cut into multiple clips</h2>

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
            <option value="copy">Fast copy, original quality</option>
            <option value="accurate">Accurate, re-encode</option>
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
            <option value="high">High, CRF 18</option>
            <option value="very_high">Very high, CRF 16</option>
            <option value="lossless">Lossless</option>
          </select>
        </label>
      </div>

      {cuts.map((cut, index) => (
        <div key={index} className="grid gap-3 rounded border p-3 md:grid-cols-4">
          <label className="space-y-1">
            <span className="text-sm font-medium">Start</span>
            <input
              value={cut.start}
              onChange={(e) => updateCut(index, "start", e.target.value)}
              className="w-full rounded border p-2"
              placeholder="HH:MM:SS"
            />
          </label>

          <label className="space-y-1">
            <span className="text-sm font-medium">End</span>
            <input
              value={cut.end}
              onChange={(e) => updateCut(index, "end", e.target.value)}
              className="w-full rounded border p-2"
              placeholder="HH:MM:SS"
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

          <div className="flex items-end">
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
      </div>
    </div>
  );
}
