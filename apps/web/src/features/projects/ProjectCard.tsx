import Link from "next/link";
import type { ProjectResponse } from "@factory/contracts";
import { StatusBadge } from "@/components/ui";

/** Format a timestamp for display, tolerating a malformed value from the wire. */
function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "unknown"
    : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** One project in the list. */
export function ProjectCard({ project }: { project: ProjectResponse }) {
  return (
    <li className="project-card" data-testid="project-card">
      <div className="project-card-header">
        <h3>
          <Link href={`/projects/${project.id}`}>{project.name}</Link>
        </h3>
        <StatusBadge status={project.status} />
      </div>
      {project.description && <p className="project-description">{project.description}</p>}
      <p className="project-meta">
        <span className="project-slug">{project.slug}</span>
        <span aria-hidden="true"> · </span>
        <span>Created {formatDate(project.created_at)}</span>
      </p>
    </li>
  );
}
