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
from launchpad.routes.watcher import watcherbp

from launchpad.listeners import start_watcher

"""
launchpad.runners, launchpad.activities, launchpad.workflows, launchpad.workers
are imported dynamically by the LaunchpadWatcher.
"""
import sys
Payload = dict[str,Any]
Sanic.START_METHOD_SET = True
Sanic.start_method = "fork"


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
        watcher: Payload | None = None,
        temporalio: Payload | None = None,
        logging: Payload | None = None
        ) -> None:
        
        self.env = env
        self.print_banner()
        
        # -- SANIC
        self.configure_logging(logging)
        self.app = Sanic("Launchpad", log_config=logging)
        self.app.config.update({"ENV":env})
        self.app.config.update({k.upper():v for k,v in sanic.get("app", {})})
        
        self.app.blueprint(deployments)
        self.app.blueprint(schedules)
        self.app.blueprint(workersbp)
        self.app.blueprint(watcherbp)
        
        # -- WATCHER
        modules = watcher.get("modules", {})
        polling = watcher.get("polling", {})
        polling_interval = polling.get("polling_interval", None)
        launchpad_watcher = LaunchpadWatcher.initialize(**modules) #self.initialize_watcher(modules)
        if polling_interval is not None:
            launchpad_watcher.set_polling_interval(polling_interval)
        
        launchpad_watcher._initialize_temporal_objects(__name__)
        self.app.ctx.watcher = launchpad_watcher
        self.app.ctx.activities = launchpad_watcher.activities()
        self.app.ctx.workflows = launchpad_watcher.workflows()
        self.app.ctx.runners = launchpad_watcher.runners()
        self.app.ctx.temporal_workers = launchpad_watcher.temporal_workers()
        
        
        deployments_settings = launchpad_watcher.deployments()
        deployments_workers_settings = launchpad_watcher.deployments_workers()
        self.app.ctx.deployments = deployments_settings
        self.app.ctx.deployments_workers = deployments_workers_settings
        
        objects = launchpad_watcher.temporal_objects()
        launchpad_watcher.inject("workflows", "runners", "workers", objects=objects)
        
        if polling.get("on_server_start", False):
            self.app.register_listener(start_watcher, "after_server_start")

        # -- TEMPORAL IO SERVER
        if temporalio is None:
            self.app.ctx.temporal_server = None
            Warning("Make sure TemporalIO is running on another Process")
        else:
            pass # start server
        
        # -- TEMPORAL WORKERS
        if deployments_workers_settings is None:
            self.app.ctx.workers = None
            Warning("Make sure Some workers are running and binded to your workflows & activities")
        else:
            self.app.ctx.workers = WorkersManager.initialize(*deployments_workers_settings)
                
    @classmethod
    def create_app(cls) -> Launchpad:
        configs = get_config(os.environ.get("CONFIG_FILEPATH", "./configs/configs.yaml"))
        return cls(**configs)
    
    def configure_logging(self, logging: Payload) -> Payload:
        logging["loggers"].update(LOGGING_CONFIG_DEFAULTS["loggers"])
        logging["handlers"].update(LOGGING_CONFIG_DEFAULTS["handlers"])
        logging["formatters"].update(LOGGING_CONFIG_DEFAULTS["formatters"])  
        return logging
    
    def print_banner(self):
        print(BANNER)
        print(f"Booting {self.env} env")
        