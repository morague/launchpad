from __future__ import annotations

import os
from sanic import Sanic
from sanic.log import LOGGING_CONFIG_DEFAULTS

from typing import Optional, Any

from launchpad.watcher import LaunchpadWatcher
from launchpad.temporal_server import TemporalServerManager
from launchpad.workers import WorkersManager
from launchpad.parsers import get_config

from launchpad.routes.deployments import deployments
from launchpad.routes.schedules import schedules
from launchpad.routes.workers import workersbp

"""
launchpad.runners, launchpad.activities, launchpad.workflows, launchpad.workers
are imported dynamically by the LaunchpadWatcher.
"""

Payload = dict[str,Any]

BANNER = """\
    __                           __                    __
   / /   ____ ___  ______  _____/ /_  ____  ____ _____/ /
  / /   / __ `/ / / / __ \/ ___/ __ \/ __ \/ __ `/ __  / 
 / /___/ /_/ / /_/ / / / / /__/ / / / /_/ / /_/ / /_/ /  
/_____/\__,_/\__,_/_/ /_/\___/_/ /_/ .___/\__,_/\__,_/   
                                  /_/          v0.2.0               
"""

class Launchpad(object):    
    def __init__(
        self,
        *,
        env: str = "development",
        sanic: Payload | None = {},
        modules: Payload | None = None,
        temporalio: Payload | None = None,
        logging: Payload | None = None
        ) -> None:
        
        self.env = env
        self.print_banner()
        
        self.configure_logging(logging)
        self.app = Sanic("Launchpad", log_config=logging)
        self.app.config.update({"ENV":env})
        self.app.config.update({k.upper():v for k,v in sanic.get("app", {})})
        
        self.app.blueprint(deployments)
        self.app.blueprint(schedules)
        self.app.blueprint(workersbp)
        
        watcher = self.initialize_watcher(modules)
        watcher._initialize_temporal_objects(__name__)
        self.app.ctx.watcher = watcher
        self.app.ctx.activities = watcher.activities()
        self.app.ctx.workflows = watcher.workflows()
        self.app.ctx.runners = watcher.runners()
        self.app.ctx.temporal_workers = watcher.temporal_workers()
        self.app.ctx.deployments = watcher.deployments()
        workers = watcher.workers()
        objects = watcher.temporal_objects()
        watcher.inject("workflows", "runners", "workers", objects=objects)

        if temporalio is None:
            self.app.ctx.temporal_server = None
            Warning("Make sure TemporalIO is running on another Process")
        else:
            pass # start server
        
        if workers is None:
            self.app.ctx.workers = None
            Warning("Make sure Some workers are running and binded to your workflows & activities")
        else:
            # prepare workers
            workers = self.prepare_workers(watcher)
            print(workers)
            self.app.ctx.workers = WorkersManager.initialize(*workers)
            
        # print(self.app.ctx.workers.ls_workers())
        # self.app.ctx.workers.kill_all_workers()
        
        
                
    @classmethod
    def create_app(cls) -> Launchpad:
        configs = get_config(os.environ.get("CONFIG_FILEPATH", "./configs/configs.yaml"))
        return cls(**configs)
    
    def configure_logging(self, logging: Payload) -> Payload:
        logging["loggers"].update(LOGGING_CONFIG_DEFAULTS["loggers"])
        logging["handlers"].update(LOGGING_CONFIG_DEFAULTS["handlers"])
        logging["formatters"].update(LOGGING_CONFIG_DEFAULTS["formatters"])  
        return logging
    
    def initialize_watcher(self, modules: Payload) -> LaunchpadWatcher:
        base_modules = {
            "configs": [os.environ.get('CONFIG_FILEPATH', "./configs/configs.yaml")],
            "workflows": ["./launchpad/workflows.py"],
            "workers": ["./launchpad/workers.py"],
            "runners": ["./launchpad/runners.py"],
            "routes": ["./launchpad/routes"]
        }
        for k,v in modules.items():
            if k not in base_modules.keys():
                base_modules[k] = v
            else:
                base_modules[k].extend(v)
        
        return LaunchpadWatcher(**base_modules)
    
    def prepare_workers(self, watcher: LaunchpadWatcher) -> Payload:
        workers = watcher.workers()
        for worker in workers:
            worker.pop("type")
            worker["activities"] = [v for k,v in watcher.activities().items() if k in worker["activities"]]
            worker["workflows"] = [v for k,v in watcher.workflows().items() if k in worker["workflows"]]
        return workers
    
    def print_banner(self):
        print(BANNER)
        print(f"Booting {self.env} env")
        