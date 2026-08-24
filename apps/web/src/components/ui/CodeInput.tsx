"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ClipboardEvent, KeyboardEvent } from "react";

const noopSubscribe = () => () => {};

/**
 * Whether this render is happening after hydration.
 *
 * `useSyncExternalStore` is the documented way to read something that legitimately
 * differs between the server render and the client — it returns the server snapshot on
 * the first client render (avoiding a hydration mismatch) and only switches after React
 * has committed, without an Effect calling `setState` to force that second render.
 */
function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

interface CodeInputProps {
  name: string;
  length?: number;
  error?: string;
  disabled?: boolean;
  /** Used to auto-focus the first empty box and to size the boxes' `autoComplete`. */
  autoFocus?: boolean;
}

/**
 * A one-time-code entry: one box per digit, behaving as a single form field.
 *
 * Built from real `<input>` elements rather than a canvas or a masked single field, so it
 * works with password managers' OTP autofill, works with a screen reader as a normal set
 * of labelled fields, and degrades to a plain text input server-side (see the hidden
 * fallback field) if JavaScript never loads.
 *
 * Each box's value is React state, not just a DOM ref. React resets uncontrolled fields
 * inside a `<form action={...}>` once the action settles — including after a failed
 * verification — which would silently blank the hidden field a moment after a rejected
 * code, breaking the very next submission. Controlled state is immune to that reset.
 */
export function CodeInput({
  name,
  length = 6,
  error,
  disabled,
  autoFocus = true,
}: CodeInputProps) {
  const [digits, setDigits] = useState<string[]>(() => Array.from({ length }, () => ""));
  const boxRefs = useRef<(HTMLInputElement | null)[]>([]);
  const errorId = `${name}-error`;

  // The hidden field only claims `name` once hydrated. If scripting is disabled, this
  // never becomes true, so the hidden field stays nameless and does not shadow the
  // <noscript> fallback below — both fields sharing one name would otherwise submit the
  // hidden (always-empty) one first.
  const scripted = useHydrated();

  // A fresh error means the code just submitted was wrong; starting the user over on
  // empty boxes is clearer than leaving a rejected code sitting there to be edited
  // digit-by-digit. Adjusting state from a prop belongs during render, not an Effect.
  const [seenError, setSeenError] = useState(error);
  if (error !== seenError) {
    setSeenError(error);
    if (error) {
      setDigits(Array.from({ length }, () => ""));
    }
  }

  useEffect(() => {
    if (error) {
      boxRefs.current[0]?.focus();
    }
  }, [error]);

  const focusBox = (index: number) => {
    boxRefs.current[index]?.focus();
    boxRefs.current[index]?.select();
  };

  const setDigit = (index: number, value: string) => {
    setDigits((current) => current.map((digit, i) => (i === index ? value : digit)));
  };

  const handleChange = (index: number, rawValue: string) => {
    const digit = rawValue.replace(/\D/g, "").slice(-1);
    setDigit(index, digit);
    if (digit && index < length - 1) {
      focusBox(index + 1);
    }
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      focusBox(index - 1);
    } else if (event.key === "ArrowLeft" && index > 0) {
      focusBox(index - 1);
    } else if (event.key === "ArrowRight" && index < length - 1) {
      focusBox(index + 1);
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
    if (!pasted) return;
    event.preventDefault();
    setDigits((current) => current.map((digit, i) => pasted[i] ?? digit));
    focusBox(Math.min(pasted.length, length - 1));
  };

  return (
    <div className="field">
      <label htmlFor={`${name}-0`}>Verification code</label>
      <div className="code-input" role="group" aria-describedby={error ? errorId : undefined}>
        {digits.map((digit, index) => (
          <input
            key={index}
            id={`${name}-${index}`}
            ref={(el) => {
              boxRefs.current[index] = el;
            }}
            type="text"
            inputMode="numeric"
            autoComplete={index === 0 ? "one-time-code" : "off"}
            maxLength={1}
            value={digit}
            disabled={disabled}
            autoFocus={autoFocus && index === 0}
            aria-label={`Digit ${index + 1} of ${length}`}
            aria-invalid={error ? true : undefined}
            className="code-digit"
            onChange={(event) => handleChange(index, event.target.value)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            onPaste={handlePaste}
          />
        ))}
      </div>
      {/* The field the server action actually reads, kept in sync with `digits` by React
          rather than by writing DOM values directly — see the note above about form
          resets. */}
      <input
        type="hidden"
        name={scripted ? name : undefined}
        value={digits.join("")}
        readOnly
      />
      {/* Without JavaScript the boxes above cannot exist as separate fields, so a visitor
          with scripting disabled gets one plain input instead. Both can never render at
          once: <noscript> is stripped entirely once React hydrates. */}
      <noscript>
        <input
          type="text"
          inputMode="numeric"
          name={name}
          maxLength={length}
          className="code-fallback"
          aria-label="Verification code"
        />
      </noscript>
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
