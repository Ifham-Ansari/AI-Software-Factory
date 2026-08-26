import Link from "next/link";

/**
 * Filter the list by lifecycle state.
 *
 * Links, not buttons: the filter belongs in the URL so a view is shareable, survives a
 * refresh, and works without JavaScript — the same reasoning as `Pagination`.
 *
 * "All" is the default and includes archived projects. That matters more than it looks:
 * if the default listing hid them, archiving would make a project vanish with no hint
 * that it still exists, which is exactly how an archive turns into an accidental delete.
 */

const FILTERS = [
  { label: "All", value: undefined },
  { label: "Active", value: "draft" },
  { label: "Archived", value: "archived" },
] as const;

export function ProjectFilters({ current }: { current?: string }) {
  return (
    <nav className="project-filters" aria-label="Filter projects by status">
      {FILTERS.map((filter) => {
        const active = current === filter.value || (!current && !filter.value);
        return (
          <Link
            key={filter.label}
            href={filter.value ? `/projects?status=${filter.value}` : "/projects"}
            className={active ? "filter-chip filter-chip-active" : "filter-chip"}
            // The filter in force is a state, not just a style: without this a screen
            // reader hears three identical links and no indication of which is applied.
            aria-current={active ? "page" : undefined}
          >
            {filter.label}
          </Link>
        );
      })}
    </nav>
  );
}
