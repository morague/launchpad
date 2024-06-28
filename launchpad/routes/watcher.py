

from sanic import Blueprint
from sanic import Request
from sanic.response import json

from launchpad.tasks import watcher_watch
from launchpad.watcher import LaunchpadWatcher
from launchpad.utils import query_kwargs

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
    if request.app.get_task("watch", raise_exception=False) is not None:
        alive = True 
    data = {"alive": alive, "polling_interval": watcher.polling_interval}    
    return json({"status":200, "reasons": "OK", "data": data}, status=200)
    
@watcherbp.get("/polling/stop")
async def stop_polling(request: Request):
    await request.app.cancel_task("watch")
    request.app.purge_tasks()
    return json({"status":200, "reasons": "OK"}, status=200)

@watcherbp.get("/polling/start")
async def start_polling(request: Request):
    
    query = query_kwargs(request.query_args)
    polling_interval = query.get("polling_interval", None)
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    if polling_interval is not None:
        watcher.set_polling_interval(polling_interval)
    
    if request.app.get_task("watch", raise_exception=False) is not None:
        raise ValueError("watcher polling alreay running")
    
    request.app.add_task(watcher_watch, name="watch")
    data = {"alive": True, "polling_interval": watcher.polling_interval}
    return json({"status":200, "reasons": "OK", "data": data}, status=200)

@watcherbp.get("/polling/interval/<polling_interval:int>")
async def update_polling_interval(request: Request, polling_interval: int):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.set_polling_interval(polling_interval)
    alive = False
    if request.app.get_task("watch", raise_exception=False) is not None:
        alive = True 
    data = {"alive": alive, "polling_interval": watcher.polling_interval}
    return json({"status":200, "reasons": "OK", "data": data}, status=200)
    
@watcherbp.get("/visit")
async def visit_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = watcher.visit()
    return json({"status":200, "reasons": "OK", "data": changes}, status=200)

@watcherbp.get("/visit/<group:str>")
async def visit_group(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = watcher.visit(group)
    return json({"status":200, "reasons": "OK", "data": changes}, status=200)

@watcherbp.get("refresh")
async def refresh_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.visit()
    watcher.update_app(request.app)
    return json({"status":200, "reasons": "OK", "data": {}}, status=200)


