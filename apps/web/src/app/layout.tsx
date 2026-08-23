import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AI Software Factory",
    template: "%s · AI Software Factory",
  },
  description:
    "A hierarchical, supervised autonomous software engineering and deployment system.",
  // The control centre is an authenticated tool; there is nothing here to index.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
