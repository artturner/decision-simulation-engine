export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-3xl font-bold">Branching Scenarios</h1>
      <p className="mt-4 text-gray-600">
        Navigate to{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-sm">
          /scenarios/[slug]
        </code>{" "}
        to start a scenario.
      </p>
    </main>
  );
}
