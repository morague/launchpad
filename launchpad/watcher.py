from __future__ import annotations

import os
import sys
import glob
import time
import signal
import requests
import asyncio
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from collections import ChainMap, deque
from itertools import chain
from multiprocessing import Process
from sanic import Sanic

import importlib, importlib.util

from types import ModuleType
from typing import Callable, Type, Optional, Any

from launchpad.parsers import parse_yaml
from launchpad.utils import is_activity, is_workflow, is_runner, is_temporal_worker, aggregate

Datetime = str

class Module:
    __module: Path
    __latest: str
    __historics: list[tuple[Datetime, str]]
    changes: bool = False
    
    @property
    def latest(self):
        return self.__latest
    
    @property
    def historics(self):
        return self.__historics
    
    @property
    def module(self):
        return self.__module
    
    @property
    def ftype(self):
        return self.module.suffix.strip(".")
    
    def __init__(self, module_fp: Path, new: bool= False) -> None:
        self.__module = module_fp
        self.__historics = []
        self.__latest = self.version()
        if new:
            self.changes = True
    
    def __repr__(self) -> str:
        return f"<{self.module}:latest {self.latest} | changes: {self.changes}>"

    def version(self):
        with open(self.module.absolute(), 'r') as f:
            version = sha256(f.read().encode()).hexdigest()
        return version
            
    def watch(self):
        changes = False
        version = self.version()
        if version != self.latest:
            changes = True
            self.changes = True
            self._update_latest(version)
        return changes
    
    def changes_resolved(self):
        self.changes = False

    def as_json(self) -> dict[str, Any]:
        return {
            "path": str(self.module.relative_to("./")),
            "latest": self.latest,
            "historics": self.historics
        }
    
    def same(self, other: Path) -> bool:
        return self.module.samefile(other)

    def _update_latest(self, version: str) -> None:
        self.__historics.insert(0, ((datetime.now().isoformat(), self.latest)))
        self.__latest = version
        


class YamlModule(Module):    
    def __init__(self, module_fp: Path, new: bool= False) -> None:
        super().__init__(module_fp, new)
    
    def payload(self):
        return parse_yaml(self.module.absolute())
    
