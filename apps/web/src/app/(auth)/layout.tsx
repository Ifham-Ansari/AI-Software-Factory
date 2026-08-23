import { redirect } from "next/navigation";
import { hasSession } from "@/lib/auth/session";

/**
 * Layout for signed-out pages.
 *
 * Someone already carrying a session should not see a sign-in form; send them to the app.
 */
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  if (await hasSession()) {
    redirect("/projects");
  }
  return <main className="auth-layout">{children}</main>;
}
