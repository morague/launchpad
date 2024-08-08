from __future__ import annotations
import sys
import os
import logging
import subprocess
import signal
import copy
from collections.abc import Sequence, Mapping
from types import SimpleNamespace
from attr import validators
from sanic import Sanic
from multiprocessing import Process
from attrs import define, field, Factory

from google.protobuf.duration_pb2 import Duration
from temporalio.service import HttpConnectProxyConfig, RPCError, RPCStatusCode
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.client import Client
from temporalio.runtime import Runtime, TelemetryConfig
from temporalio.runtime import LoggingConfig, TelemetryFilter, LogForwardingConfig
from temporalio.service import ConnectConfig, ServiceClient, HttpConnectProxyConfig
from temporalio.api.workflowservice.v1 import RegisterNamespaceRequest, ListNamespacesRequest
from temporalio.api.operatorservice.v1 import DeleteNamespaceRequest
from temporalio.api.errordetails.v1 import NamespaceAlreadyExistsFailure

from typing import Any, Type, Coroutine

from launchpad.temporal.runners import Runner
from launchpad.temporal.workers import LaunchpadWorker
from launchpad.utils import dyn_update, dyn_templating
from launchpad.exceptions import (LaunchpadKeyError, LaunchpadValueError, SettingsError, MissingImportError)

ServerAddress = str
QueueName = str
ServerName = str
NameSapceName = str
TaskName = str
AioTaskName = str | None

logger = logging.getLogger("temporal")


core_runtime = Runtime(telemetry=TelemetryConfig(
    logging=LoggingConfig(
        filter= TelemetryFilter(core_level="INFO", other_level="INFO")
    )
))

RUNTIME = core_runtime
RUNTIME.set_default(core_runtime)


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

    def __init__(self, name: str, retention: int = 604800) -> None:
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

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "retention": self.retention,
            "workers": [task_queue for task_queue in self.workers.keys()]
        }

    def _build_worker(self, settings: dict[str, Any]) -> Type[LaunchpadWorker]:
        module = sys.modules[__name__]
        worker_type = settings.pop("type", None)

        if worker_type is None:
            raise SettingsError(f"Your worker settings file is missing `type` field.")

        workerclass: LaunchpadWorker | None = getattr(module, worker_type, None)
        if workerclass is None:
            raise MissingImportError(f"worker of type {worker_type} not imported.")

        activities = [getattr(module, k, None) for k in settings["activities"]]
        workflows = [getattr(module, k, None) for k in settings["workflows"]]

        if not all(activities + workflows):
            raise MissingImportError("Missing worker Activity or Workflow import.")

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
    api_key: str | None = field(default=None)
    runtime: Runtime =  RUNTIME
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
    def workers(self) -> list[tuple[NameSpace, Type[LaunchpadWorker]]]:
        workers = []
        for namespace in self.namespaces.values():
            for worker in namespace.workers.values():
                workers.append(tuple((namespace, worker)))
        return workers


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
        proxy: dict[str, Any] | None = None,
        api_key: str | None = None
    ) -> TemporalServer:
        server = cls(name, ip, port, gui_port)
        if namespaces is not None:
            for settings in namespaces:
                await server.add_namespace(**settings)
        if default_namespace is not None:
            default = server.namespaces.get(default_namespace, None)
            if default is None:
                raise LaunchpadKeyError(f"{default_namespace} namespace not found in server {name}")
            server.default_namespace = default
        if proxy is not None:
            server.proxy = HttpConnectProxyConfig(**proxy)
        if api_key is not None:
            server.api_key = api_key
        return server


    async def get_client(self, namespace: str = "default") -> Client:
        # TODO: inject more args into Client.connect.
        client = await Client.connect(
            self.address,
            namespace=namespace,
            http_connect_proxy_config=self.proxy,
            api_key=self.api_key,
            runtime=self.runtime
        )
        return client

    async def get_service(self) -> ServiceClient:
        client = await ServiceClient.connect(
            ConnectConfig(
                target_host=self.address,
                http_connect_proxy_config=self.proxy,
                api_key=self.api_key,
                runtime=self.runtime
            )
        )
        return client

    async def add_namespace(self, name: str, retention: int = 604800, **kwargs: Any) -> None:
        try:
            await self._create_namespace(name, retention, **kwargs)
        except RPCError as e:
            if e.status == RPCStatusCode.ALREADY_EXISTS:
                logger.warning(f"[Namespace: {name}] already exist.")
            else:
                raise SystemError("Namespace cannot be created")

        if self.namespaces.get(name, None) is not None:
            raise LaunchpadKeyError(f"{name} namespace already exist in server {self.name}")

        namespace = NameSpace(name, retention)
        self.namespaces.update({name: namespace})

        if self.default_namespace is None:
            self.default_namespace = namespace

    async def remove_namespace(self, name: str, app: Sanic) -> None:
        namespace = self.namespaces.get(name, None)
        if namespace is None:
            raise LaunchpadKeyError(f"{name} namespace not found in server {self.name}")
        self.namespaces.pop(name)
        await namespace.close(app)

    def update_namespace(self, name: str) -> None:
        ...

    async def close(self, app: Sanic) -> None:
        for namespace in self.namespaces.values():
            await namespace.close(app)
        self.namespaces = {}

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.gui_address,
            "namespaces": [namespace.info() for namespace in self.namespaces.values()],
            "default_namespace": self.default_namespace.info()
        }

    async def _create_namespace(self, name: str, retention: int = 604800, **kwargs) -> None:
        client = await self.get_service()
        await client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace=name,
                workflow_execution_retention_period=Duration(seconds=retention),
                **kwargs
            )
        )

    async def _delete_namespace(self, name: str) -> None:
        client = await self.get_service()
        await client.operator_service.delete_namespace(DeleteNamespaceRequest(namespace=name))


