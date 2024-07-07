
from sanic import Sanic

from launchpad.temporal_server import TemporalServerManager
from launchpad.tasks import watcher_watch

async def start_watcher(app: Sanic):
    app.add_task(watcher_watch, name="watch")

async def on_start_deployments(app: Sanic):
    temporal: TemporalServerManager = app.ctx.temporal
    await temporal.on_server_start_deployment(app)