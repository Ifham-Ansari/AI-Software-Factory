/**
 * Shared API contracts.
 *
 * `api.ts` is generated from the backend's OpenAPI schema and must never be hand-edited;
 * CI regenerates it and fails on any diff. This file gives the generated shapes readable
 * names so application code does not reach into `components["schemas"][...]` everywhere.
 *
 * Regenerate after any API change:
 *   uv run python scripts/export_openapi.py
 *   pnpm --filter @factory/contracts generate
 */

import type { components, paths } from "./api";

export type { components, paths };

type Schemas = components["schemas"];

// --- Errors ----------------------------------------------------------------

/** The envelope every non-2xx response uses. */
export type ErrorResponse = Schemas["ErrorResponse"];
/** The error itself, carrying the stable `code` clients branch on. */
export type ErrorBody = Schemas["ErrorBody"];
/** One field-level validation problem. */
export type ErrorDetail = Schemas["ErrorDetail"];
/** Stable machine-readable error identifiers. */
export type ErrorCode = Schemas["ErrorCode"];

// --- Authentication --------------------------------------------------------

export type RegisterRequest = Schemas["RegisterRequest"];
export type SignInRequest = Schemas["SignInRequest"];
export type RefreshRequest = Schemas["RefreshRequest"];
export type SignOutRequest = Schemas["SignOutRequest"];
export type SessionResponse = Schemas["SessionResponse"];
export type UserResponse = Schemas["UserResponse"];

// --- Projects --------------------------------------------------------------

export type CreateProjectRequest = Schemas["CreateProjectRequest"];
export type UpdateProjectRequest = Schemas["UpdateProjectRequest"];
export type ProjectResponse = Schemas["ProjectResponse"];
export type ProjectStatus = Schemas["ProjectStatus"];

/** Pagination metadata returned alongside a page of items. */
export type PageMeta = Schemas["PageMeta"];
export type PaginatedProjects = Schemas["PaginatedResponse_ProjectResponse_"];

// --- Platform --------------------------------------------------------------

export type HealthResponse = Schemas["HealthResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];
export type MessageResponse = Schemas["MessageResponse"];
