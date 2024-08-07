
from sanic import Sanic

from launchpad.temporal.temporal_server import TemporalServersManager
from launchpad.tasks import watcher_watch

async def start_watcher(app: Sanic):
    app.add_task(watcher_watch, name="watch") # type: ignore

async def on_start_deploy_tasks(app: Sanic):
    temporal: TemporalServersManager = app.ctx.temporal
    await temporal.on_server_start_deploy_tasks(app)

async def on_start_deploy_workers(app: Sanic):
    temporal: TemporalServersManager = app.ctx.temporal
    await temporal.on_server_start_deploy_workers(app)
