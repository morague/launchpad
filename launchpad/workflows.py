import os
import sys
import copy
import logging
import asyncio
from abc import ABC
from pathlib import Path
from datetime import timedelta
from temporalio import workflow
from temporalio.client import WorkflowFailureError
from temporalio.workflow import ActivityCancellationType, VersioningIntent, ParentClosePolicy
from temporalio.common import RetryPolicy

from typing import Any, Coroutine, Callable

from launchpad.exceptions import NotImplemented
from launchpad.parsers import parse_yaml
from launchpad.utils import (
    parse_timeouts,
    parse_retry_policy,
    define_cancelation_type,
    define_parent_close_policy,
    define_versioning_intent,
    define_search_attributes,
    define_id_reuse_policy
)

logger = logging.getLogger("workflows")


StrOrPath= str | Path
Payload = dict[str, Any]


class BaseWorkflow(ABC):
    def parse_activity(self, kwargs: dict[str, Any]) -> tuple[Callable, list[Any], dict[str, Any]]:
        activity_name = kwargs.get("activity", None)
        if activity_name is None:
            raise KeyError("define an activity")

        activity = getattr(sys.modules[__name__], activity_name, None)
        if activity is None:
            raise ValueError("you must refresh your modules")

        arguments = kwargs.get("args", [])
        key_arguments = {
            "activity_id": kwargs.get("activity_id", None),
            "task_queue": kwargs.get("task_queue", None),
            "retry_policy": parse_retry_policy(kwargs),
            "cancellation_type": define_cancelation_type(kwargs),
            "versioning_intent": define_versioning_intent(kwargs)
        }
        key_arguments.update(parse_timeouts(kwargs))
        return (activity, arguments, key_arguments)

    def parse_child_workflows_settings(
        self,
        settings: StrOrPath|Payload,
        global_parameters: dict[str, Any]
        ) -> tuple[Callable, dict[str, Any], dict[str, Any]]:
        if not isinstance(settings, dict) and os.path.exists(settings) is False:
            raise ValueError()
        elif not isinstance(settings, dict):
            settings = parse_yaml(settings)
        workflow_payload: dict = settings.get("workflow", None)

        if workflow_payload is None:
            KeyError()

        workflow_name = workflow_payload.get("workflow", None)
        if workflow_name is None:
            raise KeyError()

        workflow_class = getattr(sys.modules[__name__], workflow_name, None)
        if workflow_class is None:
            raise KeyError()

        workflow_kwargs = workflow_payload.get("workflow_kwargs", None)
        key_arguments = {
            "task_queue": workflow_payload.get("task_queue", None),
            "cancellation_type": define_cancelation_type(global_parameters),
            "parent_close_policy": define_parent_close_policy(global_parameters),
            "id_reuse_policy": define_id_reuse_policy(workflow_payload),
            "retry_policy": parse_retry_policy(workflow_payload),
            "cron_schedule": workflow_payload.get("cron_schedule", ""),
            "memo": workflow_payload.get("memo", None),
            "search_attributes": define_search_attributes(workflow_payload),
            "versioning_intent": define_versioning_intent(global_parameters)
        }
        key_arguments.update(parse_timeouts(workflow_payload))
        return (workflow_class, workflow_kwargs, key_arguments)

    async def chain(self, kwargs: dict[str, Any]) -> Coroutine[Any, Any, None] | None:
        chain = kwargs.get("chain_with", None)
        if chain is None:
            return
        for chain_event in chain:
            handled_workflow = chain_event.get("handle", {})
            workflow_name = handled_workflow.get("workflow", None)
            workflow_class = getattr(sys.modules[__name__], workflow_name, None)
            workflow_id = handled_workflow.get("workflow_id", None)

            if workflow_class is None or workflow_id is None:
                raise KeyError()

            handled_signal = chain_event.get("signal", {})
            signal_name = handled_signal.get("signal")
            signal = getattr(workflow_class, signal_name)
            signal_args = handled_signal.get("signal_args", [])

            handle = workflow.get_external_workflow_handle_for(workflow_class.run, workflow_id)
            await handle.signal(signal, args=signal_args)

    async def handle_at_start(self, kwargs: dict[str, Any]) -> None:
        at_start = kwargs.get("at_start", None)
        if at_start is None:
            return
        await self.chain(at_start)

    async def handle_at_end(self, kwargs: dict[str, Any]) -> None:
        at_end = kwargs.get("at_end", None)
        if at_end is None:
            return
        await self.chain(at_end)
        if at_end.get("renew", False):
            workflow.continue_as_new(kwargs)

    async def run(self, kwargs: dict[str, Any]) -> None:
        raise NotImplemented()


