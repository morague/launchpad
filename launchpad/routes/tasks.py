

import copy

from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, redirect
from temporalio.client import (
    Client,
    ScheduleUpdate,
    ScheduleUpdateInput,
)

from launchpad.temporal_server import TemporalServersManager
from launchpad.authentication import protected

tasksbp = Blueprint("tasksbp", url_prefix="/tasks")
schedulesbp = Blueprint("schedulesbp", url_prefix="/schedules")

@tasksbp.get("/")
@protected("user")
async def ls_deployments(request: Request):
    temporal: TemporalServersManager = request.app.ctx.temporal
    tasks_settings = temporal.settings.tasks
    return json({"status":200, "reasons": "OK", "data": tasks_settings}, status=200)

@tasksbp.route("/deploy/<name:str>", methods=["GET", "POST"])
@protected("user")
async def deploy(request: Request, name: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    params = request.ctx.params.get_kwargs(temporal.deploy_task)
    await temporal.deploy_task(name, request.app, **params)
    return json({"status":200, "reasons": "OK", "data":{"deployed": name}},status=200)

@tasksbp.route('/signal/<server_name:str>/<namespace:str>/<workflow_name:str>/<workflow_id:str>/<signal_name:str>', methods=["GET", "POST"])
@protected("user")
async def signal(request: Request, server_name: str, namespace: str, workflow_name: str, workflow_id: str, signal_name: str):
    # TODO : reduce complexity of the endpoint...
    temporal: TemporalServersManager = request.app.ctx.temporal
    client = await temporal.get_client(server_name, namespace)
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

# -- SCHEDULES

@schedulesbp.route("/restart/<scheduler_id:str>", methods=["GET", "POST"])
@protected("user")
async def start_schedule(request: Request, scheduler_id: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    params = request.ctx.params.get_kwargs(temporal.get_temporal_frame)
    server, namespace, client = await temporal.get_temporal_frame(**params)

    handle = client.get_schedule_handle(scheduler_id,)
    await handle.unpause()
    return json({"status":200, "reasons": "OK", "data": {
        "server": server.name,
        "namespace": namespace.name,
        "restarted":scheduler_id
        }
    }, status=200)

@schedulesbp.route("/pause/<scheduler_id:str>", methods=["GET", "POST"])
@protected("user")
async def pause_schedule(request: Request, scheduler_id: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    params = request.ctx.params.get_kwargs(temporal.get_temporal_frame)
    server, namespace, client = await temporal.get_temporal_frame(**params)

    handle = client.get_schedule_handle(scheduler_id,)
    await handle.pause()
    return json({"status":200, "reasons": "OK", "data": {
        "server": server.name,
        "namespace": namespace.name,
        "paused":scheduler_id
        }
    }, status=200)

@schedulesbp.route("/trigger/<scheduler_id:str>", methods=["GET", "POST"])
@protected("user")
async def trigger_schedule(request: Request, scheduler_id: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    params = request.ctx.params.get_kwargs(temporal.get_temporal_frame)
    server, namespace, client = await temporal.get_temporal_frame(**params)

    handle = client.get_schedule_handle(scheduler_id,)
    await handle.trigger()
    return json({"status":200, "reasons": "OK", "data": {
        "server": server.name,
        "namespace": namespace.name,
        "triggered": scheduler_id
        }
    }, status=200)

@schedulesbp.route("/delete/<scheduler_id:str>", methods=["GET", "POST"])
@protected("user")
async def delete_schedule(request: Request, scheduler_id: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    params = request.ctx.params.get_kwargs(temporal.get_temporal_frame)
    server, namespace, client = await temporal.get_temporal_frame(**params)

    handle = client.get_schedule_handle(scheduler_id,)
    await handle.delete()
    return json({"status":200, "reasons": "OK", "data": {
        "server": server.name,
        "namespace": namespace.name,
        "triggered": scheduler_id
        }
    }, status=200)
