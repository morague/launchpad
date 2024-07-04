from __future__ import annotations
from datetime import timedelta, datetime
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleIntervalSpec, ScheduleCalendarSpec, ScheduleRange



from abc import ABC, abstractmethod
from typing import Any, Callable, TypedDict, TypeVar, Generic, Optional


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
    

class WorkflowRunner(Runner):
    async def run(
        self,
        workflow: Callable,
        workflow_kwargs: list[Any],
        workflow_id: str,
        task_queue: str,
        client_address: str = "localhost:7233",
        ) -> None:
        
        client = await Client.connect(client_address)
        result = await client.execute_workflow(
            workflow, 
            workflow_kwargs, 
            id=workflow_id, 
            task_queue=task_queue
        )

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(*args, **kwargs)


        

class ScheduledWorkflowRunner(Runner):
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
        workflow: Callable,
        workflow_kwargs: dict[str, Any],
        scheduler_id: str,
        workflow_id: str,
        task_queue: str,
        intervals: Optional[list[Intervals]] | None = None,
        calendars: Optional[list[Calendar]] | None = None,
        crons: Optional[list[str]] | None = None,
        skip: Optional[list[Calendar]] | None = None,
        start_at: Optional[DateTimeArgs] | None = None,
        end_at: Optional[DateTimeArgs] | None = None,
        jitter: Optional[TimedeltaArgs] | None = None,
        tz: str = "Europe/Paris",
        trigger_immediately: bool = False,
        client_address: str = "localhost:7233",
        ):
        client = await Client.connect(client_address)
        
        await client.create_schedule(
            id=scheduler_id, 
            trigger_immediately=trigger_immediately,
            schedule= Schedule(
                action=ScheduleActionStartWorkflow(
                    workflow,
                    workflow_kwargs,
                    id=workflow_id,
                    task_queue=task_queue
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
                )
            ),
        )

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.run(**kwargs)