import type { ProjectResponse, PageMeta } from "@factory/contracts";
import { EmptyState } from "@/components/ui";
import { ProjectCard } from "./ProjectCard";
import { Pagination } from "./Pagination";
import { ProjectFilters } from "./ProjectFilters";

interface ProjectListProps {
  projects: ProjectResponse[];
  meta: PageMeta;
  /** The status filter in force, if any. */
  status?: string;
}

/**
 * The project list.
 *
 * Handles the empty case explicitly. An empty collection is a normal state and the moment
 * a new user is most likely to be lost, so it says what to do next rather than rendering
 * an empty box.
 */
export function ProjectList({ projects, meta, status }: ProjectListProps) {
  if (projects.length === 0) {
    // An empty filter and an empty account mean opposite things: one is "nothing matches
    // what you asked for", the other is "you have not started yet". Telling a user with
    // twenty archived projects to "create your first project" would be nonsense.
    return (
      <>
        <ProjectFilters current={status} />
        {status ? (
          <EmptyState
            title={`No ${status === "archived" ? "archived" : "active"} projects`}
            description="Nothing here matches this filter. Try another one."
          />
        ) : (
          <EmptyState
            title="No projects yet"
            description="Create your first project to get started."
          />
        )}
      </>
    );
  }

  return (
    <>
      <ProjectFilters current={status} />
      <ul className="project-list">
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </ul>
      <Pagination meta={meta} status={status} />
    </>
  );
}
