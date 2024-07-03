import logging
import traceback
from time import perf_counter
from sanic import Request
from sanic import json

from launchpad.exceptions import LaunchpadException

logger = logging.getLogger("endpointAccess")


async def error_handler(request: Request, exception: Exception):
    perf = round(perf_counter() - request.ctx.t, 5)
    status = getattr(exception, "status", 500)
    logger.error(
        f"{request.host} > {request.method} {request.url} : {str(exception)} [None][{str(status)}][{str(len(str(exception)))}b][{perf}s]" #{request.load_json()}
    )
    if not isinstance(exception.__class__.__base__, LaunchpadException):
        # log traceback of non handled errors
        logger.error(traceback.format_exc())
    return json({"status": status, "reasons": str(exception)}, status=status)
