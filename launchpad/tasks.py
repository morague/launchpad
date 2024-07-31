from sanic import Sanic

from typing import Type

from launchpad.workers import LaunchpadWorker
from launchpad.watcher import LaunchpadWatcher


async def watcher_watch(app: Sanic):
    watcher: LaunchpadWatcher = app.ctx.watcher
    await watcher.poll(app)
