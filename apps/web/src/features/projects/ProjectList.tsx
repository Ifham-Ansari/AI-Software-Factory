import type { ProjectResponse, PageMeta } from "@factory/contracts";
import { EmptyState } from "@/components/ui";
import { ProjectCard } from "./ProjectCard";
import { Pagination } from "./Pagination";

interface ProjectListProps {
  projects: ProjectResponse[];
  meta: PageMeta;
}

/**
 * The project list.
 *
 * Handles the empty case explicitly. An empty collection is a normal state and the moment
 * a new user is most likely to be lost, so it says what to do next rather than rendering
 * an empty box.
 */
export function ProjectList({ projects, meta }: ProjectListProps) {
  if (projects.length === 0) {
    return (
      <EmptyState
        title="No projects yet"
        description="Create your first project to get started."
      />
    );
  }

  return (
    <>
      <ul className="project-list">
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </ul>
      <Pagination meta={meta} />
    </>
  );
}
