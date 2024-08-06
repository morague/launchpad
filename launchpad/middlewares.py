
import logging
import traceback
from time import perf_counter
from collections import ChainMap
from urllib.parse import unquote
from sanic import Request, HTTPResponse, json

from launchpad.parsers import ParamsParser
from launchpad.exceptions import LaunchpadException

logger = logging.getLogger("endpointAccess")

async def go_fast(request: Request) -> None:
    request.ctx.t = perf_counter()

async def log_exit(request: Request, response: HTTPResponse) -> None:
    size = "0"
    perf = round(perf_counter() - request.ctx.t, 5)
    if response.status == 200:
        if response.body is not None:
            size = str(len(response.body))
        logger.info(
            f"{request.host} > {request.method} {request.url} [None][{str(response.status)}][{size}b][{perf}s]"
        )

async def cookie_token(request: Request) -> None:
    cookie = request.cookies.get("Authorization", None)
    if cookie is not None:
        request.headers.add("Authorization", cookie)

async def extract_params(request: Request) -> None:
    nid = {k:unquote(v) for k,v in request.match_info.items() if k == "nid"} or {}
    query_args = {k:(v[0] if len(v) == 1 else v) for k,v in request.args.items()}
    payload = request.load_json() or {}
    params = dict(ChainMap(nid, payload, query_args))
    request.ctx.params = ParamsParser(**params)

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
