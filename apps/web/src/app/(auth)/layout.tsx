import { redirect } from "next/navigation";
import { hasSession } from "@/lib/auth/session";
import { ThemeToggle } from "@/components/ui";

/**
 * Layout for signed-out pages.
 *
 * Someone already carrying a session should not see a sign-in form; send them to the app.
 */
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  if (await hasSession()) {
    redirect("/projects");
  }
  return (
    <main className="auth-layout">
      {/* Reachable before signing in: someone who cannot read the form is not helped by a
          theme switch that lives behind it. */}
      <div className="auth-layout-toolbar">
        <ThemeToggle />
      </div>
      {children}
    </main>
  );
}
