import sys
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import ActivityCancellationType
from temporalio.common import RetryPolicy

from typing import Any

@workflow.defn(sandboxed=False)
class Task:
    @workflow.run
    async def run(self, kwargs: dict[str, Any]):
        print(locals())
        activity_name = kwargs.pop("activity", None)
        
        activity = getattr(sys.modules[__name__], activity_name, None)
        args = kwargs.pop("args", [])
        timeouts = self._timeouts(kwargs)
        
        retry_policy, cancellation_type = None, ActivityCancellationType.TRY_CANCEL
        retry_policy_kwargs = kwargs.get("retry_policy", None)
        cancellation_type_kwargs = kwargs.get("cancellation_type", None)
        if retry_policy_kwargs is not None:
            retry_policy = self._retry_policy(retry_policy_kwargs)
        if cancellation_type_kwargs is not None:
            cancellation_type = self._cancellation_type(cancellation_type_kwargs)
        
        if activity_name is None:
            raise KeyError("define an activity")
        if activity is None:
            raise ValueError("you must refresh your modules")
        return await workflow.execute_activity(activity, *args, **timeouts, retry_policy=retry_policy, cancellation_type=cancellation_type)
    
    def _timeouts(self, kwargs: dict[str, Any]) -> dict[str, timedelta]:
        timeouts = {}
        for k,v in kwargs.items():
            if k.endswith("_timeout"):
                timeouts.update({k:timedelta(**v)})
        return timeouts

    def _retry_policy(self, kwargs: dict[str, Any]) -> RetryPolicy:
        initial_interval = kwargs.get("initial_interval", None)
        maximum_interval = kwargs.get("maximum_interval", None)
        
        if initial_interval is not None:
            kwargs["initial_interval"] = timedelta(**initial_interval)
        if maximum_interval is not None:
            kwargs["maximum_interval"] = timedelta(**maximum_interval)
        retry_policy = RetryPolicy(**kwargs)
        return retry_policy
        
    def _cancellation_type(self, ctype: str):
        cancellation_type = getattr(ActivityCancellationType, ctype)
        return cancellation_type
