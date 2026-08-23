import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

interface BaseProps {
  label: string;
  name: string;
  /** Validation message. Its presence is what marks the field invalid. */
  error?: string;
  hint?: string;
}

type InputProps = BaseProps & Omit<InputHTMLAttributes<HTMLInputElement>, "name">;
type TextareaProps = BaseProps & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "name">;

/**
 * A labelled text input.
 *
 * The label is a real `<label>` bound by `htmlFor`, and the error is wired through
 * `aria-describedby` with `role="alert"`. A screen reader user then hears the problem
 * when it appears, rather than discovering that submitting silently did nothing.
 */
export function Field({ label, name, error, hint, ...rest }: InputProps) {
  const errorId = `${name}-error`;
  const hintId = `${name}-hint`;
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <input
        id={name}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
        {...rest}
      />
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

/** A labelled multi-line input, with the same accessibility wiring as `Field`. */
export function TextareaField({ label, name, error, hint, ...rest }: TextareaProps) {
  const errorId = `${name}-error`;
  const hintId = `${name}-hint`;
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <textarea
        id={name}
        name={name}
        rows={3}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
        {...rest}
      />
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
