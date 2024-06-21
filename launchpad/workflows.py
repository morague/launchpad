import sys
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

from typing import Callable, Type

from .activities import *
sys.modules[__name__].__dict__.update(**activities)

# with workflow.unsafe.imports_passed_through():
    # from .activities import activities
    # import sys
    # sys.modules[__name__].__dict__.update(**activities)


@workflow.defn(sandboxed=False)
class Task:
    @workflow.run
    async def run(self, kwargs):
        print(locals())
        activity = kwargs.pop("activity")
        return await workflow.execute_activity(getattr(sys.modules[__name__], activity), *kwargs["args"], schedule_to_close_timeout=timedelta(seconds=5))
