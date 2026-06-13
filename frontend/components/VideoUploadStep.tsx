"use client";

type Props = {
  file: File | null;
  uploadMessage: string | null;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onUpload: () => void;
};

export default function VideoUploadStep({
  file,
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
        disabled={!file}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        Upload to backend
      </button>

      {uploadMessage && <p className="text-sm text-gray-600">{uploadMessage}</p>}
    </section>
  );
}
