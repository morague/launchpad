"""



"""



from temporalio import activity



@activity.defn
async def hello(name: str) -> str:
    return f'Hello {name}'
