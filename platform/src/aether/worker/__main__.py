"""Nano worker process: executes monitor workflows from the task queue.

Run:  python -m aether.worker
Activities are synchronous DB code, so they run on a thread pool; workflow
orchestration stays on the event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from aether.core.config import get_settings
from aether.worker.activities import diagnose_approval, notify_approval, run_evaluation
from aether.worker.workflows import NanoMonitorWorkflow

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("aether.worker")


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(
        settings.temporal_address, namespace=settings.temporal_namespace
    )
    logger.info(
        "Nano worker connected to Temporal at %s (queue=%s)",
        settings.temporal_address,
        settings.temporal_task_queue,
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[NanoMonitorWorkflow],
            activities=[run_evaluation, diagnose_approval, notify_approval],
            activity_executor=executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
