
from sanic import Sanic

from launchpad.tasks import watcher_watch

async def start_watcher(app: Sanic):
    app.add_task(watcher_watch, name="watch")