class PyModule(Module):    
    def __init__(self, module_fp: Path, new: bool= False) -> None:
        super().__init__(module_fp, new)
        
    @property
    def module_name(self):
        file = self.module.stem
        path = str(self.module.relative_to("./")).split("/")[:-1]
        return ".".join(path + [file])
    
    def reload(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location(
            self.module_name, 
            self.module.absolute()
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = module
        spec.loader.exec_module(module)
        self.changes_resolved()
        return module
    
    def temporal_objects(self) -> dict[str, Callable]:
        objects = {}
        for k,v in sys.modules[self.module_name].__dict__.items():
            if k.startswith("__"):
                    continue
            if(is_activity(v) or is_workflow(v) or is_runner(v) or is_temporal_worker(v)):
                objects[k] = v
        return objects
    
    def inject(self, objects: dict[str, Callable]) -> None:
        sys.modules[self.module_name].__dict__.update(objects)

class Group(object):
    __name: str
    __basepaths: list[Path]    
    __modules: dict[Path, Module]
    skip: list[Path]
    
    @property
    def name(self):
        return self.__name
    
    @property
    def modules(self):
        return self.__modules    

    @property
    def basepaths(self):
        return self.__basepaths
    
    @property
    def paths(self):
        paths = []
        for p in self.basepaths:
            if p in self.skip:
                continue            
            if p.is_dir():
                paths.extend(self._explore(p))
            elif p.is_file():
                paths.append(p)
        return paths
    
    def __init__(self, name: str, paths: list[Path], skip: list[Path] = []) -> None:
        self.__name = name
        self.__basepaths = paths
        self.__modules = {}
        self.skip = skip
        self.visit()
            
    def visit(self):
        new = True
        if len(self.modules.keys()) == 0:
            new = False
        removed = self._remove_stale_module()
        modified = self._watch_modules()
        added = self._register_module(new)
        return {"added": added, "modified": modified, "removed": removed}
    
    def load(self) -> None:
        return [module.reload() for _, module in self.pymodules().items()]
                        
    def reload(self) -> None:
        return [module.reload() for _, module in self.pymodules().items() if module.changes]

    def inject(self, objects: dict[str, Callable]) -> None:
        return [module.inject(objects) for _, module in self.pymodules().items()]                

    def temporal_objects(self) -> dict[str, Callable]:
        objects = {}
        for _, module in self.pymodules().items():
            objects.update(module.temporal_objects())
        return objects
            
    def payloads(self) -> dict[str, dict]:
        payloads = {}
        for name, yaml in self.yamlmodules().items():
            payloads.update({name: yaml.payload()})
        return payloads
            
    def pymodules(self) -> dict[str, PyModule]:
        return {k:v for k,v in self.modules.items() if k.name.endswith(".py")}

    def yamlmodules(self) -> dict[str, YamlModule]:
        return {k:v for k,v in self.modules.items() if (k.name.endswith(".yaml") or k.name.endswith(".yml"))}

    def _watch_modules(self):
        modified = []
        for path, module in self.modules.items():
            changes = module.watch()
            if changes:
                modified.append(path.name)
        return modified

    def _register_module(self, new: bool= False):
        registered = []
        new_paths = list(set(self.paths) - set(self.modules.keys()))
        for path in new_paths:
            registered.append(path.name)
            if path.suffix in [".yml", ".yaml"]:
                self.__modules[path] = YamlModule(path, new)
            elif path.suffix == ".py":
                self.__modules[path] = PyModule(path, new)
        return registered
        
    def _remove_stale_module(self):
        removed_paths = list(set(self.modules.keys()) - set(self.paths))
        [self.__modules.pop(p) for p in removed_paths]
        return [p.name for p in removed_paths]
        
    def _explore(self, path: Path) -> list[Path]:
        abspath = path.relative_to("./")
        py = glob.glob(f"{abspath}/**/[!_]*.py", recursive=True)
        yaml = glob.glob(f"{abspath}/**/[!_]*.yaml", recursive=True)
        yml = glob.glob(f"{abspath}/**/[!_]*.yml", recursive=True)
        return [Path(p) for p in py + yaml + yml]
        
    

class Watcher(object):
    __basepaths: list[Path]
    __groups: dict[str, Group]
    skip: list[Path]

    @property
    def basepaths(self):
        return self.__basepaths
    
    @property
    def paths(self):        
        return list(chain.from_iterable([g.paths for g in self.groups.values()]))

    @property
    def groups(self):
        return self.__groups
    
    def __init__(self, *paths: str | Path, skip: list[str | Path] | None = None, **groups: list[str | Path]) -> None:
        self.__groups = {}
        self.__basepaths = []
        self.skip = []

        if skip is not None:
            self.skip = [Path(p) if isinstance(p, str) else p for p in skip]
        
        if paths:        
            self.add_group("others", [Path(p) if isinstance(p, str) else p for p in paths])
            
        for k, v in groups.items():
            basepaths = [Path(p) if isinstance(p, str) else p for p in v]
            self.add_group(k, basepaths)
                
    def add_group(self, name: str, basepaths: list[str | Path]) -> None:
        if self.groups.get(name, None):
            raise ValueError()
        basepaths = [Path(p) if isinstance(p, str) else p for p in basepaths]
        self.__basepaths.append(basepaths)
        self.__groups[name] = Group(name, basepaths, self.skip)
        
    def remove_group(self, name: str):
        group = self.__groups.pop(name)
        [self.__basepaths.pop(i) for i in range(len(group.basepaths)) if self.basepaths[i] in group.basepaths]
        
    def get(self, group:str):
        grp = self.groups.get(group, None)
        if grp is None:
            raise KeyError("group does not exist")
        return grp
    
    def get_module(self, path: str | Path, default: Any= None) -> PyModule | YamlModule:
        if isinstance(path, str):
            path = Path(path)
        
        module, groups = None, deque(self.groups.values())
        while (module is None and len(groups) > 0):
            group: Group = groups.popleft()
            module = group.modules.get(path, None)
        return module or default
            

    def visit(self, *groups: Optional[str]) -> None:
        res = {}
        grps = self._select_groups(groups)
        for group in grps:
            changes = group.visit()
            res[group.name] = changes
        return res
        
    def reload(self, *groups: Optional[str]) -> None:
        grps = self._select_groups(groups)
        [g.reload() for g in grps]

    def load(self, *groups: Optional[str]) -> None:
        grps = self._select_groups(groups)
        [g.load() for g in grps]        

    def inject(self, *groups: Optional[str], objects: dict[str, Callable]) -> None:
        grps = self._select_groups(groups)
        [g.inject(objects) for g in grps]
    
    def temporal_objects(self, *groups: Optional[str]) -> dict[str, Callable]:
        grps = self._select_groups(groups)
        objects = {}
        [objects.update(g.temporal_objects()) for g in grps]
        return objects
    
    def payloads(self, *groups: Optional[str]) -> dict[str, dict]:
        grps = self._select_groups(groups)
        return dict(ChainMap([g.payloads() for g in grps]))
    
    def reload_module(self, module_path: str | Path) -> None:
        module = self.get_module(module_path)
        module.reload()
    
    def temporal_objects_from_module(self, module_path: str | Path) -> dict[str, Callable]:
        module = self.get_module(module_path)
        return module.temporal_objects()
    
    def payload_from_module(self, module_path: str | Path) -> dict[str, dict]:
        module = self.get_module(module_path)
        return module.payload()

    def inject_module(self, objects: dict[str, Callable], module_path: str | Path) -> None:
        module = self.get_module(module_path)
        if not isinstance(module, PyModule):
            raise TypeError()
        module.inject(objects)
        
    def _select_groups(self, group_names: tuple[str]) -> list[Group]:
        groups = self.groups.values()
        if len(group_names) > 0:
            groups = [self.get(g) for g in group_names]
        return groups
    
class LaunchpadWatcher(Watcher):
    watcher: Process | None = None
    polling_interval: int = 600
    base_modules: dict[str, list[str | Path]] = {
        "configs": [os.environ.get('CONFIG_FILEPATH', "./configs/configs.yaml")],
        "workflows": ["./launchpad/workflows.py"],
        "workers": ["./launchpad/workers.py"],
        "runners": ["./launchpad/runners.py"],
        "routes": ["./launchpad/routes"]
    }
    
    def __init__(self, *paths: str | Path, skip: list[str | Path] | None = None, **groups: list[str | Path]) -> None:
        super().__init__(*paths, skip=skip, **groups)
    
    @classmethod
    def initialize(
        cls, 
        *paths,
        configs: list[str | Path] | None = None,
        activities: list[str | Path] | None = None,
        workflows: list[str | Path] | None = None,
        runners: list[str | Path] | None = None,
        workers: list[str | Path] | None = None,
        deployments: list[str | Path] | None = None,
        ) -> LaunchpadWatcher:
        
        modules = deepcopy(cls.base_modules)
        for k,v in locals().items():
            if k in ["cls", "modules"] or v is None or len(v) == 0:
                continue
            elif k == "paths":
                modules["others"] = list(v)
            elif k not in modules.keys():
                modules[k] = v
            else:
                modules[k].extend(v)
        return cls(**modules)
    
    
    def deployments_workers(self):
        return [v for v in self.get("workers").payloads().values()]

    def activities(self):
        return {k:v for k,v in self.get("activities").temporal_objects().items() if is_activity(v)}

    def workflows(self):
        return {k:v for k,v in self.get("workflows").temporal_objects().items() if is_workflow(v)}
    
    def deployments(self): 
        return {v["name"]:v for v in self.get("deployments").payloads().values()}
        
    def temporal_workers(self):
        return {k:v for k,v in self.get("workers").temporal_objects().items() if is_temporal_worker(v)}
    
    def runners(self):
        return {k:v for k,v in self.get("runners").temporal_objects().items() if is_runner(v)}
    
    def configs(self):
        return [v for v in self.get("configs").payloads().values()]

    async def poll(self, app: Sanic) -> None:
        while True:
            await asyncio.sleep(self.polling_interval)
            res = self.visit()
            print(aggregate(res))
            if any(aggregate(res)):
                print("refreshing")
                await self.update_app(app)
    
    async def update_app(self, app: Sanic) -> None:
        try:
            activities = self.activities()
            workflows = self.workflows()
            runners = self.runners()
            temporal_workers = self.temporal_workers()
            deployments_workers =  self.deployments_workers()
            deployments = self.deployments()
            # configs = self.configs()
            
            objects = self.temporal_objects()
            self.inject("workflows", "runners", "workers", objects=objects)        
        except Exception:
            # failed to load objects # log fail
            print("failed")
            return
        app.ctx.activities = activities
        app.ctx.workflows = workflows
        app.ctx.runners = runners
        app.ctx.temporal_workers = temporal_workers
        app.ctx.deployments_workers = deployments_workers
        app.ctx.deployments = deployments
        ### update configs or not
    
    def set_polling_interval(self, interval: int= 600):
        self.polling_interval = interval
        
    def _initialize_temporal_objects(self, module_name: str) -> None:
        groups = ["activities", "workflows", "workers", "runners"]
        for group in groups:
            modules = self.get(group).load()
            objects = self.get(group).temporal_objects()
            sys.modules[module_name].__dict__.update(objects)


    # def watch(self, polling_interval: int | None = None) -> None:
    #     if polling_interval is not None:
    #         self.polling_interval = polling_interval
            
    #     if self.watcher is not None:
    #         raise ValueError("already running watcher")
            
    #     self.watcher = Process(target=self.poll)
    #     self.watcher.start()

    # def kill_watcher(self) -> None:
    #     self.watcher.kill()
    #     self.watcher = None
    