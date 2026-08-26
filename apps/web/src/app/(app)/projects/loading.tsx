import { ProjectListSkeleton } from "@/features/projects/ProjectListSkeleton";

/**
 * Shown while the projects page streams in.
 *
 * Deliberately the same placeholder the page's own Suspense boundary uses: a navigation
 * that swaps one loading shape for another reads as two loads rather than one.
 */
export default function Loading() {
  return (
    <div className="projects-page">
      <div className="projects-main">
        <h1>Projects</h1>
        <ProjectListSkeleton />
      </div>
    </div>
  );
}
