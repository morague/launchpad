from __future__ import annotations


import os
import sys
import glob
import asyncio
import logging
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from collections import ChainMap, deque
from functools import wraps
from itertools import chain
from multiprocessing import Process
from sanic import Sanic

import importlib
import importlib.util
from importlib.abc import Traversable
from importlib.resources import files

from types import ModuleType
from typing import Callable, Optional, Any, Type

from launchpad.temporal_server import TemporalServersManager
from launchpad.parsers import parse_yaml
from launchpad.utils import (
    is_activity,
    is_workflow,
    is_runner,
    is_temporal_worker,
    aggregate,
    to_path
)

Datetime = str
Payload = dict[str, Any]

logger = logging.getLogger("watcher")

def log_group_visit(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        self: Group = args[0]
        changes = f(*args, **kwargs)
        total_changes = len(aggregate(changes))
        if total_changes == 0:
            return changes
        else:
            logger.info(f"> Visiting {self.name} group: {str(total_changes)} changes found.")
        for k,v in changes.items():
            if len(v) == 0:
                continue
            logger.info(f"> {k} files:")
            for path in v:
                module_or_path = self.modules.get(path, path)
                logger.info(f"    {str(module_or_path)}")
        return changes
    return wrapper

def log_watcher_visit(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        changes = f(*args, **kwargs)
        total_changes = len(aggregate(changes))
        if total_changes == 0:
            logger.info(f"> {str(total_changes)} changes found.")
        return changes
    return wrapper

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

    @property
    def from_package(self):
        return "site-packages" in [p.name for p in self.module.parents]

    def __init__(self, module_fp: str | Path, new: bool= False) -> None:
        self.__module = self._parse_path(module_fp)
        self.__latest = self.version()
        self.__historics = [((datetime.now().isoformat(), self.latest))]
        if new:
            self.changes = True

    def __repr__(self) -> str:
        return f"<{self.module}:latest {self.latest} | changes: {self.changes}>"

    def version(self):
        return sha256(self.module.read_text().encode()).hexdigest()

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
            "changes": self.changes,
            "historics": self.historics
        }

    def same(self, other: Path) -> bool:
        return self.module.samefile(other)

    def _update_latest(self, version: str) -> None:
        self.__latest = version
        self.__historics.insert(0, ((datetime.now().isoformat(), self.latest)))

    def _parse_path(self, path: str | Path):
        path = Path(path)
        if path.exists() is False:
            raise ValueError("path doesn't exist")
        return path

    def _package_rel_path(self) -> Path:
        index = [p.name for p in self.module.parents].index("site-packages")
        return self.module.relative_to(self.module.parents[index])



class YamlModule(Module):
    def __init__(self, module_fp: Path, new: bool= False) -> None:
        super().__init__(module_fp, new)

    def payload(self) -> Payload:
        return parse_yaml(self.module.absolute())

    def load(self) -> Payload:
        self.changes_resolved()
        return self.payload()

class PyModule(Module):
    def __init__(self, module_fp: Path, new: bool= False) -> None:
        super().__init__(module_fp, new)

    @property
    def module_name(self):
        if self.from_package:
            rel_path = self._package_rel_path()
        else:
            rel_path = Path(os.path.relpath(self.module))
        path = [p.name for p in rel_path.parents if p.name != ""]
        return ".".join(path + [rel_path.stem])

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

    def temporal_objects(self) -> dict[str, Type]:
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
    skips: list[Path]

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
            if p in self.skips:
                continue
            if p.is_dir():
                paths.extend(self._explore(p))
            elif p.is_file():
                paths.append(p)
        return paths

    def __init__(self, name: str, paths: list[str | Path], skips: list[str | Path] = []) -> None:
        self.__name = name
        self.__basepaths = to_path(paths)
        self.__modules = {}
        self.skips = to_path(skips)
        self.visit()

    def add_paths(self, *paths) -> list[Path]:
        paths = to_path(paths)
        skipped = [p for p in self.skips if p in paths]
        self.__basepaths = list(set(self.basepaths).union(set(paths)))
        self.skips = list(set(self.skips) - set(skipped))
        self.visit()

    def remove_paths(self, *paths) -> list[Path]:
        paths = to_path(paths)
        skipping = [p for p in paths if p not in self.basepaths]
        self.__basepaths = list(set(self.basepaths) - set(paths))
        self.skips = list(set(self.skips).union(set(skipping)))
        self.visit()

    @log_group_visit
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

    def temporal_objects(self) -> dict[str, Type]:
        objects = {}
        for _, module in self.pymodules().items():
            objects.update(module.temporal_objects())
        return objects

    def payloads(self) -> dict[str, dict]:
        payloads = {}
        for name, yaml in self.yamlmodules().items():
            payloads.update({name: yaml.load()})
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
                modified.append(path)
        return modified

    def _register_module(self, new: bool= False):
        registered = []
        new_paths = list(set(self.paths) - set(self.modules.keys()))
        for path in new_paths:
            registered.append(path)
            if path.suffix in [".yml", ".yaml"]:
                self.__modules[path] = YamlModule(path, new)
            elif path.suffix == ".py":
                self.__modules[path] = PyModule(path, new)
        return registered

    def _remove_stale_module(self):
        removed_paths = list(set(self.modules.keys()) - set(self.paths))
        [self.__modules.pop(p) for p in removed_paths]
        return removed_paths

    def _explore(self, path: Path) -> list[Path]:
        py = glob.glob(str(path.joinpath("**", "[!_]*.py")), recursive=True)
        yaml = glob.glob(str(path.joinpath("**", "[!_]*.yaml")), recursive=True)
        yml = glob.glob(str(path.joinpath("**", "[!_]*.yml")), recursive=True)
        return [Path(p) for p in py + yaml + yml if Path(p) not in self.skips]




class Watcher(object):
    __groups: dict[str, Group]

    @property
    def groups(self):
        return self.__groups

    @property
    def basepaths(self):
        return list(chain.from_iterable([g.basepaths for g in self.groups.values()]))

    @property
    def paths(self):
        return list(chain.from_iterable([g.paths for g in self.groups.values()]))

    @property
    def skips(self):
        return list(chain.from_iterable([g.skips for g in self.groups.values()]))

    @property
    def modules(self):
        return {k:[m for m in v.modules.values()] for k,v in self.groups.items()}

    @property
    def changed_modules(self):
        return {k:[m for m in v.modules.values() if m.changes] for k,v in self.groups.items()}

    @property
    def unchanged_modules(self):
        return {k:[m for m in v.modules.values() if m.changes is False] for k,v in self.groups.items()}

    def __init__(self, *paths: str | Path, **groups: Group) -> None:
        self.__groups = {k:v for k,v in groups.items()}
        if paths:
            self.add_group("others", paths, [])

    def add_group(self, name: str, basepaths: list[str | Path], skips: list[str | Path]) -> None:
        if self.groups.get(name, None):
            raise ValueError()
        basepaths = to_path(basepaths)
        self.__groups[name] = Group(name, basepaths, skips)

    def remove_group(self, name: str):
        group = self.__groups.pop(name)

    def add_paths(self, group_name: str, paths: list[str | Path]) -> None:
        group = self.groups.get(group_name, None)
        if group is None:
            raise ValueError("group does not exist")
        group.add_paths(*paths)

    def remove_paths(self, group_name: str, paths: list[str | Path]) -> None:
        group = self.groups.get(group_name, None)
        if group is None:
            raise ValueError("group does not exist")
        group.remove_paths(*paths)

    def get(self, group:str):
        grp = self.groups.get(group, None)
        if grp is None:
            raise KeyError("group does not exist")
        return grp

    def get_module(self, path: str | Path, default: Any= None) -> PyModule | YamlModule:
        module, groups = None, deque(self.groups.values())
        while (module is None and len(groups) > 0):
            group: Group = groups.popleft()
            module = group.modules.get(Path(path), None)
        return module or default

    @log_watcher_visit
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

    def temporal_objects(self, *groups: Optional[str]) -> dict[str, Type]:
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

    def temporal_objects_from_module(self, module_path: str | Path) -> dict[str, Type]:
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
    automatic_refresh: bool = True
    base_modules: dict[str, list[str | Path | Traversable]] = {
        "workflows": [files("launchpad").joinpath("workflows.py")],
        "workers": [files("launchpad").joinpath("workers.py")],
        "runners": [files("launchpad").joinpath("runners.py")],
        "routes": [files("launchpad").joinpath("routes")],
        "temporal": [files("launchpad").joinpath("temporal_server.py")]
    }

    def __init__(self, *paths: str | Path,  **groups: Group) -> None:
        super().__init__(*paths, **groups)

    @classmethod
    def initialize(cls, *paths,**groups: dict[str, list[str | Path]]) -> LaunchpadWatcher:
        basegroups = {}
        for k in list(set(cls.base_modules).union(set(groups.keys()))):
            basepaths = cls.base_modules.get(k, [])
            group = groups.get(k, {})
            skips = group.get("skips", [])
            basepaths.extend(group.get("basepaths", []))
            basegroups.update({k:Group(k, basepaths, skips)})
        return cls(*paths, **basegroups)


    def workers_settings(self) -> dict[str, dict[str, Any]]:
        return {v["worker"]["task_queue"]:v for v in self.get("workers").payloads().values()}

    def tasks_settings(self) -> dict[str, dict[str, Any]]:
        return {v["name"]:v for v in self.get("deployments").payloads().values()}

    def activities(self) -> dict[str, Type]:
        return {k:v for k,v in self.get("activities").temporal_objects().items() if is_activity(v)}

    def workflows(self) -> dict[str, Type]:
        return {k:v for k,v in self.get("workflows").temporal_objects().items() if is_workflow(v)}

    def workers(self) -> dict[str, Type]:
        return {k:v for k,v in self.get("workers").temporal_objects().items() if is_temporal_worker(v)}

    def runners(self) -> dict[str, Type]:
        return {k:v for k,v in self.get("runners").temporal_objects().items() if is_runner(v)}

    def configs(self):
        return [v for v in self.get("configs").payloads().values()]

    async def poll(self, app: Sanic) -> None:
        while True:
            await asyncio.sleep(self.polling_interval)
            logger.info("Visiting files...")
            self.visit()
            changes = any(aggregate(self.changed_modules))
            if self.automatic_refresh and changes:
                logger.info("Automatic file refreshing...")
                await self.update_app(app)
            elif changes and self.automatic_refresh is False:
                logger.info("Automatic refresing is deactivated.")
            logger.info(f"Next automatic visit in {self.polling_interval}...")

    async def update_app(self, app: Sanic) -> None:
        try:
            activities = self.activities()
            workflows = self.workflows()
            runners = self.runners()
            workers = self.workers()
            workers_settings =  self.workers_settings()
            tasks_settings = self.tasks_settings()

            self.reload()
            objects = self.temporal_objects()
            self.inject("workflows", "runners", "workers", "temporal", objects=objects)
        except Exception:
            logger.warning("Modules Update failed...")
            return

        temporal: TemporalServersManager = app.ctx.temporal
        temporal.refresh_settings(
            tasks_settings=tasks_settings,
            workers_settings=workers_settings
        )
        temporal.refresh_temporal_objects(
            activities=activities,
            workflows=workflows,
            runners= runners,
            workers= workers
        )
        logger.info("Modules Updated!")

    def set_polling_interval(self, interval: int= 600):
        self.polling_interval = interval

    def update_automatic_refresh(self, toggle: bool= True):
        self.automatic_refresh = toggle

    def _initialize_temporal_objects(self, module_name: str) -> None:
        groups = ["activities", "workflows", "workers", "runners", "routes"]
        for group in groups:
            modules = self.get(group).load()
            objects = self.get(group).temporal_objects()
            sys.modules[module_name].__dict__.update(objects)
