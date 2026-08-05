import type { Metadata } from "next";
import { headers } from "next/headers";
import Providers from "./providers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const ogImage = `${protocol}://${host}/og.png`;

  return {
    title: "Branching Scenarios — What Will You Choose?",
    description: "Step inside the decisions that shaped our world. Every choice changes the story, and every ending is earned.",
    openGraph: {
      title: "What Will You Choose?",
      description: "Branching historical and civic scenarios where every choice changes the story.",
      images: [{ url: ogImage, width: 1734, height: 907, alt: "What Will You Choose? Branching Scenarios" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "What Will You Choose?",
      description: "Branching historical and civic scenarios where every choice changes the story.",
      images: [ogImage],
    },
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
