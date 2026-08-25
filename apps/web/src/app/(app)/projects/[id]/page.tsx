import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import type { ProjectResponse, RunResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { StatusBadge } from "@/components/ui";
import { ProjectActions } from "@/features/projects/ProjectActions";
import { ActivityFeed } from "@/features/runs/ActivityFeed";
import { ProjectConfiguration } from "@/features/projects/ProjectConfiguration";

interface PageProps {
  params: Promise<{ id: string }>;
}

/**
 * Load a project.
 *
 * A 404 from the API means "does not exist, or is not yours" — the backend deliberately
 * does not distinguish the two, and neither does this page.
 */
async function loadProject(id: string): Promise<ProjectResponse> {
  try {
    return await apiRequest<ProjectResponse>(`/projects/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const project = await apiRequest<ProjectResponse>(`/projects/${id}`);
    return { title: project.name };
  } catch {
    // Metadata generation must never break the page it describes.
    return { title: "Project" };
  }
}

/**
 * Ensure the project has a run to stream events against.
 *
 * Phase 3's graph will create runs as part of starting work. Until then the detail page
 * creates one on demand so the realtime pipeline has something to attach to; a failure
 * here degrades the activity feed rather than the page, so it returns null instead of
 * throwing.
 */
async function ensureRun(projectId: string): Promise<string | null> {
  try {
    const run = await apiRequest<RunResponse>(`/projects/${projectId}/runs`, {
      method: "POST",
    });
    return run.id;
  } catch {
    return null;
  }
}

export default async function ProjectDetailPage({ params }: PageProps) {
  const { id } = await params;
  const project = await loadProject(id);
  const runId = await ensureRun(id);

  return (
    <article className="project-detail">
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <Link href="/projects">← All projects</Link>
      </nav>

      <header className="project-detail-header">
        <h1>{project.name}</h1>
        <StatusBadge status={project.status} />
      </header>

      {project.description ? (
        <p className="project-description">{project.description}</p>
      ) : (
        <p className="project-description muted">No description yet.</p>
      )}

      <dl className="project-facts">
        <div>
          <dt>Slug</dt>
          <dd>{project.slug}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{new Date(project.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt>Last updated</dt>
          <dd>{new Date(project.updated_at).toLocaleString()}</dd>
        </div>
      </dl>

      <ProjectActions project={project} />

      <ProjectConfiguration projectId={project.id} />

      <ActivityFeed projectId={project.id} runId={runId} />
    </article>
  );
}
