# import asyncio
# from temporalio.client import Client

# # Import the workflow from the previous code
# from launchpad.workflows import Task

# async def main():
#     # Create client connected to server at the given address
#     client = await Client.connect("localhost:7233")

#     # Execute a workflow
#     result = await client.execute_workflow(Task.run, "ROMAIN", id="my-workflow-id", task_queue="default")
#     print(f"Result: {result}")

# if __name__ == "__main__":
#     asyncio.run(main())

from launchpad.workflows import Task, Task1
from launchpad.activities import activities

from launchpad.workers import WorkersManager
workers = WorkersManager.as_main({"task_queue":"default", "workflows": [Task1,Task], "activities": list(activities.values())}) #, "activities": ["hello", "blabla"]