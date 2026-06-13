import Link from "next/link";

const tools = [
  {
    href: "/crop",
    title: "Crop video",
    description:
      "Upload a video, draw a crop area, and export either a custom crop or a 9:16 social video.",
    cta: "Open crop tool",
  },
  {
    href: "/cut",
    title: "Cut video",
    description:
      "Upload a video and export timestamp-based clips without using the crop editor.",
    cta: "Open cut tool",
  },
];

export default function HomePage() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">Video editor</h1>
        <p className="text-gray-600">Choose the workflow you need.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {tools.map((tool) => (
          <section key={tool.href} className="space-y-4 rounded border p-4">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">{tool.title}</h2>
              <p className="text-sm text-gray-600">{tool.description}</p>
            </div>

            <Link
              href={tool.href}
              className="inline-flex rounded bg-black px-4 py-2 text-white"
            >
              {tool.cta}
            </Link>
          </section>
        ))}
      </div>
    </main>
  );
}
