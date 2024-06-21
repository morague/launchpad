from __future__ import annotations

import sys
import os
from yaml import load, SafeLoader

from sanic import Sanic
from sanic.log import LOGGING_CONFIG_DEFAULTS

from typing import Optional, Any

from launchpad.temporal_server import TemporalServerManager
from launchpad.workers import WorkersManager
from launchpad.parsers import get_config

from launchpad.utils import is_activity, is_workflow


from launchpad.routes.deployments import deployments
from launchpad.routes.schedules import schedules
from launchpad.routes.workers import workersbp

from launchpad.workflows import *
from launchpad.runners import *
# from launchpad.activities import *
from launchpad.activities import activities
sys.modules[__name__].__dict__.update(**activities)


Payload = dict[str,Any]

BANNER = """\
    __                           __                    __
   / /   ____ ___  ______  _____/ /_  ____  ____ _____/ /
  / /   / __ `/ / / / __ \/ ___/ __ \/ __ \/ __ `/ __  / 
 / /___/ /_/ / /_/ / / / / /__/ / / / /_/ / /_/ / /_/ /  
/_____/\__,_/\__,_/_/ /_/\___/_/ /_/ .___/\__,_/\__,_/   
                                  /_/          v0.1.0               
"""

class Launchpad(object):    
    def __init__(
        self,
        *,
        env: str = "development",
        sanic: Payload | None = {},
        modules: Payload | None = None,
        temporalio: Payload | None = None,
        workers: Payload | None = None,
        logging: Payload | None = None
        ) -> None:
        
        self.env = env
        self.print_banner()
        
        logging["loggers"].update(LOGGING_CONFIG_DEFAULTS["loggers"])
        logging["handlers"].update(LOGGING_CONFIG_DEFAULTS["handlers"])
        logging["formatters"].update(LOGGING_CONFIG_DEFAULTS["formatters"])        

        self.app = Sanic("Launchpad", log_config=logging)
        self.app.config.update({"ENV":env})
        self.app.config.update({k.upper():v for k,v in sanic.get("app", {})})
        
        
        
        # registering 
        self.app.ctx.workflows = {k:v for k,v in sys.modules[__name__].__dict__.items() if is_workflow(v)}
        self.app.ctx.activities = {k:v for k,v in sys.modules[__name__].__dict__.items() if is_activity(v)}
        self.app.ctx.runners = {k:v for k,v in sys.modules[__name__].__dict__.items() if type(v).__name__ == "ABCMeta" and v.__bases__[0].__name__ == "Runner"}
        
        d = {}
        path = "./deployments"
        for file in os.listdir(path):
            with open(f"{path}/{file}", "r") as f:
                dep = load(f, SafeLoader)
                d.update({dep["name"]:dep})
        self.app.ctx.deployments = d
        
        
        self.app.blueprint(deployments)
        self.app.blueprint(schedules)
        self.app.blueprint(workersbp)
        
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
            for worker in workers:
                worker.pop("type")
                worker["activities"] = [sys.modules[__name__].__dict__.get(n) for n in worker["activities"]] 
                worker["workflows"] = [sys.modules[__name__].__dict__.get(n) for n in worker["workflows"]]
            self.app.ctx.workers = WorkersManager.initialize(*workers)
            
        print(self.app.ctx.workers.ls_workers())
        # self.app.ctx.workers.kill_all_workers()
        
        
                
    @classmethod
    def create_app(cls) -> Launchpad:
        configs = get_config(os.environ.get("CONFIG_FILEPATH", "./configs/configs.yaml"))
        return cls(**configs)
    
    def register_activities():
        pass
    
    def register_workflows():
        pass
    
    def register_runners():
        pass
    
    def register_deploiements():
        pass
    
    
        
    def print_banner(self):
        print(BANNER)
        print(f"Booting {self.env} env")
        