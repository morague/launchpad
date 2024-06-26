from __future__ import annotations
import sys
import time

from abc import ABC
import asyncio
import concurrent.futures
from multiprocessing import Process
from attrs import define, field
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from typing import Callable, Any

# from .workflows import Task
# from .activities import activities
# sys.modules[__name__].__dict__.update(**activities)

QueueName = str

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
        
        # workflows, activities = self.load()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as activity_executor:
            worker = Worker(
            client,
            task_queue=self.task_queue,
            workflows=self.workflows, 
            activities=self.activities,
            activity_executor=activity_executor,
            # workflow_runner=SandboxedWorkflowRunner(
            #     restrictions=SandboxRestrictions.default.with_passthrough_modules()
            # )
            )
            await worker.run()

    def run(self):
        asyncio.run(self._async_threadpool_workers())
    
    def load(self) -> tuple[list[Callable], list[Callable]]:
        workflows = list(filter(None, [getattr(sys.modules[__name__], k, None) for k in self.workflows]))
        activities = list(filter(None, [getattr(sys.modules[__name__], k, None) for k in self.activities]))
        return (workflows, activities)
        
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
            controler.add_worker(**settings)
        return controler
    
    @classmethod
    def as_main(cls, settings: dict[str, Any]= {}):
        worker = AsyncWorker(**settings)
        worker.run()
        
    def add_worker(self, **settings):
        print(settings)
        worker = AsyncWorker(**settings)
        process = Process(target= worker.run)
        process.start()
        self.__workers[worker.task_queue] = ((worker, process))
        
    def kill_worker(self, task_queue: QueueName):
        worker, process = self.__workers.get(task_queue, ((None, None)))
        if worker is None:
            raise KeyError()
        process.kill()
    
    def kill_all_workers(self) -> None:
        [process.kill() for _, process in self.__workers.values()]
        
        
    def ls_workers(self):
        return {
            worker.task_queue:{
                "worker":worker.__class__.__name__,
                "task_queue": worker.task_queue,
                "workflows": [f.__name__ for f in worker.workflows],
                "activities": [f.__name__ for f in worker.activities],
                "alive":process.is_alive(), 
                "pid":process.pid
            } 
            for worker, process in self.workers.values()
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
        


