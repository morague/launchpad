import os
import json
from pathlib import Path
from attrs import define, field, validators
from sanic.config import DEFAULT_CONFIG
import yaml
import warnings
from yaml import SafeLoader
from collections import defaultdict, ChainMap

from typing import Dict, Any, Callable

Payload = Dict[str, Any]


def parse_yaml(fp: str|Path) -> Payload:
    with open(fp, "r") as f:
        payload = yaml.load(f, SafeLoader)
    payload = map_env(payload)
    return payload

def parse_config(config: Payload) -> Payload:
    env = os.environ.get("ENV", "development")
    main_config = config.get("app", None)

    if main_config is None:
        raise KeyError("app configs not found.")

    if env not in config.keys():
        warnings.warn(f"No specific configuration found for {env}")

    env_config = config.get(env, {})

    config = defaultdict(dict)
    for key in list(set(list(main_config.keys()) + list(env_config.keys()))):
        mcfg = main_config.get(key, None)
        ecfg = env_config.get(key, None)

        if mcfg is None and ecfg is None:
            continue

        elif not mcfg or not ecfg:
            config[key] = list(filter(None, [mcfg, ecfg]))[0]

        elif type(mcfg) != type(ecfg):
            raise TypeError(
                f"{key} from cannettes and env configs must be of same type"
            )

        elif isinstance(mcfg, dict) and isinstance(ecfg, dict):
            # -- env cfg must override in case of duplicates
            config[key] = {**mcfg, **ecfg}

        else:
            # -- last case, type is not dict, override with env config
            config[key] = ecfg

    return config


def parse_client_config(filename: str, *configs: Payload) -> None:
    """generate config json file"""
    client_cfg = dict(ChainMap(*configs))
    with open(filename, "w") as writer:
        writer.write(f"var config = {json.dumps(client_cfg)};")


def map_env(payload: Payload) -> Payload:
    for k, v in payload.items():
        if isinstance(v, str) and v.startswith("${"):
            v = os.environ.get(v.split("{")[1].strip("}"), None)
            if v is None:
                raise KeyError(f"ENV variable {k} does not exist")
            payload[k] = v
        elif isinstance(v, dict):
            payload[k] = map_env(v)
    return payload


def get_config(path: str|Path) -> Payload:
    with open(path, "r") as f:
        config = yaml.load(f, SafeLoader)
        config = parse_config(config)
        config = map_env(config)
    return config



def convert_int(value: str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        return int(value)
    else:
        raise ValueError()

@define(slots=False, kw_only=True)
class ParamsParser:
    # temporal gui ; schedules
    server_name: str | None = field(default="home", validator=[validators.instance_of(str)])
    namespace_name: str | None = field(default="default", validator=[validators.instance_of(str)])

    # DYNAMIC arguments setting.
    overwrite: dict[str, Any] | None = field(default=None)
    template_args: dict[str, Any] | None = field(default=None)

    # watcher route
    polling_interval: int | None = field(default=None, converter=convert_int)
    changed: bool | None = field(default=False)
    unchanged: bool | None = field(default=False)

    def get_kwargs(self, f: Callable) -> dict[str, Any]:
        """match function params with parsed params. Return all non null params used by the function."""
        return {k:getattr(self, k) for k,v in f.__annotations__.items() if getattr(self, k, None) is not None}
