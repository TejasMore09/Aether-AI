"""Temporal workflows. Deterministic orchestration only — no I/O here.

One scheduled fire = one NanoMonitorWorkflow execution = one pass of the
decision loop. Temporal guarantees the run completes (with retries) or is
visibly failed; nothing depends on a process staying alive.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from aether.worker.activities import (
        DiagnoseInput,
        EvalInput,
        diagnose_approval,
        notify_approval,
        run_evaluation,
    )


@workflow.defn(name="NanoMonitorWorkflow")
class NanoMonitorWorkflow:
    @workflow.run
    async def run(self, payload: EvalInput) -> dict:
        result = await workflow.execute_activity(
            run_evaluation,
            payload,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=5,
            ),
        )

        # A gated decision gets a diagnosis attached. Best-effort: the
        # decision + approval already stand; a diagnosis failure must never
        # fail the monitor run (the service's fallback text makes genuine
        # failure here rare anyway).
        approval_id = result.get("approval_id")
        if approval_id:
            gated = DiagnoseInput(tenant_id=payload.tenant_id, approval_id=approval_id)
            try:
                result["diagnosis_source"] = await workflow.execute_activity(
                    diagnose_approval,
                    gated,
                    start_to_close_timeout=timedelta(seconds=90),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            except Exception:
                result["diagnosis_source"] = "failed"

            # Tell the tenant's owners a decision awaits them. Runs after
            # diagnosis so the email carries the explanation; idempotent per
            # recipient, and its failure never fails the monitor run.
            try:
                notified = await workflow.execute_activity(
                    notify_approval,
                    gated,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                result["notified"] = notified.get("notified", 0)
            except Exception:
                result["notified"] = 0

        return result
