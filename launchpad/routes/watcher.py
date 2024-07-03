

from sanic import Blueprint
from sanic import Request
from sanic.response import json

from launchpad.tasks import watcher_watch
from launchpad.watcher import LaunchpadWatcher
from launchpad.utils import query_kwargs

from launchpad.authentication import protected

watcherbp = Blueprint("watcherbp", url_prefix="/watcher")

@watcherbp.get("/modules")
@protected("user")
async def modules(request: Request):
    args = {k:True for k,_ in request.get_query_args(keep_blank_values=True)}
    changed = args.get("changed", False)
    unchanged = args.get("unchanged", False)
    if changed and unchanged:
        changed, unchanged = False, False
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    if not any([changed, unchanged]):    
        references = {k:[m.as_json() for m in v.modules.values()] for k,v in watcher.groups.items()}    
    elif changed:
        references = {k:[m.as_json() for m in v.modules.values() if m.changes] for k,v in watcher.groups.items()}
    elif unchanged:
        references = {k:[m.as_json() for m in v.modules.values() if m.changes is False] for k,v in watcher.groups.items()}
    return json({"status":200, "reasons": "OK", "data": references}, status=200)

@watcherbp.get("/modules/<group:str>")
@protected("user")
async def group_modules(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    references = {group:[m.as_json() for m in watcher.get(group).modules.values()]}
    return json({"status":200, "reasons": "OK", "data": references}, status=200)

@watcherbp.get("/polling")
@protected("user")
async def get_pooler(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    if request.app.get_task("watch", raise_exception=False) is not None:
        alive = True 
    data = {"alive": alive, "polling_interval": watcher.polling_interval, "automatic_refresh": watcher.automatic_refresh}    
    return json({"status":200, "reasons": "OK", "data": data}, status=200)
    
@watcherbp.get("/polling/stop")
@protected("user")
async def stop_polling(request: Request):
    await request.app.cancel_task("watch")
    request.app.purge_tasks()
    return json({"status":200, "reasons": "OK"}, status=200)

@watcherbp.get("/polling/start")
@protected("user")
async def start_polling(request: Request):
    
    query = query_kwargs(request.query_args)
    polling_interval = query.get("polling_interval", None)
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    if polling_interval is not None:
        watcher.set_polling_interval(polling_interval)
    
    if request.app.get_task("watch", raise_exception=False) is not None:
        raise ValueError("watcher polling alreay running")
    
    request.app.add_task(watcher_watch, name="watch")
    data = {"alive": True, "polling_interval": watcher.polling_interval, "automatic_refresh": watcher.automatic_refresh}
    return json({"status":200, "reasons": "OK", "data": data}, status=200)

@watcherbp.get("/polling/interval/<polling_interval:int>")
@protected("user")
async def update_polling_interval(request: Request, polling_interval: int):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.set_polling_interval(polling_interval)
    alive = False
    if request.app.get_task("watch", raise_exception=False) is not None:
        alive = True 
    data = {"alive": alive, "polling_interval": watcher.polling_interval, "automatic_refresh": watcher.automatic_refresh}
    return json({"status":200, "reasons": "OK", "data": data}, status=200)

@watcherbp.get("/polling/toggle/refresh")
@protected("user")
async def toggle_refresh(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.update_automatic_refresh(not watcher.automatic_refresh)
    alive = False
    if request.app.get_task("watch", raise_exception=False) is not None:
        alive = True 
    data = {"alive": alive, "polling_interval": watcher.polling_interval, "automatic_refresh": watcher.automatic_refresh}
    return json({"status":200, "reasons": "OK", "data": data}, status=200)

@watcherbp.get("/visit")
@protected("user")
async def visit_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = {k:{t:[p.name for p in m] for t,m in v.items()} for k,v in watcher.visit().items()}
    return json({"status":200, "reasons": "OK", "data": changes}, status=200)

@watcherbp.get("/visit/<group:str>")
@protected("user")
async def visit_group(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    changes = {k:{t:[p.name for p in m] for t,m in v.items()} for k,v in watcher.visit(group).items()}
    return json({"status":200, "reasons": "OK", "data": changes}, status=200)

@watcherbp.get("refresh")
@protected("user")
async def refresh_all(request: Request):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    watcher.visit()
    watcher.update_app(request.app)
    return json({"status":200, "reasons": "OK"}, status=200)

    
@watcherbp.post("/add/<group:str>")
@protected("super user")
async def add_group(request: Request, group: str):
    kwargs = request.load_json()
    basepaths = kwargs.get("basepaths", None)
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    exist = watcher.groups.get(group, None)
    if exist:
        raise KeyError("group already exist")
    if basepaths is None:
        raise ValueError("basepaths must contains at least one path")
    if isinstance(basepaths, list) is False:
        raise ValueError("basepaths must be a list of str")
    watcher.add_group(group, basepaths)
    return json({"status":200, "reasons": "OK"}, status=200)

@watcherbp.get("/remove/<group:str>")
@protected("super user")
async def remove_group(request: Request, group: str):
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    exist = watcher.groups.get(group, None)
    if exist is None:
        raise KeyError("group does not exist")
    watcher.remove_group(group)
    return json({"status":200, "reasons": "OK"}, status=200)

@watcherbp.post("/<group:str>/add")
@protected("super user")
async def add_to_group(request: Request, group: str):
    kwargs = request.load_json()
    paths = kwargs.get("paths", None)
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    exist = watcher.groups.get(group, None)
    if exist is None:
        raise KeyError("group does not exist")
    
    watcher.add_paths(group, paths) #, "data": {"added": added}
    return json({"status":200, "reasons": "OK"}, status=200)
    
    
@watcherbp.post("/<group:str>/remove")
@protected("super user")
async def remove_to_group(request: Request, group: str):
    kwargs = request.load_json()
    paths = kwargs.get("paths", None)
    
    watcher: LaunchpadWatcher = request.app.ctx.watcher
    exist = watcher.groups.get(group, None)
    if exist is None:
        raise KeyError("group does not exist")
    watcher.remove_paths(group, paths) #, "data": {"removed": removed}
    return json({"status":200, "reasons": "OK"}, status=200)    

