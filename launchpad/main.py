from __future__ import annotations

import os
from sanic import Sanic
from sanic.log import LOGGING_CONFIG_DEFAULTS

from typing import Any

from launchpad.watcher import LaunchpadWatcher
from launchpad.authentication import Authenticator
from launchpad.temporal_server import TemporalServerManager
from launchpad.workers import WorkersManager
from launchpad.parsers import get_config

from launchpad.routes.tasks import tasksbp
from launchpad.routes.schedules import schedulesbp
from launchpad.routes.workers import workersbp
from launchpad.routes.watcher import watcherbp
from launchpad.routes.base import basebp
from launchpad.routes.login import loginbp

from launchpad.routes.errors_handler import error_handler
from launchpad.listeners import start_watcher
from launchpad.middlewares import go_fast, log_exit, cookie_token

"""
launchpad.runners, launchpad.activities, launchpad.workflows, launchpad.workers
are imported dynamically by the LaunchpadWatcher.
"""

Payload = dict[str,Any]
Sanic.START_METHOD_SET = True
Sanic.start_method = "fork"


BANNER = """\
    __                           __                    __
   / /   ____ ___  ______  _____/ /_  ____  ____ _____/ /
  / /   / __ `/ / / / __ \/ ___/ __ \/ __ \/ __ `/ __  / 
 / /___/ /_/ / /_/ / / / / /__/ / / / /_/ / /_/ / /_/ /  
/_____/\__,_/\__,_/_/ /_/\___/_/ /_/ .___/\__,_/\__,_/   
                                  /_/          v0.4.0               
"""

class Launchpad(object):    
    def __init__(
        self,
        *,
        env: str = "development",
        sanic: Payload | None = {},
        watcher: Payload | None = None,
        authenticator: Payload | None = None,
        temporalio: Payload | None = None,
        logging: Payload | None = None
        ) -> None:
        
        self.env = env
        self.print_banner()
        
        # -- SANIC
        self.configure_logging(logging)
        self.app = Sanic("Launchpad", log_config=logging)
        self.app.config.update({"ENV":env})
        self.app.config.update({k.upper():v for k,v in sanic.get("app", {}).items()})
        
        self.app.blueprint(basebp)
        self.app.blueprint(tasksbp)
        self.app.blueprint(schedulesbp)
        self.app.blueprint(workersbp)
        self.app.blueprint(watcherbp)
        self.app.blueprint(loginbp)
        
        self.app.error_handler.add(Exception, error_handler)
        self.app.on_request(go_fast, priority=100)
        self.app.on_request(cookie_token, priority=99)
        self.app.on_response(log_exit, priority=100)

        
        # -- WATCHER
        modules = watcher.get("modules", {})
        polling = watcher.get("polling", {})
        polling_interval = polling.get("polling_interval", None)
        automatic_refresh = polling.get("automatic_refresh", None)
        launchpad_watcher = LaunchpadWatcher.initialize(**modules)
        if polling_interval is not None:
            launchpad_watcher.set_polling_interval(polling_interval)
        if automatic_refresh is not None:
            launchpad_watcher.update_automatic_refresh(automatic_refresh)
        
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


        # -- AUTHENTICATOR
        if authenticator is not None:
            self.app.ctx.authenticator = Authenticator.initialize(**authenticator)
        else:
            self.app.ctx.authenticator = None
        
        # -- TEMPORAL IO SERVER
        if temporalio is None:
            self.app.ctx.temporal_server = None
            Warning("Make sure TemporalIO is running on another Process")
        else:
            pass # start server
        
        # -- TEMPORAL WORKERS
        if deployments_workers_settings is None:
            self.app.ctx.workers = WorkersManager()
            Warning("Make sure Some workers are running and binded to your workflows & activities")
        else:
            self.app.ctx.workers = WorkersManager.initialize(*[v for v in deployments_workers_settings.values()])
                
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
        