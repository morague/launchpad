from typing import Type, Callable

def is_workflow(cls: Type) -> bool:
    if hasattr(cls, "__temporal_workflow_definition"):
        return True
    return False

def is_activity(callable: Callable) -> bool:
    if hasattr(callable, "__temporal_activity_definition"):
        return True
    return False

def is_runner(callable: Callable) -> bool:
    if type(callable).__name__ == "ABCMeta" and callable.__bases__[0].__name__ == "Runner":
        return True
    return False

def is_temporal_worker(callable: Callable) -> bool:
    if type(callable).__name__ == "ABCMeta" and callable.__bases__[0].__name__ == "LaunchpadWorker":
        return True
    return False