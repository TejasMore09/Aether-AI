"""Temporal Schedule management for Nano monitors.

One schedule per (tenant, domain): every interval, Temporal starts a
NanoMonitorWorkflow run. Overlap policy SKIP means a slow run is never piled
on by the next tick. Schedule ids are deterministic, so ensure() is idempotent.
"""

import uuid
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode

from aether.core.config import get_settings
from aether.worker.activities import EvalInput

_client: Client | None = None


async def get_client() -> Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    return _client


def schedule_id(tenant_id: uuid.UUID, domain: str) -> str:
    return f"nano-monitor-{tenant_id}-{domain}"


async def ensure_monitor_schedule(tenant_id: uuid.UUID, domain: str, interval_minutes: int) -> str:
    """Create or replace the monitor schedule for (tenant, domain)."""
    client = await get_client()
    sid = schedule_id(tenant_id, domain)
    settings = get_settings()

    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            "NanoMonitorWorkflow",
            EvalInput(tenant_id=str(tenant_id), domain=domain),
            id=f"{sid}-run",
            task_queue=settings.temporal_task_queue,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))]
        ),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )

    try:
        await client.create_schedule(sid, schedule)
    except RPCError as err:
        if err.status != RPCStatusCode.ALREADY_EXISTS:
            raise
        handle = client.get_schedule_handle(sid)

        def _replace(_: ScheduleUpdateInput) -> ScheduleUpdate:
            return ScheduleUpdate(schedule=schedule)

        await handle.update(_replace)
    return sid


async def run_monitor_now(tenant_id: uuid.UUID, domain: str, wait_seconds: float = 25.0) -> dict:
    """Run one full monitor cycle immediately, through the same workflow the
    schedule uses — so an on-demand run diagnoses and notifies exactly like an
    autonomous one. Waits briefly for the result; if the run outlives the wait
    it keeps going durably and we report it as still running.
    """
    import asyncio

    client = await get_client()
    settings = get_settings()
    handle = await client.start_workflow(
        "NanoMonitorWorkflow",
        EvalInput(tenant_id=str(tenant_id), domain=domain),
        id=f"nano-manual-{tenant_id}-{domain}-{uuid.uuid4().hex[:8]}",
        task_queue=settings.temporal_task_queue,
    )
    try:
        result = await asyncio.wait_for(handle.result(), timeout=wait_seconds)
    except TimeoutError:  # asyncio.TimeoutError is an alias since 3.11
        return {"status": "running", "workflow_id": handle.id}
    return {"status": "completed", "workflow_id": handle.id, "result": result}


async def delete_monitor_schedule(tenant_id: uuid.UUID, domain: str) -> bool:
    client = await get_client()
    try:
        await client.get_schedule_handle(schedule_id(tenant_id, domain)).delete()
        return True
    except RPCError as err:
        if err.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
