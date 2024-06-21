



from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, text

from temporalio.client import Client

workersbp = Blueprint("workers", url_prefix="/workers")



@workersbp.get("/")
async def ls_workers(request: Request):
    workers = request.app.ctx.workers
    if workers is None:
        text("TemporalIo workers are handled outside of Launchad.", status=200)
        
    infos = workers.ls_workers()
    return json(infos, status=200)

@workersbp.route("/start/<task_queue:str>", methods=["GET","POST"])
async def start_worker(request: Request):
    return empty()

@workersbp.route("/kill/<task_queue:str>", methods=["GET","POST"])
async def kill_worker(request: Request, task_queue: str):
    workers = request.app.ctx.workers
    if workers is None:
        text("TemporalIo workers are handled outside of Launchad.", status=200)
    workers.kill_worker(task_queue)    
    return json({"success":task_queue}, status=200)