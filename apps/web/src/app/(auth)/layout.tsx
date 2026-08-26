import { redirect } from "next/navigation";
import { hasSession } from "@/lib/auth/session";
import { ThemeToggle } from "@/components/ui";

/**
 * Layout for signed-out pages.
 *
 * Someone already carrying a session should not see a sign-in form; send them to the app.
 *
 * **The theme toggle sits inside the card, not above it.** It has to be reachable before
 * signing in — someone who cannot read the form is not helped by a switch that lives
 * behind it — but floating it over the page made it look like stray browser furniture
 * rather than part of the product. Positioning it against the card's own box puts it in
 * the corner opposite the mark, where it reads as a control belonging to this panel, and
 * keeps it there at every width because the wrapper is the card's width. It is rendered
 * before the card so it comes first in the tab order, as it did when it was a toolbar.
 *
 * One toggle, in the layout, serves sign-in, registration and email verification alike —
 * a copy per page would be three controls to keep in step for no gain.
 */
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  if (await hasSession()) {
    redirect("/projects");
  }
  return (
    <main className="auth-layout">
      <div className="auth-panel">
        <ThemeToggle />
        {children}
      </div>
    </main>
  );
}
