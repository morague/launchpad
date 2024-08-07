import json
from pathlib import Path
from datetime import timedelta
from collections import deque
from jinja2 import Template, StrictUndefined
from typing import Sequence, Type, Callable, Any


def dyn_update(settings: dict[str, Any], overwrite: dict[str, Any]) -> dict[str, Any]:
    """
    dyn into nested dicts and overwrite values.
    :overwrite:
        key format: "layer0.layer1.arg"
    """
    def update(settings: dict[str, Any], layers: deque[str], value: Any) -> dict[str, Any]:
        layer = layers.popleft()
        if settings.get(layer, None) is None:
            raise KeyError(f"overwrite key {layer} not found")
        if len(layers) > 0:
            settings[layer] = update(settings[layer], layers, value)
        else:
            settings[layer] = value
        return settings

    for key, value in overwrite.items():
        layers = deque(key.split("."))
        settings = update(settings, layers, value)
    return settings

def dyn_templating(settings: dict[str, Any], template_values: dict[str, Any]) -> dict[str, Any]:
    base = json.dumps(settings)
    template = Template(base, undefined=StrictUndefined).render(**template_values)
    return json.loads(template)

def to_path(paths: Sequence[str | Path]) -> list[Path]:
    return [Path(p) if isinstance(p, str) else p for p in paths]

def aggregate(payload: dict[str, Any]) -> list[str]:
    aggregated = []
    for v in payload.values():
        if isinstance(v, dict):
            aggregated.extend(aggregate(v))
        elif isinstance(v, list):
            aggregated.extend(v)
    return aggregated

def parse_timeouts(kwargs: dict[str, Any]) -> dict[str, timedelta]:
    timeouts = {}
    for k,v in kwargs.items():
        if k.endswith("_timeout"):
            timeouts.update({k:timedelta(**v)})
    return timeouts
