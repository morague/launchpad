from __future__ import annotations
import sys
import time
import logging
from abc import ABC
import asyncio
import concurrent.futures
from functools import wraps
from multiprocessing import Process

from attrs import define, field, Factory

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from typing import Callable, Any, Coroutine, Type


QueueName = str

logger = logging.getLogger("workers")

def log(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*args, **kwargs) -> Any:
        logger.info(f"[{f.__name__}][args: {args}][kwargs: {kwargs}]")
        return f(*args, **kwargs)
    return wrapper



class LaunchpadWorker(ABC):
    client: Client
    task_queue: str
    max_workers: int
    workflows: list[Type]
    activities: list[Type]

    async def run(self) -> None:
        ...


@define(frozen=True, slots=False)
class AsyncWorker(LaunchpadWorker):
    client: Client = field()
    task_queue: str = field(default="default")
    workflows: list[Type] = field(default=Factory(list))
    activities: list[Type] = field(default=Factory(list))
    max_workers: int = field(default=100)

    async def _async_threadpool_workers(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as activity_executor:
            worker = Worker(
            self.client,
            task_queue=self.task_queue,
            workflows=self.workflows,
            activities=self.activities,
            activity_executor=activity_executor,
            )
            await worker.run()

    async def run(self) -> None:
        await self._async_threadpool_workers()
