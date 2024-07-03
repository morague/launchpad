
import logging
from time import perf_counter
from sanic import Request, HTTPResponse

logger = logging.getLogger("endpointAccess")

async def go_fast(request: Request) -> Request:
    request.ctx.t = perf_counter()

async def log_exit(request: Request, response: HTTPResponse) -> HTTPResponse:
    perf = round(perf_counter() - request.ctx.t, 5)
    if response.status == 200:
        logger.info(
            f"{request.host} > {request.method} {request.url} [None][{str(response.status)}][{str(len(response.body))}b][{perf}s]" #{request.load_json()}
        )
            
async def cookie_token(request: Request) -> Request:
    cookie = request.cookies.get("Authorization", None)
    if cookie is not None:
        request.headers.add("Authorization", cookie)