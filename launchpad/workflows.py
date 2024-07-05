import os
import sys
import logging
import asyncio
from abc import ABC
from pathlib import Path
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import ActivityCancellationType
from temporalio.common import RetryPolicy

from typing import Any, Coroutine

from launchpad.parsers import parse_yaml
from launchpad.exceptions import NotImplemented

logger = logging.getLogger("workflows")


StrOrPath= str | Path
Payload = dict[str, Any]

def prepare_workflow_deployment(deployment:StrOrPath|Payload) -> Payload:
    if not isinstance(deployment, dict) and os.path.exists(deployment) is False:
        raise ValueError()
    elif not isinstance(deployment, dict):
        deployment = parse_yaml(deployment)
    workflow_payload = deployment.get("workflow", None)
    
    if workflow_payload is None:
        KeyError()
        
    workflow_name = workflow_payload.get("workflow", None)
    workflow_class = getattr(sys.modules[__name__], workflow_name, None)
    workflow_kwargs = workflow_payload.get("workflow_kwargs", None)
    workflow_id = workflow_payload.get("workflow_id", None)
    task_queue = workflow_payload.get("task_queue", None)
    
    if not all([workflow_class, workflow_kwargs, workflow_id, task_queue]):
        raise KeyError()
    return (workflow_class, workflow_kwargs, workflow_id, task_queue)
    


class BaseWorkflow(ABC):    
    def define_cancelation_type(self, kwargs: dict[str, Any]) -> ActivityCancellationType:
        from temporalio.workflow import ActivityCancellationType
        
        cancellation_type = kwargs.get("cancellation_type", None)
        if cancellation_type is None:
            return ActivityCancellationType.TRY_CANCEL
        return getattr(ActivityCancellationType, cancellation_type)
    
    def parse_retry_policy(self, kwargs: dict[str, Any]) -> RetryPolicy | None:
        retry_policy = kwargs.get("retry_policy", None)
        if retry_policy is None:
            return None
        
        initial_interval = retry_policy.get("initial_interval", None)
        maximum_interval = retry_policy.get("maximum_interval", None)
        
        if initial_interval is not None:
            retry_policy["initial_interval"] = timedelta(**initial_interval)
        if maximum_interval is not None:
            retry_policy["maximum_interval"] = timedelta(**maximum_interval)
        return RetryPolicy(**retry_policy)
    
    def parse_timeouts(self, kwargs: dict[str, Any]) -> dict[str, timedelta]:
        timeouts = {}
        for k,v in kwargs.items():
            if k.endswith("_timeout"):
                timeouts.update({k:timedelta(**v)})
        return timeouts
    
    async def chain(self, kwargs: dict[str, Any]) -> Coroutine[Any, Any, None] | None:
        chain = kwargs.get("chain", None)
        if chain is None:
            return
        
        handled_workflow = chain.get("handle", {})
        workflow_name = handled_workflow.get("workflow", None)
        workflow_class = getattr(sys.modules[__name__], workflow_name, None)
        workflow_id = handled_workflow.get("workflow_id", None)
        
        if workflow_class is None or workflow_id is None:
            raise KeyError()        

        handled_signal = chain.get("signal", {})
        signal_name = handled_signal.get("signal")
        signal = getattr(workflow_class, signal_name)
        signal_args = handled_signal.get("signal_args", [])
        
        handle = workflow.get_external_workflow_handle_for(workflow_class.run, workflow_id)
        return await handle.signal(signal, args=signal_args)    

    async def run(self, kwargs: dict[str, Any]):
        raise NotImplemented()
    
    
    
    
@workflow.defn(sandboxed=False)
class Task(BaseWorkflow):
    @workflow.run
    async def run(self, kwargs: dict[str, Any]):
        activity_name = kwargs.pop("activity", None)

        activity = getattr(sys.modules[__name__], activity_name, None)
        retry_policy = self.parse_retry_policy(kwargs)
        cancellation_type = self.define_cancelation_type(kwargs)
        timeouts = self.parse_timeouts(kwargs)
        args = kwargs.pop("args", [])
        
        if activity_name is None:
            raise KeyError("define an activity")
        if activity is None:
            raise ValueError("you must refresh your modules")

        logger.info(f"Starting Workflow {self.__class__.__name__} with activity {activity_name}...")
        return await workflow.execute_activity(activity, *args, **timeouts, retry_policy=retry_policy, cancellation_type=cancellation_type)

@workflow.defn(sandboxed=False)
class ChainedTask(BaseWorkflow):
    """Chained tasks uses signals to start or get started from other workflows"""
    
    async def chain(self, kwargs: dict[str, Any]) -> Coroutine[Any, Any, None] | None:
        chain = kwargs.get("chain", None)
        if chain is None:
            return
        
        
        handled_workflow = chain.get("handle", {})
        workflow_name = handled_workflow.get("workflow", None)
        workflow_class = getattr(sys.modules[__name__], workflow_name, None)
        workflow_id = handled_workflow.get("workflow_id", None)
        
        if workflow_class is None or workflow_id is None:
            raise KeyError()        

        handled_signal = chain.get("signal", {})
        signal_name = handled_signal.get("signal")
        signal = getattr(workflow_class, signal_name)
        signal_args = handled_signal.get("signal_args", [])
        
        handle = workflow.get_external_workflow_handle_for(workflow_class.run, workflow_id)
        return await handle.signal(signal, args=signal_args)
        
    @workflow.signal(name="trigger")
    async def trigger(self, name:str):
        print("signal trigger>>>>>", name)
        return name
    
    @workflow.run
    async def run(self, kwargs: dict[str, Any]):
        activity_name = kwargs.pop("activity", None)

        activity = getattr(sys.modules[__name__], activity_name, None)
        retry_policy = self.parse_retry_policy(kwargs)
        cancellation_type = self.define_cancelation_type(kwargs)
        timeouts = self.parse_timeouts(kwargs)
        args = kwargs.pop("args", [])
        
        if activity_name is None:
            raise KeyError("define an activity")
        if activity is None:
            raise ValueError("you must refresh your modules")

        logger.info(f"Starting Workflow {self.__class__.__name__} with activity {activity_name}...")
        res = await workflow.execute_activity(activity, *args, **timeouts, retry_policy=retry_policy, cancellation_type=cancellation_type)
        return await self.chain(kwargs)
        
        
@workflow.defn(sandboxed=False)  
class PollingWorkflowDeployer(BaseWorkflow):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._exit = False
        
    @workflow.signal(name="exit")
    async def exit_polling(self) -> None:
        self._exit = True

    @workflow.signal(name="queue")
    async def queue(self, name: str):
        await self._queue.put(name)
    
    @workflow.run
    async def run(self, kwargs: dict[str, Any]) -> None:
        while True:
            await workflow.wait_condition(self._polling_condition)
            
            while not self._queue.empty():
                deployment_path = self._queue.get_nowait()
                workflow_class, workflow_kwargs, workflow_id, task_queue = prepare_workflow_deployment(deployment_path)
                await workflow.start_child_workflow(workflow_class, workflow_kwargs,id=workflow_id, task_queue=task_queue)

            if self._exit:
                return 
            
    def _polling_condition(self) -> bool:
        return not self._queue.empty() or self._exit