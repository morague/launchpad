from __future__ import annotations
import os
import subprocess
import signal
import copy
from sanic import Sanic
from multiprocessing import Process
from attrs import define, field

from typing import Any

@define(slots=True)
class TemporalServerManager:
    __server: Process | None = field(default=None)
    
    @property
    def server(self):
        return self.__server
    
    @classmethod
    def run(cls, args: list[str] = []) -> TemporalServerManager:
        server = cls()
        server.__server = Process(target=server.start_server, args=args)
        server.__server.start()
        return server
    
    @classmethod
    def simple_manager(cls) -> TemporalServerManager:
        manager = cls()
        manager.__server = None
        return manager
        
    def start_server(self, args: list[str] = []) -> None:
        subprocess.run(" ".join(["temporal", "server", "start-dev"] + args), shell = True, executable="/bin/bash", preexec_fn=os.setsid)
    
    def kill_server(self) -> None:
        # os.kill(self.server.pid, signal.SIGINT) # kill parent process as well :c
        self.__server.kill()
    
    async def deploy(self, app: Sanic, task_name: str) -> None:
        deployment = copy.deepcopy(app.ctx.deployments.get(task_name, None))
        if deployment is None:
            raise KeyError()

        runner_name = deployment.get("runner", None)
        runner_class = app.ctx.runners.get(runner_name, None)
        
        if runner_name is None or runner_class is None:
            raise KeyError()

        workflow_payload = deployment.get("workflow")
        workflow_name = workflow_payload.get("workflow", None)
        workflow_class = app.ctx.workflows.get(workflow_name, None)
        if workflow_name is None or workflow_class is None:
            raise KeyError()
        else:
            workflow_payload["workflow"] = workflow_class
        await runner_class()(**workflow_payload)
        
    async def on_server_start_deployment(self, app: Sanic) -> None:
        deployments_settings = app.ctx.deployments
        for task_name, settings in deployments_settings.items():
            deployable = settings.get("deploy_on_server_start", False)
            if deployable:
                await self.deploy(app, task_name)