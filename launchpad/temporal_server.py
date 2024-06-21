from __future__ import annotations
import os
import subprocess
import signal
from multiprocessing import Process
from attrs import define, field

@define(slots=True)
class TemporalServerManager:
    __server: Process = field(default=None)
    
    @property
    def server(self):
        return self.__server
    
    @classmethod
    def run(cls, args: list[str] = []) -> TemporalServerManager:
        server = cls()
        server.__server = Process(target=server.start_server, args=args)
        server.__server.start()
        return server
        
    def start_server(self, args: list[str] = []) -> None:
        subprocess.run(" ".join(["temporal", "server", "start-dev"] + args), shell = True, executable="/bin/bash", preexec_fn=os.setsid)
    
    def kill_server(self) -> None:
        os.kill(self.server.pid, signal.SIGINT) # kill parent process as well :c
