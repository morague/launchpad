from __future__ import annotations
import sys
from abc import ABC, abstractmethod
from datetime import timedelta, datetime
from temporalio.worker import Worker
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleIntervalSpec,
    ScheduleCalendarSpec,
    ScheduleRange,
    SchedulePolicy,
    ScheduleState,
    ScheduleOverlapPolicy
)

from typing import Any, Callable, TypedDict, TypeVar, Generic, Optional

from launchpad.utils import (
    parse_retry_policy,
    define_id_reuse_policy
)

F = TypeVar('F', bound=Callable[..., Any])

class Intervals(TypedDict):
    every: list[TimedeltaArgs]
    offset: list[TimedeltaArgs]
    
class Calendar(TypedDict):
    second: list[int]
    minute: list[int]
    hour: list[int]
    day_of_month: list[int]
    month: list[int]
    year: list[int]
    day_of_week: list[int]
    comment: str

class TimedeltaArgs(TypedDict):
    days: int
    seconds: int
    microseconds: int
    milliseconds: int
    minutes: int
    hours: int
    weeks: int
    
class DateTimeArgs(TypedDict):
    year: int
    month: int
    day: int
    hours: int
    minute: int
    second: int
    microsecond: int
    tzinfo: str

class shared_signature(Generic[F]):
    def __init__(self, target: F) -> None: ...
    def __call__(self, wrapped: Callable[..., Any]) -> F: ...

class Runner(ABC):    
    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        ...
    
    @shared_signature(run)
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(*args, **kwargs)

    def parse_timedeltas(self, /, **kwargs: Optional[TimedeltaArgs] | None) -> dict[str, timedelta]:
        timedeltas = {}
        for k,v in kwargs.items():
            if v is None:
                continue
            timedeltas.update({k: timedelta(**v)})
        return timedeltas


class WorkflowRunner(Runner):
    async def run(
        self,
        workflow: Callable,
        workflow_kwargs: list[Any],
        workflow_id: str,
        task_queue: str,
        client_address: str = "localhost:7233",
        execution_timeout: Optional[TimedeltaArgs] | None = None,
        run_timeout: Optional[TimedeltaArgs] | None = None,
        task_timeout: Optional[TimedeltaArgs] | None = None,
        id_reuse_policy: Optional[str] | None = None,
        retry_policy: Optional[dict[str, Any]] | None = None,
        cron_schedule: Optional[str] = "",
        memo: Optional[dict[str, Any]] | None = None,
        start_delay: Optional[TimedeltaArgs] | None = None,
        start_signal: str | None = None,
        start_signal_args: list[Any] | None = None,
        rpc_metadata: dict[str, str] = {},
        rpc_timeout: Optional[TimedeltaArgs] | None = None,
        search_attributes: None = None,
        request_eager_start: bool = False
        ) -> None:
        
        timedeltas = self.parse_timedeltas(
            execution_timeout=execution_timeout,
            run_timeout=run_timeout,
            task_timeout=task_timeout,
            start_delay=start_delay,
            rpc_timeout=rpc_timeout
        )
        retry_policy = parse_retry_policy({"retry_policy": retry_policy})
        id_reuse_policy = define_id_reuse_policy({"id_reuse_policy": id_reuse_policy})      
        client = await Client.connect(client_address)
        await client.start_workflow(
            workflow, 
            workflow_kwargs, 
            id=workflow_id, 
            task_queue=task_queue,
            retry_policy=retry_policy,
            id_reuse_policy=id_reuse_policy,
            cron_schedule=cron_schedule,
            memo=memo,
            start_signal=start_signal,
            start_signal_args=start_signal_args,
            rpc_metadata=rpc_metadata,
            search_attributes=search_attributes,
            request_eager_start=request_eager_start,
            **timedeltas,
        )

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(*args, **kwargs)

class WorkflowRunnerWithTempWorker(Runner):
    async def run(
        self,
        workflow: Callable,
        workflow_kwargs: list[Any],
        workflow_id: str,
        task_queue: str,
        client_address: str = "localhost:7233",
        execution_timeout: Optional[TimedeltaArgs] | None = None,
        run_timeout: Optional[TimedeltaArgs] | None = None,
        task_timeout: Optional[TimedeltaArgs] | None = None,
        id_reuse_policy: Optional[str] | None = None,
        retry_policy: Optional[dict[str, Any]] | None = None,
        cron_schedule: Optional[str] = "",
        memo: Optional[dict[str, Any]] | None = None,
        start_delay: Optional[TimedeltaArgs] | None = None,
        start_signal: str | None = None,
        start_signal_args: list[Any] | None = None,
        rpc_metadata: dict[str, str] = {},
        rpc_timeout: Optional[TimedeltaArgs] | None = None,
        search_attributes: None = None,
        request_eager_start: bool = False
        ) -> None:
        
        timedeltas = self.parse_timedeltas(
            execution_timeout=execution_timeout,
            run_timeout=run_timeout,
            task_timeout=task_timeout,
            start_delay=start_delay,
            rpc_timeout=rpc_timeout
        )
        retry_policy = parse_retry_policy({"retry_policy": retry_policy})
        id_reuse_policy = define_id_reuse_policy({"id_reuse_policy": id_reuse_policy})          

        client = await Client.connect(client_address)
        activity = getattr(sys.modules[__name__], workflow_kwargs.get("activity", None))
        if activity is None:
            raise ValueError()
        
        async with Worker(client, task_queue=task_queue, workflows=[workflow], activities=[activity]):
            await client.execute_workflow(
                workflow, 
                workflow_kwargs, 
                id=workflow_id, 
                task_queue=task_queue,
                retry_policy=retry_policy,
                id_reuse_policy=id_reuse_policy,
                cron_schedule=cron_schedule,
                memo=memo,
                start_signal=start_signal,
                start_signal_args=start_signal_args,
                rpc_metadata=rpc_metadata,
                search_attributes=search_attributes,
                request_eager_start=request_eager_start,
                **timedeltas,
            )
    
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(*args, **kwargs)

