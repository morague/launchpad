from __future__ import annotations

import os
from pathlib import Path
from sanic import Sanic
from sanic.log import LOGGING_CONFIG_DEFAULTS

from typing import Any, Optional

from launchpad.watcher import LaunchpadWatcher
from launchpad.authentication import Authenticator
from launchpad.temporal_server import TemporalServersManager
from launchpad.parsers import get_config

from launchpad.routes.tasks import tasksbp
from launchpad.routes.schedules import schedulesbp
from launchpad.routes.workers import workersbp
from launchpad.routes.watcher import watcherbp
from launchpad.routes.base import basebp
from launchpad.routes.login import loginbp

from launchpad.routes.errors_handler import error_handler
from launchpad.listeners import start_watcher, on_start_deploy_workers, on_start_deploy_tasks
from launchpad.middlewares import go_fast, log_exit, cookie_token

"""
launchpad.runners, launchpad.activities, launchpad.workflows, launchpad.workers
are imported dynamically by the LaunchpadWatcher.
"""
StrOrPath = str | Path
Payload = dict[str,Any]
Sanic.START_METHOD_SET = True
Sanic.start_method = "fork"


BANNER = """\
    __                           __                    __
   / /   ____ ___  ______  _____/ /_  ____  ____ _____/ /
  / /   / __ `/ / / / __ \/ ___/ __ \/ __ \/ __ `/ __  /
 / /___/ /_/ / /_/ / / / / /__/ / / / /_/ / /_/ / /_/ /
/_____/\__,_/\__,_/_/ /_/\___/_/ /_/ .___/\__,_/\__,_/
                                  /_/          v0.5.0
"""

class Launchpad(object):
    def __init__(
        self,
        *,
        env: str = "development",
        sanic: Payload | None = None,
        logging: Payload | None = None,
        **kwargs
        ) -> None:

        self.env = env
        self.print_banner()

        # -- SANIC
        if logging is None:
            logging = {"formatters": {},"handlers": {},"loggers": {}}
        if sanic is None:
            sanic = {}
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

    async def initialize_components(
        self,
        watcher: Payload | None = None,
        authenticator: Payload | None = None,
        temporalio: Payload | None = None,
        **kwargs
    ) -> None:
        # -- WATCHER
        if watcher is None:
            modules, polling = {}, {}
        else:
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
        objects = launchpad_watcher.temporal_objects()
        launchpad_watcher.inject("workflows", "runners", "workers", "temporal", objects=objects)

        if polling.get("on_server_start", False):
            self.app.register_listener(start_watcher, "after_server_start")


        # -- AUTHENTICATOR
        if authenticator is not None:
            self.app.ctx.authenticator = Authenticator.initialize(**authenticator)
        else:
            self.app.ctx.authenticator = None

        # -- TEMPORAL IO SERVER
        if temporalio is None:
            temporalio = {"servers": [{"name":"home", "ip":"localhost", "port": 7233, "gui_port": 8233}]}
        temporal_manager = await TemporalServersManager.intialize(
            **temporalio,
            tasks_settings=launchpad_watcher.tasks_settings(),
            workers_settings=launchpad_watcher.workers_settings(),
            activities=launchpad_watcher.activities(),
            workflows=launchpad_watcher.workflows(),
            runners=launchpad_watcher.runners(),
            workers= launchpad_watcher.workers()
        )
        self.app.ctx.temporal = temporal_manager
        self.app.register_listener(on_start_deploy_workers, "after_server_start", priority=100)
        self.app.register_listener(on_start_deploy_tasks, "after_server_start", priority=99)

    @classmethod
    async def create_app(cls, configs_path: Optional[StrOrPath] | None = None) -> Sanic:
        if configs_path is None:
            configs_path = os.environ.get("CONFIG_FILEPATH", "./launchpad_configs.yaml")
        if os.path.exists(configs_path):
            configs = get_config(configs_path)
        else:
            raise FileNotFoundError("configs file not found")
        launchpad = cls(**configs)
        await launchpad.initialize_components(**configs)
        return launchpad.app

    def configure_logging(self, logging: Payload) -> Payload:
        # base logging
        logging["formatters"].update(
            {
                "simple": {
                    "class": "logging.Formatter",
                    "format": "[%(asctime)s][%(name)s][%(process)d][%(levelname)s] | %(message)s",
                    "datefmt": "%d-%m-%Y %H:%M:%S"
                }
            })
        logging["handlers"].update(
            {
                "stream": {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                    "formatter": "simple",
                    "stream": "ext://sys.stdout"
                }
            })
        logging["loggers"].update({
            "endpointAccess": {"level": "INFO", "handlers": ["stream"], "propagate": False},
            "watcher": {"level": "INFO", "handlers": ["stream"], "propagate": False},
            "workflows": {"level": "INFO", "handlers": ["stream"], "propagate": False},
            "workers": {"level": "INFO", "handlers": ["stream"], "propagate": False},
            "temporal": {"level": "INFO", "handlers": ["stream"], "propagate": False}
        })

        # update with user specs
        logging["loggers"].update(LOGGING_CONFIG_DEFAULTS["loggers"])
        logging["handlers"].update(LOGGING_CONFIG_DEFAULTS["handlers"])
        logging["formatters"].update(LOGGING_CONFIG_DEFAULTS["formatters"])
        return logging

    def print_banner(self):
        print(BANNER)
        print(f"Booting {self.env} env")
