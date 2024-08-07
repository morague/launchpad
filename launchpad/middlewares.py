
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

async def parse_args(request: Request) -> None:
    args = {}
    for pair in request.get_args(keep_blank_values=True):
        if len(pair) == 2:
            key, value = pair
            args[key] = unquote(value)
        elif len(pair) == 1:
            key = pair[0]
            args[key] = True
    request.ctx.args = args

async def parse_url(request: Request) -> None:
    request.ctx.infos = {k:(unquote(v) if isinstance(v, str) else v)for k, v in request.match_info.items()} or {}

async def extract_params(request: Request) -> None:
    payload = request.load_json() or {}
    params = dict(ChainMap(
        payload,
        request.ctx.args
    ))
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
