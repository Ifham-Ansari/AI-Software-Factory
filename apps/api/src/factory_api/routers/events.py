"""Workflow runs, event replay, job submission and the event WebSocket.

The replay endpoint and the socket are two halves of one contract. A client holds a
sequence cursor; it replays the gap over REST, then resumes the socket. Because the socket
is server-to-client only and every event carries a dense per-run ``seq``, a reconnecting
client can prove it missed nothing.

The socket carries **no commands**. Every client action is an authenticated, audited REST
call — one command path, one authorization point (architecture.md §10.2).
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, Query, WebSocket, status
from starlette.websockets import WebSocketDisconnect

from factory_api.dependencies import CurrentUserId, StateDep
from factory_api.dependencies.phase2 import (
    EventStoreDep,
    JobQueueDep,
    OwnedProjectId,
)
from factory_api.schemas.errors import ErrorResponse
from factory_api.schemas.events import (
    EnqueueJobRequest,
    EventPageResponse,
    EventResponse,
    JobResponse,
    RunResponse,
    WebSocketTicketResponse,
)
from factory_api.ws.manager import run_fanout
from factory_api.ws.tickets import TICKET_TTL_SECONDS
from factory_core.domain.ids import RunId, new_run_id, parse_uuid
from factory_core.errors import NotFoundError
from factory_core.events import create_run
from factory_core.events.store import MAX_REPLAY_LIMIT
from factory_core.infrastructure.queue.schemas import JobRequest, JobStatus
from factory_core.observability import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["events"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Create a workflow run",
)
async def create_workflow_run(project_id: OwnedProjectId, store: EventStoreDep) -> RunResponse:
    """Create a run to carry events and jobs.

    Phase 3's graph will own run creation. It is exposed now because events and jobs
    both hang off a run, and the realtime pipeline has to be demonstrable before any
    agent exists to drive it.
    """
    run_id = new_run_id()
    await create_run(store.session, project_id=project_id, run_id=run_id)
    return RunResponse(
        id=run_id,
        project_id=project_id,
        status="pending",
        last_seq=0,
        created_at=await store.created_at(run_id),
    )


@router.get(
    "/runs/{run_id}/events",
    response_model=EventPageResponse,
    responses=_ERRORS,
    summary="Replay a run's events from a sequence cursor",
)
async def replay_events(
    run_id: str,
    store: EventStoreDep,
    actor_id: CurrentUserId,
    after_seq: int = Query(
        default=0, ge=0, description="Return events with seq greater than this."
    ),
    limit: int = Query(default=100, ge=1, le=MAX_REPLAY_LIMIT),
) -> EventPageResponse:
    """Return the events a client has not seen.

    This is what makes a dropped socket lossless: the client sends the last ``seq`` it
    processed and receives exactly the gap, in order, once.

    Raises:
        NotFoundError: The run does not exist, or belongs to another user's project.
    """
    resolved = await _owned_run(run_id, store, actor_id)
    events = await store.read_after(resolved, after_seq=after_seq, limit=limit)
    latest = await store.latest_seq(resolved)
    next_seq = events[-1].seq if events else after_seq
    return EventPageResponse(
        items=[EventResponse.from_envelope(event) for event in events],
        next_seq=next_seq,
        has_more=next_seq < latest,
        latest_seq=latest,
    )


@router.post(
    "/runs/{run_id}/ws-ticket",
    response_model=WebSocketTicketResponse,
    responses=_ERRORS,
    summary="Mint a single-use ticket for the event socket",
)
async def create_ws_ticket(
    run_id: str, store: EventStoreDep, state: StateDep, actor_id: CurrentUserId
) -> WebSocketTicketResponse:
    """Issue a short-lived ticket authorising one socket connection.

    A ticket rather than a cookie (CSRF-prone on WebSocket) or a query-string bearer
    token (which lands in access logs). See ``ws/tickets.py``.
    """
    resolved = await _owned_run(run_id, store, actor_id)
    project_id = await store.project_for(resolved)
    ticket = state.tickets.issue(user_id=actor_id, project_id=project_id)
    return WebSocketTicketResponse(
        ticket=ticket.value,
        expires_in=TICKET_TTL_SECONDS,
        socket_path=f"/ws/runs/{resolved}",
    )


@router.post(
    "/runs/{run_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Enqueue background work against a run",
)
async def enqueue_job(
    run_id: str,
    body: EnqueueJobRequest,
    store: EventStoreDep,
    queue: JobQueueDep,
    actor_id: CurrentUserId,
) -> JobResponse:
    """Submit a job.

    Enqueued in the request's own transaction, so the job and the state that justifies it
    commit together — there is no window where a worker could claim a job referring to
    something that was rolled back.
    """
    resolved = await _owned_run(run_id, store, actor_id)
    project_id = await store.project_for(resolved)
    job_id = await queue.enqueue(
        JobRequest(
            type=body.type,
            payload={"steps": body.steps},
            project_id=project_id,
            run_id=resolved,
            idempotency_key=body.idempotency_key,
        )
    )
    return JobResponse(
        id=job_id, run_id=resolved, type=body.type, status=JobStatus.PENDING, attempts=0
    )


@router.websocket("/ws/runs/{run_id}")
async def run_events_socket(websocket: WebSocket, run_id: str, ticket: str = Query()) -> None:
    """Stream a run's events to an authorised client.

    Server-to-client only. The ticket is redeemed once, before the socket is accepted, so
    an unauthorised handshake never reaches the accepted state.
    """
    state = websocket.app.state.app_state
    parsed = parse_uuid(run_id)
    redeemed = state.tickets.redeem(ticket)

    if parsed is None or redeemed is None:
        # 1008 (policy violation) for every rejection: an unauthorised caller learns
        # nothing about whether the run exists or the ticket merely expired.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    resolved = RunId(parsed)
    await websocket.accept()
    await state.connections.register(resolved, websocket)
    fanout = asyncio.create_task(run_fanout(state.connections, state.event_bus, resolved))
    try:
        # The client sends nothing meaningful; this receive loop exists to observe the
        # disconnect. Anything it does send is discarded — commands go over REST.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Socket torn down underneath us during shutdown. Normal, not an error.
        pass
    finally:
        fanout.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await fanout
        await state.connections.unregister(resolved, websocket)


async def _owned_run(run_id: str, store: EventStoreDep, actor_id: CurrentUserId) -> RunId:
    """Resolve a run id, proving the caller's user owns its project.

    Raises:
        NotFoundError: Malformed id, unknown run, or a run under another user's project.
            All three report 404 so this cannot be used to discover run ids.
    """
    parsed = parse_uuid(run_id)
    if parsed is None:
        raise NotFoundError("The requested run was not found.")
    resolved = RunId(parsed)
    if not await store.is_owned_by(resolved, owner_id=actor_id):
        raise NotFoundError("The requested run was not found.")
    return resolved
