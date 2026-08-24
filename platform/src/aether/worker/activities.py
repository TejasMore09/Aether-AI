"""Temporal activities: the non-deterministic edges of the monitor loop.

Activities may touch the database and the network; workflows may not. All
business logic stays in aether.services.evaluation — an activity is a thin,
retryable shell around it.
"""

import uuid
from dataclasses import dataclass

from temporalio import activity

from aether.services.evaluation import evaluate_domain


@dataclass
class EvalInput:
    tenant_id: str  # UUID as string — Temporal payloads stay JSON-simple
    domain: str


@activity.defn(name="run_evaluation")
def run_evaluation(payload: EvalInput) -> dict:
    outcome = evaluate_domain(
        tenant_id=uuid.UUID(payload.tenant_id),
        domain=payload.domain,
        triggered_by=f"nano-monitor:{payload.domain}",
    )
    result = outcome.as_dict()
    activity.logger.info(
        "nano-monitor evaluated tenant=%s domain=%s status=%s action=%s",
        payload.tenant_id,
        payload.domain,
        result.get("status"),
        result.get("action", "-"),
    )
    return result
