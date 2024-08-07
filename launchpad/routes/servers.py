
from sanic import Blueprint
from sanic import Request
from sanic.models.handler_types import Sanic
from sanic.response import json, empty

from launchpad.temporal.temporal_server import (
    TemporalServersManager,
    TemporalServer,
    NameSpace
)

from launchpad.authentication import protected

serversbp = Blueprint("servers", url_prefix="/servers")
workersbp = Blueprint("workers", "/workers")



@serversbp.get("/")
@protected("user")
async def get_servers_info(request: Request):
    temporal: TemporalServersManager = request.app.ctx.temporal
    return json({"status":200, "reasons": "OK", "data": temporal.info()}, status=200)

@serversbp.post("/add/<server_name: str>")
@protected("super user")
async def add_server(request: Request, server_name: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    payload = request.json
    payload.update({"name": server_name})
    await temporal.add_server(payload)
    return json({"status":200, "reasons": "OK", "data": {"added": payload}}, status=200)


@serversbp.get("/remove/<server_name: str>")
@protected("super user")
async def remove_server(request: Request, server_name: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    await temporal.remove_server(server_name, request.app)
    return json({"status":200, "reasons": "OK", "data": {"removed": server_name}}, status=200)

@serversbp.route("/<server_name: str>/add/<namespace_name: str>", methods=["GET", "POST"])
@protected("user")
async def add_namespace(request: Request, server_name: str, namespace_name: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    server = temporal.get_server(server_name)
    await  server.add_namespace(namespace_name, **request.json)
    return json({"status":200, "reasons": "OK", "data": {"added_namespace": namespace_name}}, status=200)

@serversbp.get("/<server_name: str>/remove/<namespace_name: str>")
@protected("user")
async def remove_namespace(request: Request, server_name: str, namespace_name: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    server = temporal.get_server(server_name)
    await server.remove_namespace(namespace_name, request.app)
    return json({"status":200, "reasons": "OK", "data": {"removed_namespace": namespace_name}}, status=200)

# -- WORKERS
@workersbp.route("/start/<task_queue: str>", methods=["GET", "POST"])
@protected("user")
async def start_worker(request: Request, task_queue: str):
    temporal: TemporalServersManager = request.app.ctx.temporal
    await temporal.deploy_worker(task_queue,request.app)
    return json({"status":200, "reasons": "OK", "data": {"started": task_queue}}, status=200)

@workersbp.route("/restart/<task_queue: str>", methods=["GET", "POST"])
@protected("user")
async def restart_worker(request: Request, server_name: str, namespace_name: str, task_queue: str):
    """json:: server_name; namespace_name"""
    temporal: TemporalServersManager = request.app.ctx.temporal
    await temporal.restart_worker(task_queue, request.app, **request.json)
    return json({"status":200, "reasons": "OK", "data": {"restarted": task_queue}}, status=200)


@workersbp.route("stop/<task_queue: str>", methods=["GET", "POST"])
@protected("user")
async def stop_worker(request: Request, task_queue: str):
    """json:: server_name; namespace_name"""
    temporal: TemporalServersManager = request.app.ctx.temporal
    await temporal.stop_worker(task_queue, request.app, **request.json)
    return json({"status":200, "reasons": "OK", "data": {"stopped": task_queue}}, status=200)
