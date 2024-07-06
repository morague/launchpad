

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
    deployment = copy.deepcopy(request.app.ctx.deployments.get(name, None))
    if deployment is None:
        raise KeyError()

    runner_name = deployment.get("runner", None)
    runner_class = request.app.ctx.runners.get(runner_name, None)
    
    if runner_name is None or runner_class is None:
        raise KeyError()

    workflow_payload = deployment.get("workflow")
    workflow_name = workflow_payload.get("workflow", None)
    workflow_class = request.app.ctx.workflows.get(workflow_name, None)
    if workflow_name is None or workflow_class is None:
        raise KeyError()
    else:
        workflow_payload["workflow"] = workflow_class
    
    print(workflow_payload)
    await runner_class()(**workflow_payload)
    return json({"status":200, "reasons": "OK", "data":{"deployed": name}},status=200)

