

import copy

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json

deployments = Blueprint("deployments", url_prefix="/deployments")



@deployments.get("/")
async def ls_deployments(request: Request):
    deplmtns = request.app.ctx.deployments
    return json(deplmtns, status=200)

@deployments.get("/deploy/<name:str>")
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
    return json({"success": name},status=200)

@deployments.get("new/scaffold")
async def scaffold_deployment(request: Request):
    return empty()

@deployments.post("new/import")
async def import_deployment(request: Request):
    return empty()
