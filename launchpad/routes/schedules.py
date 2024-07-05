




from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json

from temporalio.client import Client

from launchpad.authentication import protected

schedulesbp = Blueprint("schedulesbp", url_prefix="/schedules")

@schedulesbp.get("/")
@protected("user")
async def get_schedules(request: Request):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    infos = []
    async for schedule in await client.list_schedules():
        infos.append(schedule.info)
    print(infos)
    return empty()

@schedulesbp.post("/info/<scheduler_id:str>")
@protected("user")
async def schedule_infos(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_schedule_handle(scheduler_id,)
    desc = await handle.describe()
    # not serialisable
    return json(desc,status=200)

@schedulesbp.get("/restart/<scheduler_id:str>")
@protected("user")
async def start_schedule(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_schedule_handle(scheduler_id,) 
    await handle.unpause()  
    return json({"status":200, "reasons": "OK", "data": {scheduler_id: "restarted"}}, status=200)

@schedulesbp.get("/pause/<scheduler_id:str>")
@protected("user")
async def pause_schedule(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.pause()  
    return json({"status":200, "reasons": "OK", "data": {scheduler_id: "paused"}}, status=200)

@schedulesbp.get("/trigger/<scheduler_id:str>")
@protected("user")
async def trigger_schedule(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.trigger()
    return json({"status":200, "reasons": "OK", "data": {scheduler_id: "triggered"}}, status=200)

@schedulesbp.get("/delete/<scheduler_id:str>")
@protected("user")
async def delete_schedule(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.delete()    
    return json({"status":200, "reasons": "OK", "data": {scheduler_id: "deleted"}}, status=200)

@schedulesbp.post("/update/<scheduler_id:str>")
@protected("user")
async def update_schedule(request: Request, scheduler_id: str):
    server = request.app.config.TEMPORAL_CLIENT_ADDRESS
    client = await Client.connect(server)
    return empty()