class ScheduledWorkflowRunner(Runner):
    
    def _define_overlap(self, overlap: str | None = None) -> ScheduleOverlapPolicy:
        if overlap is None: 
            return ScheduleOverlapPolicy.SKIP
        overlap = getattr(ScheduleOverlapPolicy, overlap, None)
        if overlap is None:
            return KeyError()
        return overlap
        
    
    def _build_state(
        self,
        limited_actions: bool = False,
        note: Optional[str] = None,
        paused: bool = False,
        remaining_actions: int = 0
        ) -> ScheduleState:
        return ScheduleState(
            note=note,
            paused=paused,
            limited_actions=limited_actions,
            remaining_actions=remaining_actions
        )
        
    def _build_policy(
        self,
        catchup_window: Optional[TimedeltaArgs] | None = None,
        overlap: str | None = None,
        pause_on_failure: bool = False
        ) -> SchedulePolicy:
        
        if catchup_window is None:
            catchup_window = timedelta(minutes=1)
        else:
            catchup_window = timedelta(**catchup_window)
        overlap = self._define_overlap(overlap)
        
        return SchedulePolicy(
            overlap=overlap,
            catchup_window=catchup_window,
            pause_on_failure=pause_on_failure
        )
    
    def _build_specs(
        self,
        intervals: Optional[list[Intervals]] | None = None,
        calendars: Optional[list[Calendar]] | None = None,
        crons: Optional[list[str]] | None = None,
        skip: Optional[list[Calendar]] | None = None,
        start_at: Optional[list[TimedeltaArgs]] | None = None,
        end_at: Optional[DateTimeArgs] | None = None,
        jitter: Optional[TimedeltaArgs] | None = None,
        ) -> dict:
        specs = {}
        if intervals is not None:
            schedules = []
            for sched in intervals:
                schedule = {k:timedelta(**v) for k,v in sched.items() if v is not None}
                schedules.append(ScheduleIntervalSpec(**schedule))
            specs["intervals"] = schedules
            
        if calendars is not None:
            schedules = []
            for sched in calendars:
                schedule = {k:[ScheduleRange(d) for d in v] for k,v in sched.items() if v is not None}
                schedules.append(ScheduleCalendarSpec(**schedule))
            specs["calendars"] = schedules
        
        if crons is not None:
            # will assume crons are correct for now.
            specs["cron_expressions"] = crons
            
        if skip is not None:
            schedules = []
            for sched in calendars:
                schedule = {k:[ScheduleRange(d) for d in v] for k,v in sched.items() if v is not None}
                schedules.append(ScheduleCalendarSpec(**schedule))
            specs["skip"] = schedules
        
        if start_at is not None:
            specs["start_at"] = datetime(**start_at)
        if end_at is not None:
            specs["start_at"] = datetime(**end_at)
        if jitter is not None:
            specs["jitter"] = timedelta(**jitter)
        return specs
               
    async def run(
        self,
        #actions
        workflow: Callable,
        workflow_kwargs: dict[str, Any],
        scheduler_id: str,
        workflow_id: str,
        task_queue: str,
        client_address: str = "localhost:7233",
        trigger_immediately: bool = False,
        execution_timeout: Optional[TimedeltaArgs] | None = None,
        run_timeout: Optional[TimedeltaArgs] | None = None,
        task_timeout: Optional[TimedeltaArgs] | None = None,
        retry_policy: Optional[dict[str, Any]] | None = None,
        memo: Optional[dict[str, Any]] | None = None,
        #specs
        intervals: Optional[list[Intervals]] | None = None,
        calendars: Optional[list[Calendar]] | None = None,
        crons: Optional[list[str]] | None = None,
        skip: Optional[list[Calendar]] | None = None,
        start_at: Optional[DateTimeArgs] | None = None,
        end_at: Optional[DateTimeArgs] | None = None,
        jitter: Optional[TimedeltaArgs] | None = None,
        tz: str = "Europe/Paris",
        #policy
        catchup_window: Optional[TimedeltaArgs] | None = None,
        overlap: str | None = None,
        pause_on_failure: bool = False,
        #states
        limited_actions: bool = False,
        note: Optional[str] = None,
        paused: bool = False,
        remaining_actions: int = 0
        ) -> None:
        
        timedeltas = self.parse_timedeltas(
            execution_timeout=execution_timeout,
            run_timeout=run_timeout,
            task_timeout=task_timeout,
        )
        retry_policy = parse_retry_policy({"retry_policy": retry_policy})        

        client = await Client.connect(client_address)
        
        await client.create_schedule(
            id=scheduler_id, 
            trigger_immediately=trigger_immediately,
            schedule= Schedule(
                action=ScheduleActionStartWorkflow(
                    workflow,
                    workflow_kwargs,
                    id=workflow_id,
                    task_queue=task_queue,
                    retry_policy=retry_policy,
                    memo=memo,
                    **timedeltas
                ),
                spec=ScheduleSpec(**self._build_specs(
                    intervals, 
                    calendars, 
                    crons, 
                    skip, 
                    start_at, 
                    end_at, 
                    jitter
                    ), 
                    time_zone_name=tz
                ),
                policy=self._build_policy(
                    catchup_window=catchup_window,
                    overlap=overlap,
                    pause_on_failure=pause_on_failure
                ),
                state= self._build_state(
                    limited_actions=limited_actions,
                    note=note,
                    paused=paused,
                    remaining_actions=remaining_actions
                )
            ),
        )

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(**kwargs)
    




