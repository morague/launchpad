

import copy

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, redirect

from launchpad.temporal_server import TemporalServerManager
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
    app = request.app
    temporal: TemporalServerManager = app.ctx.temporal
    await temporal.deploy(app, name)
    return json({"status":200, "reasons": "OK", "data":{"deployed": name}},status=200)

