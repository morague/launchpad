from __future__ import annotations
import sys
import os
import logging
import subprocess
import signal
import copy
from types import SimpleNamespace
from attr import validators
from sanic import Sanic
from multiprocessing import Process
from attrs import define, field, Factory

from google.protobuf.duration_pb2 import Duration
from temporalio.service import HttpConnectProxyConfig, RPCError, RPCStatusCode
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.client import Client
from temporalio.service import ConnectConfig, ServiceClient
from temporalio.api.workflowservice.v1 import RegisterNamespaceRequest, ListNamespacesRequest
from temporalio.api.operatorservice.v1 import DeleteNamespaceRequest
from temporalio.api.errordetails.v1 import NamespaceAlreadyExistsFailure

from typing import Any, Type, Coroutine

from launchpad.workers import LaunchpadWorker

ServerAddress = str
QueueName = str
TaskName = str
AioTaskName = str | None

logger = logging.getLogger("temporal")




class NameSpace:
    """
    NameSpace is an abstract representation of a TemporalIO server Namespace.
    :attr:
        :name: name of the namespace.
        :workers: workers instance runned for the namespace.
    Namespace only reference running workers.
    All workers/ workers settings are accessible from the TemporalServersManager.
    A NameSpace use those settings to build up workers.
    """
    name: str
    retention: int
    __workers: dict[QueueName, tuple[Type[LaunchpadWorker], AioTaskName]]

    @property
    def workers(self):
        return self.__workers

    def __init__(self, name: str, retention: int) -> None:
        self.name = name
        self.retention = retention
        self.__workers = {}

    def __repr__(self) -> str:
        return f"<Namespace {self.name}: workers({str([name for name in self.workers.keys()])})>"

    async def start_workers(self, settings: dict[str, Any], app: Sanic) -> None:
        worker = self._build_worker(settings)
        app.add_task(worker.run, name=f"worker__{worker.task_queue}") # type: ignore
        self.__workers.update({worker.task_queue: tuple((worker, f"worker__{worker.task_queue}"))}) # type: ignore

    async def stop_workers(self, worker_name, app: Sanic) -> None:
        await app.cancel_task(f"worker__{worker_name}", raise_exception=False)
        self.__workers.pop(f"worker__{worker_name}", None)
        app.purge_tasks()

    async def restart_workers(self, settings: dict[str, Any], app: Sanic) -> None:
        worker = self._build_worker(settings)
        await app.cancel_task(f"worker__{worker.task_queue}", raise_exception=False)
        app.purge_tasks()
        app.add_task(worker.run, name=f"worker__{worker.task_queue}") # type: ignore
        self.__workers.update({worker.task_queue: tuple((worker, f"worker__{worker.task_queue}"))}) # type: ignore

    async def close(self, app: Sanic):
        for task_queue in self.workers.keys():
            await app.cancel_task(f"worker__{task_queue}", raise_exception=False)
        app.purge_tasks()
        self.__workers = {}

    def _build_worker(self, settings: dict[str, Any]) -> Type[LaunchpadWorker]:
        module = sys.modules[__name__]
        worker_type = settings.pop("type", None)

        if worker_type is None:
            raise ValueError("worker not existing")

        workerclass: LaunchpadWorker | None = getattr(module, worker_type, None)
        if workerclass is None:
            raise KeyError("worker class not imported")

        activities = [getattr(module, k, None) for k in settings["activities"]]
        workflows = [getattr(module, k, None) for k in settings["workflows"]]

        if not all(activities + workflows):
            raise ValueError("activities or workflows not imported in workers module")

        settings["activities"] = activities
        settings["workflows"] = workflows

        return workerclass(**settings) # type: ignore








