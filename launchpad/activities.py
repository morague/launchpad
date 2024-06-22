from __future__ import annotations

from temporalio import activity

import sys
import glob
import inspect
from hashlib import sha256
from collections import deque
import importlib
from pathlib import Path

from typing import Callable

from launchpad.utils import is_activity, is_workflow, path_into_module

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
    


class Module:
    __module: str
    __latest: str
    __historics: list[str]
    modified: bool = False
    
    @property
    def latest(self):
        return self.__latest
    
    @property
    def historics(self):
        return self.__historics
    
    @property
    def module(self):
        return self.__module    

    def __init__(self, module_fp: str) -> None:
        self.__module = module_fp
        self.__historics = []
        self._update_latest(self.version())
    
    def __repr__(self) -> str:
        return f"<{self.module}:latest {self.latest} | modified: {self.modified}>"
        
    def version(self):
        with open(self.module, 'r') as f:
            version = sha256(f.read().encode()).hexdigest()
        return version
            
    def watch(self):
        version = self.version()
        if version != self.latest:
            self.modified = True
            self._update_latest(version)
    
    def changes_resolved(self):
        self.modified = False

    def _update_latest(self, version: str) -> None:
        self.__latest = version
        self.__historics.insert(0, version)
    
    

class Watcher(object):
    __roots: list[str] = ["./"]
    __modules: dict[str, Module]
    _skip: list[str] = ["asgi.py"]

    @property
    def roots(self):
        return self.__roots
    
    @property
    def modules(self):
        return self.__modules
    
    def __init__(self, *paths) -> None:
        self.__modules = {}
        for fp in paths:
            path = Path(fp)
            if path.is_dir():
                self.__roots.append(fp)
            else:
                self.__modules[fp] = Module(fp)
        self.__roots = list(set(self.__roots))

    @classmethod
    def initialize(cls, *paths) -> Watcher:
        watcher = cls(*paths)
        watcher.visit()
        return watcher

    def visit(self) -> None:
        files = []
        [files.extend(self._explore_folder(p)) for p in self.roots]
        for file in files:
            self._register_file(file)
        self._remove_stale_files(files)
        
    def refresh(self) -> None:
        for fp, mod in self.modules.items():
            if mod.modified:
                name = path_into_module(fp)
                importlib.reload(name)
                mod.changes_resolved()

    def load_temporal_objects(self) -> dict[str, Callable]:
        objects = {}
        for name in self.pymodules().keys():
            name = path_into_module(name)
            module = importlib.import_module(name=name)
            for k,v in module.__dict__.items():
                if k.startswith("__"):
                    continue
                
                # ref = objects.get(k, None)
                # if ref is not None and (is_activity(v) or is_workflow(v)) and ref != v:
                #     raise KeyError()
                
                if(is_activity(v) or is_workflow(v)):
                    objects[k] = v
        # sys.modules[inspect.stack()[1].filename].__dict__.update(objects)
        return objects

    def pymodules(self) -> dict[str, Module]:
        return {k:v for k,v in self.modules.items() if k.endswith(".py")}
    
    def _register_file(self, fp: str) -> None:
        ref = self.modules.get(fp, None)
        if Path(fp).name in self._skip:
            return
        elif ref is None:
            self.__modules[fp] = Module(fp)
        else:
            self.modules[fp].watch()
            
    def _remove_stale_files(self, visited_files: list[str]) -> None:
        removed = list(set(self.modules.keys()) - set(visited_files))
        [self.__modules.pop(fp) for fp in removed]
    
    def _explore_folder(self, path) -> list[str]:
        py = glob.glob(f"{path}/**/[!_]*.py", recursive=True)
        yaml = glob.glob(f"{path}/**/[!_]*.yaml", recursive=True)
        yml = glob.glob(f"{path}/**/[!_]*.yml", recursive=True)
        return py + yaml + yml
    
        
    
    