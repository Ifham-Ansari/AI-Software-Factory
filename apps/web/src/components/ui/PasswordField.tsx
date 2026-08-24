"use client";

import { useId, useState } from "react";
import type { InputHTMLAttributes } from "react";

interface PasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "name" | "type"> {
  label: string;
  name: string;
  error?: string;
  hint?: string;
}

/**
 * A password input with a show/hide toggle.
 *
 * Visibility is local component state, not written back to the form: toggling it must
 * never change what gets submitted, only how it is displayed while typing. The toggle is
 * a real button with `aria-pressed` and a label that names the resulting action ("Show
 * password" / "Hide password") rather than the current state, which reads more naturally
 * to a screen reader as something to *do*.
 */
export function PasswordField({
  label,
  name,
  error,
  hint,
  className,
  ...rest
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const reactId = useId();
  const fieldId = name || reactId;
  const errorId = `${fieldId}-error`;
  const hintId = `${fieldId}-hint`;

  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <div className="password-field">
        <input
          id={fieldId}
          name={name}
          type={visible ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : hint ? hintId : undefined}
          className={className}
          {...rest}
        />
        <button
          type="button"
          className="password-toggle"
          onClick={() => setVisible((current) => !current)}
          aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
          tabIndex={-1}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      {hint && !error && (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** An open eye — shown when the password is hidden, meaning "click to reveal". */
function EyeIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

/** A crossed-out eye — shown when the password is visible, meaning "click to hide". */
function EyeOffIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <path d="M6.61 6.61A18.5 18.5 0 0 0 1 12s4 8 11 8a9.26 9.26 0 0 0 5.39-1.61" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}
