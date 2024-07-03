from pathlib import Path
from typing import Type, Callable, Any

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

def aggregate(payload: dict[str, Any]) -> list[str]:
    aggregated = []
    for v in payload.values():
        if isinstance(v, dict):
            aggregated.extend(aggregate(v))
        elif isinstance(v, list):
            aggregated.extend(v)
    return aggregated

def query_kwargs(args: list[tuple[str, str]]) -> dict[str, Any]:
    kwargs = {}
    for k,v in args:
        if v.isnumeric():
            kwargs.update({k:int(v)})
    return kwargs

def to_path(paths: list[str | Path]) -> list[Path]:
    return [Path(p) if isinstance(p, str) else p for p in paths]