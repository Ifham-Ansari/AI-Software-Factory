"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Alert, Button } from "@/components/ui";

/** Error boundary for the authenticated area, keeping the app shell intact. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error", error);
  }, [error]);

  return (
    <div className="error-page">
      <h1>Something went wrong</h1>
      <Alert variant="error">
        We could not load this page. It may be a temporary problem.
      </Alert>
      <div className="error-actions">
        <Button onClick={reset}>Try again</Button>
        <Link href="/projects">Back to projects</Link>
      </div>
    </div>
  );
}
