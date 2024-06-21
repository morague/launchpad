
from temporalio import activity

@activity.defn
async def hello(name: str) -> str:
    return f'Hello {name}'

@activity.defn
async def blabla(name: str) -> str:
    return f'ABLBALBALBALBALBAL {name}'

@activity.defn
async def appfile(name: str) -> None:
    with open("res",'a+') as f:
        f.write(f"{name}\n")
        
    