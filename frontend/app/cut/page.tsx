"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CutListEditor from "@/components/CutListEditor";
import JobStatusList from "@/components/JobStatusList";
import VideoUploadStep from "@/components/VideoUploadStep";
import { uploadVideo, type JobStatus } from "@/lib/api";

export default function CutPage() {
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
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

  return (
    <main className="mx-auto max-w-6xl space-y-8 p-8">
      <div className="space-y-2">
        <Link href="/" className="text-sm text-blue-700">
          Back to tools
        </Link>
        <h1 className="text-3xl font-bold">Cut video</h1>
      </div>

      <VideoUploadStep
        file={file}
        uploadMessage={uploadMessage}
        onFileChange={handleFileChange}
        onUpload={handleUpload}
      />

      {videoUrl && (
        <section className="space-y-4 rounded border p-4">
          <h2 className="text-xl font-semibold">2. Preview video</h2>
          <video src={videoUrl} controls className="w-full bg-black" />
        </section>
      )}

      {videoId && (
        <section className="space-y-4">
          <h2 className="text-xl font-semibold">3. Add cuts</h2>
          <CutListEditor videoId={videoId} onJobStarted={addJob} />
        </section>
      )}

      {!videoId && videoUrl && (
        <p className="text-sm text-gray-600">
          Upload the video to the backend before adding cuts.
        </p>
      )}

      <JobStatusList jobs={jobs} onJobUpdate={updateJob} />
    </main>
  );
}
