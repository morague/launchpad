from __future__ import annotations

import sys
import glob

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from collections import ChainMap, deque

import importlib, importlib.util

from types import ModuleType
from typing import Callable, Type, Optional

from launchpad.parsers import parse_yaml
from launchpad.utils import is_activity, is_workflow

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
        self._update_latest(self.version())
        if new:
            self.changes = True
    
    def __repr__(self) -> str:
        return f"<{self.module}:latest {self.latest} | changes: {self.changes}>"

    def version(self):
        with open(self.module.absolute(), 'r') as f:
            version = sha256(f.read().encode()).hexdigest()
        return version
            
    def watch(self):
        version = self.version()
        if version != self.latest:
            self.changes = True
            self._update_latest(version)
    
    def changes_resolved(self):
        self.changes = False

    def same(self, other: Path) -> bool:
        return self.module.samefile(other)

    def _update_latest(self, version: str) -> None:
        self.__historics.insert(0, ((datetime.now().isoformat(), self.__latest)))
        self.__latest = version


class YamlModule(Module):    
    def __init__(self, module_fp: str, new: bool= False) -> None:
        super().__init__(module_fp, new)
    
    def payload(self):
        return parse_yaml(self.module.absolute())
    
class PyModule(Module):    
    def __init__(self, module_fp: str, new: bool= False) -> None:
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
        return module
    
    def temporal_objects(self) -> dict[str, Callable]:
        objects = {}
        for k,v in sys.modules[self.module_name].__dict__.items():
            if k.startswith("__"):
                    continue
            if(is_activity(v) or is_workflow(v)):
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
        
    @classmethod
    def initialize(cls, name: str, paths: list[Path], skip: list[Path] = []) -> Group:
        group = cls(name, paths, skip)
        group.visit()
        return group
    
    def visit(self):
        new = True
        if len(self.modules.keys()) == 0:
            new = False
        self._remove_stale_module()
        self._watch_modules()
        self._register_module(new)
    
    def reload(self) -> None:
        for _, module in self.pymodules().items():
            if module.changes:
                module.reload()
                
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
        return {k:v for k,v in self.modules.items() if k.endswith(".py")}

    def yamlmodules(self) -> dict[str, YamlModule]:
        return {k:v for k,v in self.modules.items() if (k.endswith(".yaml") or k.endswith(".yml"))}

    def _watch_modules(self):
        [module.watch() for module in self.modules.values()]

    def _register_module(self, new: bool= False):
        new_paths = list(set(self.paths) - set(self.modules.keys()))
        for path in new_paths:
            if path.suffix in [".yml", ".yaml"]:
                self.__modules[path] = YamlModule(path, new)
            elif path.suffix == ".py":
                self.__modules[path] = PyModule(path, new)
            
    def _remove_stale_module(self):
        removed_paths = list(set(self.modules.keys()) - set(self.paths))
        [self.__modules.pop(p) for p in removed_paths]

    def _explore(self, path: Path) -> list[Path]:
        abspath = path.absolute()
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
        paths = []
        [paths.extend(g.paths) for g in self.groups]
        return paths

    @property
    def groups(self):
        return self.__groups
    
    def __init__(self, *paths: str | Path, skip: list[str | Path] | None = None, **groups: list[str | Path]) -> None:
        self.__groups = {}
        self.__basepaths = []
        self.skip = []
        if skip  is not None:
            self.skip = [Path(p) if isinstance(p, str) else p for p in skip]
        
        self.add_group("others", [Path(p) if isinstance(p, str) else p for p in paths], self.skip)
        for k, v in groups.items():
            basepaths = [Path(p) if isinstance(p, str) else p for p in v]
            self.add_group(k, basepaths, self.skip)
                
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
            raise KeyError()
        return grp
    
    def get_module(self, path: str | Path) -> PyModule | YamlModule:
        if isinstance(path, str):
            path = Path(path)
        
        module, groups = None, deque(self.groups)
        while (module is None or len(groups) > 0):
            group: Group = groups.popleft()
            module = group.modules.get(path, None)
        
        if module is None:
            raise KeyError()
        return module
            

    def visit(self, *groups: Optional[str]) -> None:
        grps = self._select_groups(groups)
        [g.visit() for g in grps]
        
    def reload(self, *groups: Optional[str]) -> None:
        grps = self._select_groups(groups)
        [g.reload() for g in grps]
        
    def temporal_objects(self, *groups: Optional[str]) -> dict[str, Callable]:
        grps = self._select_groups(groups)
        return dict(ChainMap([g.temporal_objects() for g in grps]))
    
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
        if len(group_names) == 0:
            groups = [self.get(g) for g in group_names]
        return groups
    