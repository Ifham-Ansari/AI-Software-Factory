import type { ComponentPropsWithRef, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

// ComponentPropsWithRef rather than ButtonHTMLAttributes so callers can hold a ref —
// ConfirmDialog needs one to place initial focus on the safe action. In React 19 `ref` is
// an ordinary prop for function components, so no forwardRef wrapper is required.
interface ButtonProps extends ComponentPropsWithRef<"button"> {
  variant?: Variant;
  size?: Size;
  /** Renders a busy state and blocks further submits. */
  loading?: boolean;
  children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  danger: "btn-danger",
  ghost: "btn-ghost",
};

/**
 * A button.
 *
 * `loading` disables the button as well as showing a spinner: a form that is already
 * submitting must not accept a second click, which would create two projects.
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`btn ${VARIANTS[variant]} btn-${size} ${className}`.trim()}
      disabled={disabled ?? loading}
      aria-busy={loading}
      {...rest}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
