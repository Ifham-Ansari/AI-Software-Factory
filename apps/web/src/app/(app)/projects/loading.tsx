import { Skeleton } from "@/components/ui";

/** Shown while the projects page streams in. */
export default function Loading() {
  return (
    <div className="projects-page">
      <div className="projects-main">
        <h1>Projects</h1>
        <Skeleton rows={3} />
      </div>
    </div>
  );
}
