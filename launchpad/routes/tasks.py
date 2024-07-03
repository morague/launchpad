

import copy

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, redirect

from launchpad.authentication import protected

tasksbp = Blueprint("tasksbp", url_prefix="/tasks")


@tasksbp.get("/")
@protected("user")
async def ls_deployments(request: Request):
    deplmtns = request.app.ctx.deployments
    return json({"status":200, "reasons": "OK", "data": deplmtns}, status=200)

@tasksbp.get("/deploy/<name:str>")
@protected("user")
async def deploy(request: Request, name: str):
    dplmt = request.app.ctx.deployments.get(name, None)
    print(dplmt)
    if dplmt is None:
        raise ValueError()
    
    deploy = copy.deepcopy(dplmt)
    workflow = deploy.get("workflow")
    runner = request.app.ctx.runners.get(deploy.get("runner"), None)
    workflow["workflow"] = request.app.ctx.workflows.get(workflow["workflow"], None)
    
    scheduler = deploy.pop("schedule", None)
    if scheduler is not None:
        workflow.update(scheduler)
    
    if runner is None:
        raise ValueError()
    
    if workflow["workflow"] is None:
        raise ValueError()
    print(deploy)
    await runner()(**workflow)
    return json({"status":200, "reasons": "OK", "data":{name: "deployed"}},status=200)

