"use client";

import { useEffect } from "react";
import {
  getApiErrorMessage,
  getDownloadUrl,
  getJob,
  type JobStatus,
} from "@/lib/api";

type Props = {
  jobs: JobStatus[];
  onJobUpdate: (job: JobStatus) => void;
};

export default function JobStatusList({ jobs, onJobUpdate }: Props) {
  useEffect(() => {
    const activeJobs = jobs.filter((job) => job.status === "processing");

    if (activeJobs.length === 0) return;

    function pollActiveJobs() {
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
            error: getApiErrorMessage(error, "Could not fetch job status"),
          });
        }
      });
    }

    pollActiveJobs();

    const timer = window.setInterval(pollActiveJobs, 1500);

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
                {job.status === "done" &&
                  (job.cut_output_dir || job.shorts_output_dir
                    ? "Ready in output folders"
                    : "Ready to download")}
                {job.status === "failed" && (job.error || "Export failed")}
              </p>

              {job.status === "done" && job.cut_output_dir && (
                <p className="mt-2 text-sm text-gray-600">
                  Raw cuts:{" "}
                  <code className="rounded bg-gray-100 px-1">
                    {job.cut_output_dir}
                  </code>
                </p>
              )}

              {job.status === "done" && job.shorts_output_dir && (
                <p className="mt-1 text-sm text-gray-600">
                  Shorts clips:{" "}
                  <code className="rounded bg-gray-100 px-1">
                    {job.shorts_output_dir}
                  </code>
                </p>
              )}
            </div>

            {job.status === "done" && (job.output || job.archive) && (
              <div className="flex flex-wrap gap-2">
                <a
                  href={getDownloadUrl(job.id)}
                  className="w-fit rounded bg-black px-4 py-2 text-sm text-white"
                >
                  Download
                </a>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