@define(repr=False)
class TemporalServer:
    name: str = field(validator=[validators.instance_of(str)])
    ip: str = field(validator=[validators.instance_of(str)])
    port: int = field(validator=[validators.instance_of(int)])
    gui_port: int = field(validator=[validators.instance_of(int)])
    namespaces: dict[str, NameSpace] = field(default=Factory(dict))
    default_namespace: NameSpace = field(init=False)
    proxy: HttpConnectProxyConfig | None = field(default=None)

    @property
    def address(self):
        return f"{self.ip}:{str(self.port)}"

    @property
    def gui_address(self):
        return f"{self.ip}:{str(self.gui_port)}"

    @property
    def namespaces_names_list(self):
        return [namespace.name for namespace in self.namespaces.values()]

    @property
    def workers(self) -> list[Type[LaunchpadWorker]]:
        return []

    def __attrs_post_init__(self) -> None:
        self.namespaces.update({"default": NameSpace("default", 604800)})
        self.default_namespace = self.namespaces.get("default") # type: ignore

    def __repr__(self) -> str:
        return f"<Temporal {self.address} : Namespaces({self.namespaces_names_list})>"

    @classmethod
    async def initialize(
        cls,
        name: str,
        ip: str,
        port: int,
        gui_port: int,
        namespaces: list[dict[str, Any]] | None = None,
        default_namespace: str | None = None,
        proxy: dict[str, Any] | None = None
    ) -> TemporalServer:
        server = cls(name, ip, port, gui_port)
        if namespaces is not None:
            for settings in namespaces:
                await server.add_namespace(**settings)
        if default_namespace is not None:
            default = server.namespaces.get(default_namespace, None)
            if default is None:
                raise KeyError("namespace does not exist")
            server.default_namespace = default
        if proxy is not None:
            ...
        return server


    async def get_client(self, namespace: str = "default") -> Client:
        # TODO: inject more args into Client.connect.
        client = await Client.connect(self.address, namespace=namespace)
        return client


    async def add_namespace(self, name: str, retention: int, **kwargs: Any) -> None:
        try:
            await self._create_namespace(name, retention, **kwargs)
        except RPCError as e:
            if e.status == RPCStatusCode.ALREADY_EXISTS:
                logger.warning(f"[Namespace: {name}] already exist.")
            else:
                raise SystemError("Namespace cannot be created")

        if self.namespaces.get(name, None) is not None:
            raise KeyError("Namespace already exist")

        namespace = NameSpace(name, retention)
        self.namespaces.update({name: namespace})

        if self.default_namespace is None:
            self.default_namespace = namespace

    async def remove_namespace(self, name: str, app: Sanic) -> None:
        namespace = self.namespaces.get(name, None)
        if namespace is None:
            raise KeyError("Namespace does not exist")
        self.namespaces.pop(name)
        await namespace.close(app)

    def update_namespace(self, name: str) -> None:
        ...

    async def close(self, app: Sanic) -> None:
        for namespace in self.namespaces.values():
            await namespace.close(app)
        self.namespaces = {}

    async def _create_namespace(self, name: str, retention: int, **kwargs) -> None:
        # TODO: add more args to connection
        client = await ServiceClient.connect(ConnectConfig(target_host=self.address))
        await client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace=name,
                workflow_execution_retention_period=Duration(seconds=retention),
                **kwargs
            )
        )

    async def _delete_namespace(self, name: str) -> None:
        client = await ServiceClient.connect(ConnectConfig(target_host=self.address))
        await client.operator_service.delete_namespace(DeleteNamespaceRequest(namespace=name))


