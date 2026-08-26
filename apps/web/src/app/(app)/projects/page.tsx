import type { Metadata } from "next";
import { Suspense } from "react";
import type { PaginatedProjects } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { Skeleton } from "@/components/ui";
import { CreateProjectForm } from "@/features/projects/CreateProjectForm";
import { ProjectList } from "@/features/projects/ProjectList";

export const metadata: Metadata = { title: "Projects" };

interface PageProps {
  searchParams: Promise<{ page?: string; search?: string; status?: string }>;
}

/** Fetch and render the list. Split out so Suspense can stream it. */
async function Projects({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = new URLSearchParams();
  // Clamped rather than trusted: a caller-supplied page number reaches the API, and the
  // API rejects out-of-range values with a 422 that would surface as an error page.
  const page = Number.parseInt(params.page ?? "1", 10);
  query.set("page", String(Number.isFinite(page) && page > 0 ? page : 1));
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);

  const result = await apiRequest<PaginatedProjects>(`/projects?${query}`);
  return <ProjectList projects={result.items} meta={result.meta} status={params.status} />;
}

export default async function ProjectsPage({ searchParams }: PageProps) {
  return (
    <div className="projects-page">
      <div className="projects-main">
        <h1>Projects</h1>
        <Suspense fallback={<Skeleton rows={3} />}>
          <Projects searchParams={searchParams} />
        </Suspense>
      </div>
      <aside className="projects-sidebar">
        <CreateProjectForm />
      </aside>
    </div>
  );
}
