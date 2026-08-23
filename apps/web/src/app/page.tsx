import { redirect } from "next/navigation";
import { hasSession } from "@/lib/auth/session";

/**
 * The root path is a router, not a page.
 *
 * A cookie only decides *where* to send someone. It is never treated as proof of
 * anything: the destination re-checks with the backend, which is the only authority on
 * whether a session is real.
 */
export default async function HomePage() {
  redirect((await hasSession()) ? "/projects" : "/login");
}
