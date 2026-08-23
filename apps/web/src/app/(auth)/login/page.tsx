import type { Metadata } from "next";
import { AuthForm } from "@/features/auth/AuthForm";
import { signInAction } from "@/lib/actions/auth";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return <AuthForm mode="sign-in" action={signInAction} />;
}
