"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Alert, Button, Field } from "@/components/ui";
import { initialFormState, type FormState } from "@/lib/actions/state";
import { MIN_PASSWORD_LENGTH } from "@/lib/validation";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

interface AuthFormProps {
  mode: "sign-in" | "register";
  action: Action;
}

/**
 * Sign-in and registration.
 *
 * One component for both because they differ only by a field and some copy; two
 * near-identical forms would drift in their validation and error handling.
 *
 * Built on `useActionState`, so it submits as a plain HTML form when JavaScript has not
 * loaded yet and progressively upgrades to inline errors and a pending state once it has.
 */
export function AuthForm({ mode, action }: AuthFormProps) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const isRegister = mode === "register";
  const errors = state.fieldErrors ?? {};

  return (
    <div className="auth-card">
      <h1>{isRegister ? "Create your account" : "Sign in"}</h1>
      <p className="auth-subtitle">
        {isRegister
          ? "Describe what you want built. The factory does the rest."
          : "Welcome back."}
      </p>

      {state.error && <Alert variant="error">{state.error}</Alert>}

      <form action={formAction} noValidate>
        {isRegister && (
          <Field
            label="Name"
            name="display_name"
            type="text"
            autoComplete="name"
            required
            error={errors.display_name}
          />
        )}

        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          required
          error={errors.email}
        />

        <Field
          label="Password"
          name="password"
          type="password"
          // A new password gets `new-password` so managers offer to generate one;
          // an existing one gets `current-password` so they autofill it.
          autoComplete={isRegister ? "new-password" : "current-password"}
          required
          error={errors.password}
          hint={isRegister ? `At least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
        />

        <Button type="submit" loading={pending} className="btn-block">
          {isRegister ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="auth-switch">
        {isRegister ? (
          <>
            Already have an account? <Link href="/login">Sign in</Link>
          </>
        ) : (
          <>
            No account yet? <Link href="/register">Create one</Link>
          </>
        )}
      </p>
    </div>
  );
}
