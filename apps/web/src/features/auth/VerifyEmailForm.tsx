"use client";

import { useActionState, useEffect, useState } from "react";
import Link from "next/link";
import { Alert, Button, CodeInput } from "@/components/ui";
import { initialFormState } from "@/lib/actions/state";
import { resendVerificationAction, verifyEmailAction } from "@/lib/actions/auth";

const RESEND_COOLDOWN_SECONDS = 60;

interface VerifyEmailFormProps {
  email: string;
}

/**
 * The second step of registration: enter the 6-digit code that was emailed.
 *
 * The resend cooldown here is a client-side courtesy, not a security control — the
 * server enforces the real limit and returns the same response either way. This countdown
 * only stops someone from mashing the button; it is fine if it drifts from the server's.
 */
export function VerifyEmailForm({ email }: VerifyEmailFormProps) {
  const [verifyState, verifyAction, verifying] = useActionState(
    verifyEmailAction,
    initialFormState,
  );
  const [resendState, resendAction, resending] = useActionState(
    resendVerificationAction,
    initialFormState,
  );
  const [cooldown, setCooldown] = useState(0);

  // Starting the cooldown when a resend succeeds is state derived from another state
  // value, not a synchronization with anything external — so it belongs during render
  // (React's documented pattern for this), not in an Effect reacting to `resendState`.
  const [seenResendState, setSeenResendState] = useState(resendState);
  if (resendState !== seenResendState) {
    setSeenResendState(resendState);
    if (resendState.success) {
      setCooldown(RESEND_COOLDOWN_SECONDS);
    }
  }

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  return (
    <div className="auth-card">
      <div className="auth-mark" aria-hidden="true">
        <MailMark />
      </div>
      <h1>Check your email</h1>
      <p className="auth-subtitle">
        We sent a 6-digit code to <strong>{email}</strong>. Enter it below to finish creating
        your account.
      </p>

      {verifyState.error && <Alert variant="error">{verifyState.error}</Alert>}

      <form action={verifyAction} noValidate>
        <input type="hidden" name="email" value={email} />
        <CodeInput name="code" error={verifyState.fieldErrors?.code} />
        <Button type="submit" loading={verifying} className="btn-block">
          Verify email
        </Button>
      </form>

      <div className="auth-resend">
        {resendState.message && <p className="auth-resend-message">{resendState.message}</p>}
        {resendState.error && <Alert variant="error">{resendState.error}</Alert>}
        <form action={resendAction}>
          <input type="hidden" name="email" value={email} />
          <Button
            type="submit"
            variant="ghost"
            loading={resending}
            disabled={cooldown > 0}
            className="btn-block"
          >
            {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
          </Button>
        </form>
      </div>

      <p className="auth-switch">
        Wrong address? <Link href="/register">Start over</Link>
      </p>
    </div>
  );
}

/** A minimal envelope mark, matching the factory mark used on the other auth screens. */
function MailMark() {
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
      <rect width="36" height="36" rx="10" className="auth-mark-bg" />
      <path
        d="M9 13h18v10a1 1 0 0 1-1 1H10a1 1 0 0 1-1-1V13Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M9 13l9 6 9-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
