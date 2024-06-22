from typing import Type, Callable

def is_workflow(cls: Type) -> bool:
    if hasattr(cls, "__temporal_workflow_definition"):
        return True
    return False

def is_activity(callable: Callable) -> bool:
    if hasattr(callable, "__temporal_activity_definition"):
        return True
    return False

def path_into_module(fp: str) -> str:
    segments = fp.split("/")
    path, name = segments[:-1], segments[-1].split(".")[0]
    if len(path) > 1:
        name = ".".join(path[1:]) + f".{name}"
    return name