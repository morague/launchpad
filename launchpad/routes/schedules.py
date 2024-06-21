




from sanic import Blueprint
from sanic import Request
from sanic.response import empty, json, text

from temporalio.client import Client

schedules = Blueprint("schedules", url_prefix="/schedules")

@schedules.get("/")
async def get_schedules(request: Request):
    client = await Client.connect("localhost:7233")
    infos = []
    async for schedule in await client.list_schedules():
        infos.append(schedule.raw_entry.SerializeToString().decode("ascii"))
        # not serialisable
    return text(infos[0], status=200)
    # return empty()

@schedules.post("/info/<scheduler_id:str>")
async def schedule_infos(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_schedule_handle(scheduler_id,)
    desc = await handle.describe()
    # not serialisable
    return json(desc,status=200)

@schedules.get("/restart/<scheduler_id:str>")
async def start_schedule(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_schedule_handle(scheduler_id,) 
    await handle.unpause()  
    return empty()

@schedules.get("/pause/<scheduler_id:str>")
async def pause_schedule(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.pause()  
    return empty()

@schedules.get("/trigger/<scheduler_id:str>")
async def trigger_schedule(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.trigger()
    return empty()

@schedules.get("/delete/<scheduler_id:str>")
async def delete_schedule(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_schedule_handle(scheduler_id,)
    await handle.delete()    
    return empty()

@schedules.post("/update/<scheduler_id:str>")
async def update_schedule(request: Request, scheduler_id: str):
    client = await Client.connect("localhost:7233")
    return empty()

