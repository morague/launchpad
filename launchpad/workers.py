from __future__ import annotations
import sys
import time
import logging
from abc import ABC
import asyncio
import concurrent.futures
from functools import wraps
from multiprocessing import Process
from attrs import define, field
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from typing import Callable, Any


QueueName = str

logger = logging.getLogger("workers")

def log(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*args, **kwargs) -> Any:
        logger.info(f"[{f.__name__}][args: {args}][kwargs: {kwargs}]")
        return f(*args, **kwargs)
    return wrapper
    

class LaunchpadWorker(ABC):
    def run(self):
        ...


@define(frozen=True, slots=False)
class AsyncWorker(LaunchpadWorker):
    client_address: str = field(default="localhost:7233")
    task_queue: str = field(default="default")
    workflows: list[Callable] = field(default=[])
    activities: list[Callable] = field(default=[])
    max_workers: int = field(default=100)
    
    async def _async_threadpool_workers(self):
        client = await Client.connect(self.client_address)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as activity_executor:
            worker = Worker(
            client,
            task_queue=self.task_queue,
            workflows=self.workflows, 
            activities=self.activities,
            activity_executor=activity_executor,
            )
            await worker.run()

    def run(self):
        asyncio.run(self._async_threadpool_workers())
    
        
@define(slots=True)
class WorkersManager:
    __workers: dict[QueueName, tuple[AsyncWorker, Process]] = field(default={})

    @property
    def workers(self):
        return self.__workers    
        
    @classmethod
    def initialize(cls, *workers_settings) -> WorkersManager:
        controler = cls()
        for settings in workers_settings:
            if settings.get("deploy_on_server_start", False):
                controler.add_worker(**settings)
        return controler
    
    @classmethod
    def as_main(cls, settings: dict[str, Any]= {}):
        worker = AsyncWorker(**settings)
        worker.run()
    
    @log
    def add_worker(self, **settings):
        worker_settings = settings.get("worker", None)
        worker = self._build_worker(worker_settings)
        process = Process(target= worker.run)
        process.start()
        self.__workers[worker.task_queue] = ((worker, process))
        return (worker, process)
    
    @log
    def kill_worker(self, task_queue: QueueName):
        worker, process = self.__workers.get(task_queue, ((None, None)))
        if worker is None:
            raise KeyError()
        process.kill()
    
    def kill_all_workers(self) -> None:
        [process.kill() for _, process in self.__workers.values()]

    def ls_workers(self):
        return {k:self.worker_infos(k) for k in self.workers.keys()}
    
    def worker_infos(self, task_queue: str) -> dict[str, Any]:
        worker, process = self.workers.get(task_queue, ((None, None)))
        if worker is None:
            raise ValueError("worker does not exist")
        
        return {
            "worker":worker.__class__.__name__,
            "task_queue": worker.task_queue,
            "workflows": [f.__name__ for f in worker.workflows],
            "activities": [f.__name__ for f in worker.activities],
            "alive":process.is_alive(), 
            "pid":process.pid
        }
    
    def restart_worker(self, task_queue: QueueName):
        worker, process = self.workers.get(task_queue, ((None,None)))
        if worker is None:
            raise KeyError()
        
        if process.is_alive():
            process.kill()
            
        process = Process(target= worker.run)
        process.start()
        self.__workers[worker.task_queue] = ((worker, process))
        
    def _build_worker(self, settings: dict[str, Any]) -> LaunchpadWorker:
        module = sys.modules[__name__]
        worker_type = settings.pop("type", None)
        
        if worker_type is None:
            raise ValueError("worker not existing")

        workerclass: LaunchpadWorker = getattr(module, worker_type)
        activities = [getattr(module, k, None) for k in settings["activities"]]
        workflows = [getattr(module, k, None) for k in settings["workflows"]]
        if not all(activities + workflows):
            raise ValueError("activities or workflows not imported in workers module")
        
        settings["activities"] = activities
        settings["workflows"] = workflows
        
        return workerclass(**settings)