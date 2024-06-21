from __future__ import annotations

from temporalio import activity

import sys
import glob
from hashlib import sha256
from collections import deque
import importlib
from pathlib import Path


from launchpad.utils import is_activity


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
    
    

class Importer(object):
    __roots: list[str] = ["./"]
    __modules: dict[str, Module]

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
    def load(cls, *paths):
        importer = cls(*paths)
        
    
    def find_pymodules(self, folder_path) -> list[str]:
        pass
    
    def explore_folder(self, path) -> list[str]:
        pyfiles = []
        pyfiles.extend(glob.glob(f"{path}/[!_]*.py"))
        for folder in glob.glob(f"{path}/[!_]*[!.*]"):
            pyfiles.extend(self.explore_folder(folder))
        return pyfiles
            
    def is_folder_path(path) -> bool:
        pass
    
    