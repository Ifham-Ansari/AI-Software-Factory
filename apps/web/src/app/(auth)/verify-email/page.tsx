import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { VerifyEmailForm } from "@/features/auth/VerifyEmailForm";

export const metadata: Metadata = { title: "Verify your email" };

interface VerifyEmailPageProps {
  searchParams: Promise<{ email?: string }>;
}

export default async function VerifyEmailPage({ searchParams }: VerifyEmailPageProps) {
  const { email } = await searchParams;

  // The code-entry step is meaningless without knowing which address it applies to.
  if (!email) {
    redirect("/register");
  }

  return <VerifyEmailForm email={email} />;
}
