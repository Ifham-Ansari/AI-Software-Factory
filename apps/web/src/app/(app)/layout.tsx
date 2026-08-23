import { redirect } from "next/navigation";
import Link from "next/link";
import type { UserResponse } from "@factory/contracts";
import { apiRequestOrNull } from "@/lib/api/client";
import { signOutAction } from "@/lib/actions/auth";
import { Button } from "@/components/ui";

/**
 * Layout for authenticated pages.
 *
 * This is where authentication is actually enforced on the frontend: it asks the backend
 * who the caller is, and a `null` answer means the session is gone, expired, or revoked.
 * Checking for a cookie would only prove one exists — the backend is the authority.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await apiRequestOrNull<UserResponse>("/auth/me");

  if (user === null) {
    redirect("/login");
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link href="/projects" className="app-brand">
          AI Software Factory
        </Link>
        <div className="app-user">
          <span data-testid="current-user">{user.display_name}</span>
          <form action={signOutAction}>
            <Button type="submit" variant="ghost" size="sm">
              Sign out
            </Button>
          </form>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
