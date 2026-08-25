import type { ConfigurationResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";

/**
 * What a project still needs before it can be built.
 *
 * A Server Component: this is read-only data with no interactivity, so shipping a client
 * bundle for it would buy nothing. Storing a credential is a separate, deliberate flow —
 * this panel only reports what is missing.
 *
 * Handles all four states. "Failed to load" is its own case rather than being collapsed
 * into "empty": a project with no requirements and a project whose configuration could
 * not be read mean opposite things to a user.
 */
export async function ProjectConfiguration({ projectId }: { projectId: string }) {
  let report: ConfigurationResponse | null = null;
  try {
    report = await apiRequest<ConfigurationResponse>(
      `/projects/${projectId}/configuration`,
    );
  } catch {
    // Degrades to a notice: a configuration read failing must not blank the whole page.
    report = null;
  }

  if (report === null) {
    return (
      <section className="panel" aria-labelledby="config-heading">
        <h2 id="config-heading">Configuration</h2>
        <p className="muted">Configuration could not be loaded. Try refreshing.</p>
      </section>
    );
  }

  if (report.requirements.length === 0) {
    return (
      <section className="panel" aria-labelledby="config-heading">
        <h2 id="config-heading">Configuration</h2>
        <p className="muted">
          Nothing required yet. Requirements appear once the project is planned.
        </p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="config-heading">
      <h2 id="config-heading">Configuration</h2>
      <p className={report.is_satisfied ? "config-ready" : "muted"}>
        {report.is_satisfied
          ? "All required configuration is present."
          : `${report.missing.length} item(s) still needed.`}
      </p>

      <ul className="config-list" data-testid="config-list">
        {report.requirements.map((requirement) => (
          <li key={requirement.key} className="config-row" data-testid="config-row">
            <span className="config-key">{requirement.key}</span>
            <span
              className={
                requirement.satisfied ? "config-state config-set" : "config-state config-missing"
              }
            >
              {/* Spelled out, not colour alone. */}
              {requirement.satisfied ? "Set" : "Missing"}
            </span>
            <span className="config-description muted">{requirement.description}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
