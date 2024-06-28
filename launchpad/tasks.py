import time
import asyncio
from sanic import Sanic

from launchpad.watcher import LaunchpadWatcher
from launchpad.utils import aggregate

async def watcher_watch(app: Sanic):
    watcher: LaunchpadWatcher = app.ctx.watcher
    
    # raises
    
    await watcher.poll(app)
        