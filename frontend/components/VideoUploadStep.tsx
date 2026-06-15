"use client";

type Props = {
  file: File | null;
  isUploading: boolean;
  uploadProgress: number | null;
  uploadMessage: string | null;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onUpload: () => void;
};

export default function VideoUploadStep({
  file,
  isUploading,
  uploadProgress,
  uploadMessage,
  onFileChange,
  onUpload,
}: Props) {
  return (
    <section className="space-y-4 rounded border p-4">
      <h2 className="text-xl font-semibold">1. Upload video</h2>

      <input type="file" accept="video/*" onChange={onFileChange} />

      <button
        onClick={onUpload}
        disabled={!file || isUploading}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {isUploading ? "Uploading..." : "Upload to backend"}
      </button>

      {isUploading && uploadProgress !== null && (
        <div className="max-w-md space-y-1">
          <div className="h-2 overflow-hidden rounded bg-gray-200">
            <div
              className="h-full rounded bg-blue-600 transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-sm text-gray-600">{uploadProgress}% uploaded</p>
        </div>
      )}

      {uploadMessage && <p className="text-sm text-gray-600">{uploadMessage}</p>}
    </section>
  );
}
