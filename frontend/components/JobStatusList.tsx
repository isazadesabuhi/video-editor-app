"use client";

import { useEffect } from "react";
import { getDownloadUrl, getJob, type JobStatus } from "@/lib/api";

type Props = {
  jobs: JobStatus[];
  onJobUpdate: (job: JobStatus) => void;
};

export default function JobStatusList({ jobs, onJobUpdate }: Props) {
  useEffect(() => {
    const activeJobs = jobs.filter((job) => job.status === "processing");

    if (activeJobs.length === 0) return;

    const timer = window.setInterval(() => {
      activeJobs.forEach(async (job) => {
        try {
          const result = await getJob(job.id);

          onJobUpdate({
            ...job,
            ...result,
            id: job.id,
            label: job.label,
          });
        } catch (error) {
          onJobUpdate({
            ...job,
            status: "failed",
            error:
              error instanceof Error
                ? error.message
                : "Could not fetch job status",
          });
        }
      });
    }, 1500);

    return () => window.clearInterval(timer);
  }, [jobs, onJobUpdate]);

  if (jobs.length === 0) return null;

  return (
    <section className="space-y-3 rounded border p-4">
      <h2 className="text-xl font-semibold">Exports</h2>

      <div className="space-y-3">
        {jobs.map((job) => (
          <div
            key={job.id}
            className="flex flex-col gap-3 rounded border p-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-medium">{job.label}</p>
              <p className="text-sm text-gray-600">
                {job.status === "processing" && "Processing"}
                {job.status === "done" && "Ready to download"}
                {job.status === "failed" && (job.error || "Export failed")}
              </p>
            </div>

            {job.status === "done" && (
              <a
                href={getDownloadUrl(job.id)}
                className="w-fit rounded bg-black px-4 py-2 text-sm text-white"
              >
                Download
              </a>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
