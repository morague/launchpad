
import copy
from datetime import timedelta
from typing import Callable, Type, Any

from temporalio.common import RetryPolicy, SearchAttributes, TypedSearchAttributes, WorkflowIDReusePolicy
from temporalio.workflow import (
    VersioningIntent,
    ActivityCancellationType,
    ParentClosePolicy,
)

def is_workflow(cls: Type) -> bool:
    if hasattr(cls, "__temporal_workflow_definition"):
        return True
    return False

def is_activity(callable: Callable) -> bool:
    if hasattr(callable, "__temporal_activity_definition"):
        return True
    return False

def is_runner(callable: Type) -> bool:
    if type(callable).__name__ == "ABCMeta" and callable.__bases__[0].__name__ == "Runner":
        return True
    return False

def is_temporal_worker(callable: Type) -> bool:
    if type(callable).__name__ == "ABCMeta" and callable.__bases__[0].__name__ == "LaunchpadWorker":
        return True
    return False


def parse_retry_policy(kwargs: dict[str, Any]) -> RetryPolicy | None:
    retry_policy = copy.deepcopy(kwargs.get("retry_policy", None))
    if retry_policy is None:
        return None

    initial_interval = retry_policy.get("initial_interval", None)
    maximum_interval = retry_policy.get("maximum_interval", None)

    if initial_interval is not None:
        retry_policy["initial_interval"] = timedelta(**initial_interval)
    if maximum_interval is not None:
        retry_policy["maximum_interval"] = timedelta(**maximum_interval)
    return RetryPolicy(**retry_policy)

def define_versioning_intent(kwargs: dict[str, Any]) -> VersioningIntent | None:
    versioning_intent = kwargs.get("versioning_intent", None)
    if versioning_intent is None:
        return None
    versioning_intent = getattr(VersioningIntent, versioning_intent, None)
    if versioning_intent is None:
        return None
    return versioning_intent

def define_cancelation_type(kwargs: dict[str, Any]) -> ActivityCancellationType | None:
    cancellation_type = kwargs.get("cancellation_type", None)
    if cancellation_type is None:
        return ActivityCancellationType.WAIT_CANCELLATION_COMPLETED
    cancellation_type = getattr(ActivityCancellationType, cancellation_type, None)
    if cancellation_type is None:
        return ActivityCancellationType.WAIT_CANCELLATION_COMPLETED
    return cancellation_type

def define_parent_close_policy(kwargs: dict[str, Any]) -> ParentClosePolicy | None:
    parent_close_policy = kwargs.get("parent_close_policy", None)
    if parent_close_policy is None:
        return ParentClosePolicy.TERMINATE
    parent_close_policy = getattr(ParentClosePolicy, parent_close_policy, None)
    if parent_close_policy is None:
        return ParentClosePolicy.TERMINATE
    return parent_close_policy

def define_id_reuse_policy(kwargs: dict[str, Any]) -> WorkflowIDReusePolicy:
    id_reuse_policy = kwargs.get("id_reuse_policy", None)
    if id_reuse_policy is None:
        return WorkflowIDReusePolicy.ALLOW_DUPLICATE
    id_reuse_policy = getattr(WorkflowIDReusePolicy, id_reuse_policy, None)
    if id_reuse_policy is None:
        return WorkflowIDReusePolicy.ALLOW_DUPLICATE
    return id_reuse_policy

def define_search_attributes(kwargs: dict[str, Any]) -> TypedSearchAttributes | SearchAttributes | None:
    return None
