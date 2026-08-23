"use client";

import { useEffect } from "react";
import { Alert, Button } from "@/components/ui";

/**
 * The last line of defence for an unexpected client-side failure.
 *
 * Deliberately shows no technical detail. `error.digest` is a server-generated id that
 * correlates with the server log holding the real stack trace, which is what someone
 * reporting a problem should quote.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled application error", error);
  }, [error]);

  return (
    <main className="error-page">
      <h1>Something went wrong</h1>
      <Alert variant="error">
        The page could not be displayed. Trying again often resolves it.
      </Alert>
      {error.digest && (
        <p className="muted">
          Reference: <code>{error.digest}</code>
        </p>
      )}
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
