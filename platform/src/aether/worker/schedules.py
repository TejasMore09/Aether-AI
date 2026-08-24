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


async def ensure_monitor_schedule(
    tenant_id: uuid.UUID, domain: str, interval_minutes: int
) -> str:
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


async def delete_monitor_schedule(tenant_id: uuid.UUID, domain: str) -> bool:
    client = await get_client()
    try:
        await client.get_schedule_handle(schedule_id(tenant_id, domain)).delete()
        return True
    except RPCError as err:
        if err.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
