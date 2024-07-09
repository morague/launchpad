

import copy

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, redirect
from temporalio.client import Client

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

@tasksbp.route('/signal/<workflow_name:str>/<workflow_id:str>/<signal_name:str>', methods=["GET", "POST"])
@protected("user")
async def signal(request: Request, workflow_name: str, workflow_id: str, signal_name: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_workflow_handle(workflow_id=workflow_id)
    
    # get the workflow_class
    workflow_class = request.app.ctx.workflows.get(workflow_name, None)
    if workflow_class is None:
        raise KeyError()
    
    signal_method = getattr(workflow_class, signal_name, None)
    if signal_method is None:
        raise KeyError()       
    
    query_args = request.get_query_args(keep_blank_values=True)
    post_args = request.json
    annotations = signal_method.__annotations__
    # parsing. TODO: move to utils
    args = []
    for arg_name, arg_type in annotations.items():
        query_val = [v for k,v in query_args if k == arg_name]
        post_val = post_args.get(arg_name, None)
        if len(query_val) > 1 or all([query_val, post_val]):
            raise ValueError("must only reference the argument once")
        if len(query_val) == 1:
            query_val = query_val[0]
        if not all([query_val, post_val]):
            raise ValueError(f"{arg_name} arg must be specified")
        val = post_val or query_val
        if isinstance(arg_type, str):
            args.append(str(val))
        if isinstance(arg_type, int):
            args.append(int(val))
        if isinstance(arg_type, bool):
            args.append(bool(val))
            
    await handle.signal(signal_method, *args)
    return json({"status":200, "reasons": "OK", "data":{"workflow": workflow_name, "workflow_id": workflow_id, "signal": signal_name}},status=200)