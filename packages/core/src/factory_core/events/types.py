"""The event catalog and actor model.

``EventType`` is a closed enum, which is what makes "unknown event type rejected at the
boundary" enforceable: an event arriving with a type outside this list fails validation
rather than being stored and later confusing a client that has never heard of it.

The catalog mirrors architecture.md §10.1. Types are namespaced ``subject.verb`` and are
**stable strings** — they are persisted in ``workflow_events.type`` and matched by browser
code, so a rename is a breaking change to both. Add new members; never repurpose one.

Most of the catalog belongs to phases that have not been built yet. They are declared now
because the enum is the contract the event store validates against, and adding them later
would mean either a migration of stored rows or a second, competing enum.
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Every event this platform can emit."""

    # --- Workflow lifecycle (Phase 3+) ---
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"

    # --- Phases within a run (Phase 4) ---
    PHASE_ENTERED = "phase.entered"
    PHASE_COMPLETED = "phase.completed"

    # --- Delegation and agents (Phase 4) ---
    SUPERVISOR_DELEGATED = "supervisor.delegated"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # --- Tasks (Phase 4) ---
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_RETRYING = "task.retrying"
    TASK_REASSIGNED = "task.reassigned"

    # --- Tools (Phase 3) ---
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # --- Decisions and approvals (Phase 3/4) ---
    DECISION_RECORDED = "decision.recorded"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_CHANGES_REQUESTED = "approval.changes_requested"

    # --- Budget (Phase 3) ---
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXCEEDED = "budget.exceeded"

    # --- Migrations and deployment (Phase 7) ---
    MIGRATION_STARTED = "migration.started"
    MIGRATION_VALIDATED = "migration.validated"
    MIGRATION_APPLIED = "migration.applied"
    MIGRATION_FAILED = "migration.failed"
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_SUCCEEDED = "deployment.succeeded"
    DEPLOYMENT_FAILED = "deployment.failed"
    DEPLOYMENT_ROLLED_BACK = "deployment.rolled_back"
    HEALTHCHECK_PASSED = "healthcheck.passed"
    HEALTHCHECK_FAILED = "healthcheck.failed"

    # --- Diagnostics (Phase 2) ---
    RUN_LOG = "run.log"
    #: Emitted by the `noop` job handler. Proves the whole pipeline — enqueue, claim,
    #: execute, persist, publish, fan out to a browser — without any agent existing.
    JOB_PROGRESS = "job.progress"


class ActorKind(StrEnum):
    """What kind of principal caused an event."""

    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