class TemporalServersManager:
    """


    default server is None until one server is added.
    if no default is specified, then default_server is
    set to the first server listed.
    """

    __servers: dict[ServerAddress, TemporalServer]
    default_server: TemporalServer | None
    settings: SimpleNamespace
    temporal_objects: SimpleNamespace

    @property
    def servers(self):
        return self.__servers

    def __init__(self) -> None:
        self.__servers = {}
        self.default_server = None
        self.settings = SimpleNamespace(
            tasks= {},
            workers= {}
        )
        self.temporal_objects = SimpleNamespace(
            activities={},
            workflows={},
            runners={},
            workers={}
        )

    @classmethod
    async def intialize(
        cls,
        servers: list[dict[str, Any]],
        default_server: str | None = None,
        workers_settings: dict[QueueName, dict[str, Any]] | None = None,
        tasks_settings: dict[TaskName, dict[str, Any]] | None = None,
        activities: dict[str, Type] | None = None,
        workflows: dict[str, Type] | None = None,
        runners: dict[str, Type] | None = None,
        workers: dict[str, Type] | None = None,
    ) -> TemporalServersManager:

        manager = cls()
        for settings in servers:
            await manager.add_server(settings)
        if default_server is not None:
            default = manager.servers.get(default_server, None)
            if default is None:
                raise KeyError("server does not exist")
            manager.default_server = default

        manager.refresh_settings(
            tasks_settings=tasks_settings,
            workers_settings=workers_settings
        )
        manager.refresh_temporal_objects(
            activities=activities,
            workflows=workflows,
            runners=runners,
            workers=workers
        )
        return manager

    async def add_server(self, settings: dict[str, Any]) -> None:
        server = await TemporalServer.initialize(**settings)
        if self.servers.get(server.name, None) is not None:
            raise KeyError("server already exist")

        self.__servers.update({server.name: server})
        if self.default_server is None:
            self.default_server = server

    async def remove_server(self, server_name: str, app: Sanic) -> None:
        """
        remove server from __servers.
        if server is default server.
        then raise ValueError
        """
        server = self.__servers.get(server_name, None)
        if server is None:
            raise KeyError("server does not exist")
        if self.default_server == server:
            raise ValueError("Server is your default server. Cannot remove it.")
        self.__servers.pop(server_name, None)
        await server.close(app)


    def update_server(self) -> None:
        ...

    def refresh_temporal_objects(self, **temporal_objs: dict[str, Type] | None) -> None:
        for name, objects in temporal_objs.items():
            if name not in ["activities", "workflows", "runners", "workers"] or objects is None:
                continue
            setattr(self.temporal_objects, name, objects)

    def refresh_settings(self, **settings: dict[str, dict[str, Any]] | None) -> None:
        for name, setting in settings.items():
            if name not in ["tasks_settings", "workers_settings"] or setting is None:
                continue
            name = name.split("_")[0]
            setattr(self.settings, name, setting)
        print(self.settings)

    def get_server(self, server_name: str) -> TemporalServer:
        server = self.servers.get(server_name, None)
        if server is None:
            raise KeyError("Server does not exist")
        return server

    async def get_client(self, server_name: str, namespace: str = "default") -> Client:
        server = self.get_server(server_name)
        client = await server.get_client(namespace)
        return client

    async def deploy_task(self, task_name: str, app: Sanic) -> None:
        # TODO: add templating
        deployment = copy.deepcopy(self.settings.tasks.get(task_name, None))
        if deployment is None:
            raise KeyError()

        server_name = deployment.get("client", None) # RENAME SERVER ??
        namespace_name = deployment.get("namespace", None)

        if server_name is None:
            server: TemporalServer = self.default_server
        else:
            server: TemporalServer = self.get_server(server_name)

        if server is None:
            raise KeyError()

        if namespace_name is None:
            namespace = server.default_namespace
        else:
            namespace = server.namespaces.get(namespace_name)

        if namespace is None:
            raise KeyError()

        client = await server.get_client(namespace=namespace.name)

        runner_name = deployment.get("runner", None)
        runner_class = self.temporal_objects.runners.get(runner_name, None)

        if runner_name is None or runner_class is None:
            raise KeyError()

        workflow_payload = deployment.get("workflow")
        if workflow_payload is None:
            raise KeyError()

        workflow_name = workflow_payload.get("workflow", None)
        workflow_class = self.temporal_objects.workflows.get(workflow_name, None)

        if workflow_name is None or workflow_class is None:
            raise KeyError()

        workflow_payload.update({"client": client, "workflow": workflow_class})
        await runner_class()(**workflow_payload)

    async def deploy_worker(self, worker_name: str, app: Sanic):
        # TODO: add templating

        deployment = copy.deepcopy(self.settings.workers.get(worker_name, None))
        if deployment is None:
            raise KeyError("Worker queue does not exist")

        server_name = deployment.get("server", None)
        namespace_name = deployment.get("namespace", None)
        settings = deployment.get("worker", None)

        if server_name:
            server = self.servers.get(server_name, None)
        else:
            server = self.default_server

        if server is None:
            raise ValueError("server does not exist and default server unset")
        if settings is None:
            raise KeyError("Worker config unset.")

        if namespace_name is None:
            namespace = server.default_namespace
        else:
            namespace = server.namespaces.get(namespace_name, None)
        if namespace is None:
            raise KeyError("namespace not found.")

        client = await server.get_client(namespace.name)
        settings.update({"client": client})
        await namespace.start_workers(settings, app)

    async def on_server_start_deploy_tasks(self, app: Sanic) -> None:
        for task_name, settings in self.settings.tasks.items():
            deployable = settings.get("deploy_on_server_start", False)
            dynamic_settings = settings.get("dynamic_args", False)
            if deployable and dynamic_settings is False:
                try:
                    await self.deploy_task(task_name, app)
                except WorkflowAlreadyStartedError:
                    logger.warning(f"[Task: {task_name}] is already running.")
            elif deployable and dynamic_settings:
                logger.warning(f"[Task: {task_name}] Dynamic tasks templates cannot be deployed at server start...")

    async def on_server_start_deploy_workers(self, app: Sanic) -> None:
        for worker_name, settings in self.settings.workers.items():
            dynamic_settings = settings.get("dynamic_args", False)
            if dynamic_settings is False:
                await self.deploy_worker(worker_name, app)
