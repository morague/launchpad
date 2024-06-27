

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, text

from launchpad.watcher import LaunchpadWatcher
from launchpad.utils import is_activity, is_workflow, is_runner, is_temporal_worker

watcherbp = Blueprint("watcherbp", url_prefix="/watcher")

@watcherbp.get("/modules")
async def modules(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    references = {k:[m.as_json() for m in v.modules.values()] for k,v in watcher.groups.items()}
    return json(references, status=200)

@watcherbp.get("/modules/<group:str>")
async def group_modules(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    references = {group:[m.as_json() for m in watcher.get(group).modules.values()]}
    return json(references, status=200)

@watcherbp.get("/polling")
async def get_pooler(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    return json({
        "watcher": watcher.watcher.pid,
        "alive": watcher.watcher.is_alive(),
        "pooling_interval": watcher.polling_interval
    }, status=200)
    
@watcherbp.get("/polling/stop")
async def stop_polling(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.kill_watcher()
    return json({"alive":False}, status=200)

@watcherbp.get("/polling/start")
async def start_polling(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.watch() # add params for pooling interval
    return json({
        "watcher": watcher.watcher.pid,
        "alive": watcher.watcher.is_alive(),
        "pooling_interval": watcher.polling_interval
    }, status=200)

@watcherbp.get("/visit")
async def visit_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = watcher.visit()
    return json(changes, status=200)


@watcherbp.get("/visit/<group:str>")
async def visit_group(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = watcher.visit(group)
    return json(changes, status=200)

    
    
@watcherbp.get("refresh")
async def refresh_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.visit()
    
    request.app.ctx.activities = watcher.activities()
    request.app.ctx.workflows = watcher.workflows()
    request.app.ctx.runners = watcher.runners()
    request.app.ctx.temporal_workers = watcher.temporal_workers()
    request.app.ctx.deployments = watcher.deployments()
    
    objects = watcher.temporal_objects()
    watcher.inject("workflows", "runners", "workers", objects=objects)
    return text("Done")
