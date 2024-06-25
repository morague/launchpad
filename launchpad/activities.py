from __future__ import annotations

import sys
import glob

import importlib, importlib.util

from launchpad.utils import is_activity

Datetime = str

def find_modules(*paths) -> list[str]:
    modules = []
    [modules.extend(glob.glob(f"{path}/[!_]*.py")) for path in paths]
    return modules

def load_activities(module_path: str):
    segments = module_path.split("/")
    path, name = "/".join(segments[:-1]), segments[-1].split(".")[0]
    if path not in sys.path:
        sys.path.insert(0, path)
    module = importlib.import_module(name=name)
    return {f"{k}":v for k,v in module.__dict__.items() if is_activity(v)}



PATH = "../launchpad/activities"
modules_paths = find_modules(PATH)

activities = {}
for module_path in modules_paths:
    activities.update(load_activities(module_path))
    

