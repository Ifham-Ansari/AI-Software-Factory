import Link from "next/link";
import type { PageMeta } from "@factory/contracts";

/**
 * Page navigation.
 *
 * Rendered as links rather than buttons so pages are shareable, work in a new tab, and
 * function without JavaScript. Hidden entirely when there is only one page — controls
 * that cannot do anything are noise.
 */
export function Pagination({ meta, status }: { meta: PageMeta; status?: string }) {
  if (meta.total_pages <= 1) return null;

  // The filter has to survive paging. Without it, page 2 of "Archived" silently becomes
  // page 2 of everything, and the list appears to change under the user.
  const href = (page: number): string => {
    const query = new URLSearchParams({ page: String(page) });
    if (status) query.set("status", status);
    return `/projects?${query}`;
  };

  return (
    <nav className="pagination" aria-label="Pagination">
      {meta.has_previous ? (
        <Link href={href(meta.page - 1)} rel="prev">
          ← Previous
        </Link>
      ) : (
        <span className="pagination-disabled">← Previous</span>
      )}

      <span aria-current="page">
        Page {meta.page} of {meta.total_pages}
      </span>

      {meta.has_next ? (
        <Link href={href(meta.page + 1)} rel="next">
          Next →
        </Link>
      ) : (
        <span className="pagination-disabled">Next →</span>
      )}
    </nav>
  );
}
