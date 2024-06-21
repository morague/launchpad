from launchpad.workers import WorkersControler
from launchpad.temporal_server import TemporalServerControler
import asyncio
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec
from temporalio.worker import Worker
import time
from datetime import datetime, timedelta
import os

from launchpad.workflows import Task1, Task
from launchpad.activities import activities

# server =TemporalServerControler.run()


# print("_______________________________")
# print("STARTING WORKERS")
# workers = WorkersControler.initialize({"task_queue":"default","workflows": ["Task1"], "activities": ["hello", "blabla"]})
# print("_______________________________")
# print("KILLING server")
# workers.kill_all_workers()
# server.kill_server()
# time.sleep(5)
# print("here!!!!")

async def main():
    # Create client connected to server at the given address
    client = await Client.connect("localhost:7233")

    # Execute a workflow
    result = await client.execute_workflow(Task.run, "ROMAIN", id="my-workflow-id", task_queue="default")
    print(f"Result: {result}")



async def run_workflow(callable, kwargs, id, task_queue, client):
    client = await Client.connect(client)

    async with Worker(client,task_queue="default", activities= list(activities.values()), workflows=[Task, Task1]):
        result = await client.execute_workflow(callable, kwargs, id=id, task_queue=task_queue)
        print(f"Result: {result}")


async def run_interval_workflows(callable, kwargs, id, wid, task_queue, client):
    client = await Client.connect(client)
    
    await client.create_schedule(
        id, 
        Schedule(
            action=ScheduleActionStartWorkflow(
                callable,
                kwargs,
                id=wid,
                task_queue=task_queue
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=10))])
            ),
        )


async def run_cron_workflows():
    pass

async def run_delai_workflows():
    pass



# asyncio.run(run_workflow(
#     callable=Task1.run,
#     kwargs={"activity":"blabla", "args":["ROMAIN"], "client":"localhost:7233"},
#     id="my-cute-litle-workflow-id",
#     task_queue="default",
#     client="localhost:7233"
# ))

asyncio.run(run_interval_workflows(
    callable=Task1.run,
    kwargs={"activity":"appfile", "args":["ROMAIN"], "client":"localhost:7233"},
    id="my-nasty-interval",
    wid="my-cute-litle-workflow-id",
    task_queue="default",
    client="localhost:7233"
))



# if __name__ == "__main__":
#     asyncio.run(main("MIMIMI"))