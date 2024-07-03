



from sanic import Blueprint
from sanic import Request
from sanic.response import json, empty

from launchpad.workers import WorkersManager

workersbp = Blueprint("workers", url_prefix="/workers")



@workersbp.get("/")
async def get_workers_deployments(request: Request):
    deployments_workers = request.app.ctx.deployments_workers
    return json({"status":200, "reasons": "OK", "data": deployments_workers}, status=200)

@workersbp.get("/status")
async def ls_workers(request: Request):
    manager: WorkersManager = request.app.ctx.workers
    infos = manager.ls_workers()
    return json({"status":200, "reasons": "OK", "data": infos}, status=200)

@workersbp.route("/start/<task_queue:str>", methods=["GET","POST"])
async def start_worker(request: Request, task_queue: str):
    worker = request.app.ctx.deployments_workers.get(task_queue, None)
    if worker is None:
        raise ValueError("worker does not exist")
    
    manager: WorkersManager = request.app.ctx.workers
    _, process = manager.workers.get(task_queue, (None, None))
    if process is not None and process.is_alive():
        raise ValueError("worker already alive")

    manager.add_worker(**worker)
    return json({"status":200, "reasons": "OK", "data": manager.worker_infos(task_queue)}, status=200)
    
@workersbp.route("/stop/<task_queue:str>", methods=["GET","POST"])
async def kill_worker(request: Request, task_queue: str):
    manager: WorkersManager = request.app.ctx.workers
    manager.kill_worker(task_queue)
    return json({"status":200, "reasons": "OK", "data": manager.worker_infos(task_queue)}, status=200)

@workersbp.post("/import")
async def import_worker_deployments(request: Request):
    return empty()
