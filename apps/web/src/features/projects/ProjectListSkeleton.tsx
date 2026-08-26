/**
 * The shape the project list is about to take [F-222].
 *
 * A skeleton rather than a spinner, and a project-shaped one rather than a row of plain
 * bars: the point of a placeholder is that the layout does not jump when the real content
 * lands, and a generic block that is the wrong height guarantees it will. Each placeholder
 * mirrors a `ProjectCard` — title, status pill, description line, metadata line — so the
 * page settles in place rather than reflowing.
 *
 * `aria-hidden` with a single live region beside it: a screen reader user needs to be told
 * "loading", once, not to have four decorative bars described to them.
 */
export function ProjectListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="project-skeleton" data-testid="project-skeleton">
      <p className="visually-hidden" role="status">
        Loading projects…
      </p>
      <ul aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="project-skeleton-card">
            <div className="project-skeleton-header">
              <span className="shimmer project-skeleton-title" />
              <span className="shimmer project-skeleton-badge" />
            </div>
            <span className="shimmer project-skeleton-line" />
            <span className="shimmer project-skeleton-meta" />
          </li>
        ))}
      </ul>
    </div>
  );
}
