import type { Metadata } from "next";
import Providers from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Branching Scenarios",
  description: "Interactive branching scenario player",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
