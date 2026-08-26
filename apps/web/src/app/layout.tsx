import type { Metadata } from "next";
import { ToastProvider } from "@/components/ui";
import { DEFAULT_THEME, THEME_INIT_SCRIPT } from "@/lib/theme/theme";
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

/**
 * `suppressHydrationWarning` on <html> and <body> covers attributes injected by browser
 * extensions before React hydrates — password managers, antivirus and accessibility
 * add-ons all stamp the document root (`bis_register`, `__processed_<uuid>__`,
 * `data-lt-installed`). Those are not our markup and there is nothing to fix in it.
 *
 * It suppresses one level only, and does not cascade to descendants, so a genuine
 * mismatch inside the app still reports normally. That narrowness is the reason it is
 * safe here and would not be if applied more widely: these two elements render fixed
 * attributes, so a real mismatch on them is close to impossible, while every element
 * below them still renders data.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme={DEFAULT_THEME} suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before the first paint. Anything later — including
            hydration — shows a frame of the wrong colours on every load. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body suppressHydrationWarning>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
