from typing import Type, Callable

def is_workflow(cls: Type) -> bool:
    if hasattr(cls, "__temporal_workflow_definition"):
        return True
    return False

def is_activity(callable: Callable) -> bool:
    if hasattr(callable, "__temporal_activity_definition"):
        return True
    return False