class TemporalServersManager:
    """


    default server is None until one server is added.
    if no default is specified, then default_server is
    set to the first server listed.
    """

    __servers: dict[ServerAddress, TemporalServer]
    default_server: TemporalServer
    settings: SimpleNamespace
    temporal_objects: SimpleNamespace

    @property
    def servers(self) -> dict[ServerAddress, TemporalServer]:
        return self.__servers

    @property
    def workers(self) -> list[tuple[TemporalServer, NameSpace, Type[LaunchpadWorker]]]:
        workers = []
        for server in self.servers.values():
            for namespace, worker in server.workers:
                workers.append(tuple((server, namespace, worker)))
        return workers

    def __init__(self) -> None:
        self.__servers = {}
        self.settings = SimpleNamespace(tasks = {},workers = {})
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
        workers_settings: Mapping[QueueName, dict[str, Any]] | None = None,
        tasks_settings: Mapping[TaskName, dict[str, Any]] | None = None,
        activities: Mapping[str, Type] | None = None,
        workflows: Mapping[str, Type] | None = None,
        runners: Mapping[str, Type] | None = None,
        workers: Mapping[str, Type] | None = None,
    ) -> TemporalServersManager:

        manager = cls()
        for settings in servers:
            await manager.add_server(settings)
        if default_server is not None:
            default = manager.servers.get(default_server, None)
            if default is None:
                raise LaunchpadKeyError(f"{default_server} not found. cannot be set as default server")
            manager.default_server = default
        elif len(servers) == 1:
            key = list(manager.servers.keys())[0]
            default = manager.servers.get(key)
            manager.default_server = default # type: ignore
        else:
            raise SettingsError(f"You must set a default server.")

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

    def info(self) -> dict[str, Any]:
        return {name:server.info() for name, server in self.servers.items()}

    async def add_server(self, settings: dict[str, Any]) -> None:
        server = await TemporalServer.initialize(**settings)
        if self.servers.get(server.name, None) is not None:
            raise LaunchpadKeyError(f" cannot set server :{server.name}. server name already exist")

        self.__servers.update({server.name: server})
        if getattr(self, "default_server", None):
            self.default_server = server

    async def remove_server(self, server_name: str, app: Sanic) -> None:
        """
        remove server from __servers.
        if server is default server.
        then raise ValueError
        """
        server = self.__servers.get(server_name, None)
        if server is None:
            raise LaunchpadKeyError(f"cannot remove server: {server_name}. {server_name} key does not exist.")
        if self.default_server == server:
            raise LaunchpadValueError(f"cannot remove server: {server_name}. {server_name} is set as default server.")
        self.__servers.pop(server_name, None)
        await server.close(app)

    def update_server(self) -> None:
        ...

    def refresh_temporal_objects(self, **temporal_objs: Mapping[str, Type] | None) -> None:
        for name, objects in temporal_objs.items():
            if name not in ["activities", "workflows", "runners", "workers"] or objects is None:
                continue
            setattr(self.temporal_objects, name, objects)

    def refresh_settings(self, **settings: Mapping[str, Mapping[str, Any]] | None) -> None:
        for name, setting in settings.items():
            if name not in ["tasks_settings", "workers_settings"] or setting is None:
                continue
            name = name.split("_")[0]
            setattr(self.settings, name, setting)

    def get_task_settings(
        self,
        task_name: str,
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        settings = copy.deepcopy(self.settings.tasks.get(task_name, None))
        if settings is None:
            raise SettingsError(f"Cannot load tasks settings: {task_name}. Tasks settings not found under name {task_name}.")
        settings = self._dyn_update_settings(settings, overwrite, template_args)
        return settings

    def get_worker_settings(
        self,
        worker_name: str,
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        settings = copy.deepcopy(self.settings.workers.get(worker_name, None))
        if settings is None:
            raise SettingsError(f"Cannot load worker settings: {worker_name}. worker settings not found under name {worker_name}.")
        settings = self._dyn_update_settings(settings, overwrite, template_args)
        return settings

    def get_server(self, server_name: str) -> TemporalServer:
        server = self.servers.get(server_name, None)
        if server is None:
            raise LaunchpadKeyError(f"cannot get server: {server_name}. Server {server_name} name does not exist")
        return server

    async def get_temporal_frame(self, namespace_name: str | None = None, server_name: str | None = None) -> tuple[TemporalServer, NameSpace, Client]:
        """ get a server, namespace frame a client connection"""
        if server_name is None:
            server: TemporalServer = self.default_server
        else:
            server: TemporalServer = self.get_server(server_name)

        if server is None:
            raise LaunchpadKeyError(f"cannot get server: {server_name}. Server {server_name} name does not exist")

        if namespace_name is None:
            namespace = server.default_namespace
        else:
            namespace = server.namespaces.get(namespace_name)

        if namespace is None:
            raise LaunchpadKeyError(f"cannot get namespace: {namespace_name} from server {server_name}. namespace {namespace_name} does not exist")

        client = await server.get_client(namespace=namespace.name)
        return (server, namespace, client)

    async def get_client(self, server_name: str, namespace: str = "default") -> Client:
        server = self.get_server(server_name)
        client = await server.get_client(namespace)
        return client

    def get_workers(
        self,
        task_queue: str,
        server_name: str | None = None,
        namespace_name: str | None = None
    ) -> list[tuple[TemporalServer, NameSpace, Type[LaunchpadWorker]]]:
        def condition(server: TemporalServer, namespace: NameSpace, worker: Type[LaunchpadWorker]) -> bool:
            is_server, is_namespace, is_task_queue = True, True, True
            if server_name is not None and server.name != server_name:
                is_server = False
            if namespace is not None and namespace.name != namespace_name:
                is_namespace = False
            if worker.task_queue != task_queue:
                is_task_queue = False
            return all([is_server, is_namespace, is_task_queue])
        return [payload for payload in self.workers if condition(*payload)]

    def get_task_runner(self, settings: dict[str, Any]) -> Type[Runner]:
        runner_name = settings.get("runner", None)
        runner_class = self.temporal_objects.runners.get(runner_name, None)

        if runner_name is None:
            raise SettingsError("Cannot get Temporal runner. Tasks settings must set a `runner` field.")
        if runner_class is None:
            raise MissingImportError(f"Cannot get Temporal runner. `{runner_name}` is not imported.")
        return runner_class

    async def deploy_task(
        self,
        task_name: str,
        app: Sanic,
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> None:
        deployment = self.get_task_settings(task_name, overwrite, template_args)
        server, namespace, client = await self._get_temporal_frame(deployment)
        runner = self.get_task_runner(deployment)
        settings = self._get_runner_frame(deployment, client)
        await runner()(**settings)

    async def deploy_worker(
        self,
        worker_name: str,
        app: Sanic,
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> None:
        deployment = self.get_worker_settings(worker_name, overwrite, template_args)
        server, namespace, client = await self._get_temporal_frame(deployment)
        # get worker frame
        settings = deployment.get("worker", None)
        settings.update({"client": client})
        await namespace.start_workers(settings, app)

    async def restart_worker(
        self,
        task_queue: str,
        app: Sanic,
        # find worker
        server_name: str | None = None,
        namespace_name: str | None = None,
        # apply dynamic update
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> None:
        workers = self.get_workers(task_queue, server_name, namespace_name)
        if len(workers) == 1:
            server, namespace, worker = workers[0]
        else:
            raise LaunchpadKeyError(f"Cannot select a worker to restart. Multiple workers found. Define a server name and a namespace name to refine your search.")

        deployment = self.settings.workers.get(worker.task_queue)
        deployment = self._dyn_update_settings(deployment, overwrite, template_args)

        client = await server.get_client(namespace.name)
        deployment.update({"namespace": namespace.name, "client": client})
        await namespace.restart_workers(deployment, app)

    async def stop_worker(
        self,
        task_queue: str,
        app: Sanic,
        server_name: str | None = None,
        namespace_name: str | None = None
    ) -> None:
        workers = self.get_workers(task_queue, server_name, namespace_name)
        if len(workers) == 1:
            server, namespace, worker = workers[0]
        else:
            raise LaunchpadKeyError(f"Cannot select a worker to stop. Multiple workers found. Define a server name and a namespace name to refine your search.")
        await namespace.stop_workers(task_queue, app)

    async def on_server_start_deploy_tasks(self, app: Sanic) -> None:
        for task_name, settings in self.settings.tasks.items():
            deployable = settings.get("deploy_on_server_start", False)
            dynamic_settings = settings.get("template", False)
            if deployable and dynamic_settings is False:
                try:
                    await self.deploy_task(task_name, app)
                except WorkflowAlreadyStartedError:
                    logger.warning(f"[Task: {task_name}] is already running.")
            elif deployable and dynamic_settings:
                logger.warning(f"[Task: {task_name}] Dynamic tasks templates cannot be deployed at server start...")

    async def on_server_start_deploy_workers(self, app: Sanic) -> None:
        for worker_name, settings in self.settings.workers.items():
            dynamic_settings = settings.get("template", False)
            if dynamic_settings is False:
                await self.deploy_worker(worker_name, app)

    def _dyn_update_settings(
        self,
        settings: dict[str, Any],
        overwrite: dict[str, Any] | None = None,
        template_args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        overwritable = settings.get("overwritable", False)
        dynamic_template = settings.get("template", False)

        if dynamic_template and template_args:
            settings = dyn_templating(settings, template_args)

        if overwritable and overwrite:
            settings = dyn_update(settings, overwrite)
        return settings

    async def _get_temporal_frame(self, settings: dict[str, Any]) -> tuple[TemporalServer, NameSpace, Client]:
        server_name = settings.get("server", None)
        namespace_name = settings.get("namespace", None)
        return await self.get_temporal_frame(namespace_name, server_name)

    def _get_runner_frame(self, settings: dict[str, Any] , client: Client) -> dict[str, Any]:
        payload = settings.get("workflow", None)
        if payload is None:
            raise SettingsError("Task settings missing `workflow` field.")

        workflow_name = payload.get("workflow", None)
        workflow_class = self.temporal_objects.workflows.get(workflow_name, None)

        if workflow_name is None:
            raise LaunchpadKeyError(f"Task settings missing `workflow.workflow` field.")

        if workflow_class is None:
            raise MissingImportError(f"cannot get temporal workflow. `{workflow_name}` is not imported")

        payload.update({"client": client, "workflow": workflow_class})
        return payload
