import sys
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy



@workflow.defn(sandboxed=False)
class Task:
    @workflow.run
    async def run(self, kwargs):
        print(locals())
        activity_name = kwargs.pop("activity", None)
        if activity_name is None:
            raise KeyError("define an activity")
        activity = getattr(sys.modules[__name__], activity_name)
        return await workflow.execute_activity(activity, *kwargs["args"], schedule_to_close_timeout=timedelta(seconds=5))
