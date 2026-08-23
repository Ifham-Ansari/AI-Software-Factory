import Link from "next/link";
import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="error-page">
      <EmptyState
        title="Not found"
        description="That page does not exist, or you do not have access to it."
        action={<Link href="/projects">Back to projects</Link>}
      />
    </main>
  );
}
