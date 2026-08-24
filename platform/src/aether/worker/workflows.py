"""Temporal workflows. Deterministic orchestration only — no I/O here.

One scheduled fire = one NanoMonitorWorkflow execution = one pass of the
decision loop. Temporal guarantees the run completes (with retries) or is
visibly failed; nothing depends on a process staying alive.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from aether.worker.activities import EvalInput, run_evaluation


@workflow.defn(name="NanoMonitorWorkflow")
class NanoMonitorWorkflow:
    @workflow.run
    async def run(self, payload: EvalInput) -> dict:
        return await workflow.execute_activity(
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