@workflow.defn(sandboxed=False)
class Task(BaseWorkflow):
    @workflow.run
    async def run(self, kwargs: dict[str, Any]):
        activity_name = kwargs.get("activity", None)
        activity, arguments, key_arguments = self.parse_activity(kwargs)

        await self.handle_at_start(kwargs)
        logger.info(f"[workflow: {self.__class__.__name__}][activity: {activity_name}][args: {arguments}] Starting activity")
        await workflow.execute_activity(activity, *arguments, **key_arguments)
        await self.handle_at_end(kwargs)

@workflow.defn(sandboxed=False)
class TaskDispatcher(BaseWorkflow):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._exit = False

    @workflow.signal(name="exit")
    async def exit(self) -> None:
        self._exit = True

    @workflow.signal(name="queue")
    async def queue(self, name: str):
        await self._queue.put(name)

    @workflow.run
    async def run(self, kwargs: dict[str, Any]) -> None:
        while True:
            await workflow.wait_condition(self.polling_condition)

            while not self._queue.empty():
                settings = self._queue.get_nowait()
                workflow_class, workflow_kwargs, key_arguments = self.parse_child_workflows_settings(settings, kwargs)
                activity_name = workflow_kwargs.get("activity", None)
                args = workflow_kwargs.get("args", None)
                logger.info(f"[workflow: {self.__class__.__name__}][child workflow: {workflow_class.__name__}][activity: {activity_name}][args: {args}] Starting Child Workflow")
                await workflow.start_child_workflow(workflow_class, workflow_kwargs, **key_arguments)

            if self._exit:
                return

    def polling_condition(self) -> bool:
        return not self._queue.empty() or self._exit


@workflow.defn(sandboxed=False)
class AwaitedTask(BaseWorkflow):
    def __init__(self) -> None:
        self._start = False
        self._exit = False

    @workflow.signal(name="exit")
    async def exit(self) -> None:
        self._exit = True

    @workflow.signal(name="start")
    async def start(self):
        self._start = True

    @workflow.run
    async def run(self, kwargs: dict[str, Any]) -> None:
        await workflow.wait_condition(lambda: self._start or self._exit)

        if self._exit:
            return

        activity_name = kwargs.get("activity", None)
        activity, arguments, key_arguments = self.parse_activity(kwargs)

        await self.handle_at_start(kwargs)
        logger.info(f"[workflow: {self.__class__.__name__}][activity: {activity_name}][args: {arguments}] Starting activity")
        await workflow.execute_activity(activity, *arguments, **key_arguments)
        await self.handle_at_end(kwargs)


@workflow.defn(sandboxed=False)
class BatchTask(BaseWorkflow):
    @workflow.run
    async def run(self, kwargs: dict[str, Any]) -> None:
        batch = kwargs.get("batch", None)
        if batch is None:
            raise KeyError()

        await self.handle_at_start(kwargs)
        for activity_payload in batch:
            activity_name = activity_payload.get("activity", None)
            activity, arguments, key_arguments = self.parse_activity(activity_payload)
            logger.info(f"[workflow: {self.__class__.__name__}][activity: {activity_name}][args: {arguments}] Starting activity")
            await workflow.execute_activity(activity, *arguments, **key_arguments)
        await self.handle_at_end(kwargs)

@workflow.defn(sandboxed=False)
class AwaitedBatchTask(BaseWorkflow):
    def __init__(self) -> None:
        self._start = False
        self._exit = False

    @workflow.signal(name="exit")
    async def exit(self) -> None:
        self._exit = True

    @workflow.signal(name="start")
    async def start(self):
        self._start = True

    @workflow.run
    async def run(self, kwargs: dict[str, Any]) -> None:
        await workflow.wait_condition(lambda: self._start or self._exit)

        if self._exit:
            return

        batch = kwargs.get("batch", None)
        if batch is None:
            raise KeyError()

        await self.handle_at_start(kwargs)
        for activity_payload in batch:
            activity_name = activity_payload.get("activity", None)
            activity, arguments, key_arguments = self.parse_activity(activity_payload)
            logger.info(f"[workflow: {self.__class__.__name__}][activity: {activity_name}][args: {arguments}] Starting activity")
            await workflow.execute_activity(activity, *arguments, **key_arguments)
        await self.handle_at_end(kwargs)
