


from sanic import Blueprint
from sanic import Request
from sanic.response import empty, redirect

basebp = Blueprint("basebp", url_prefix="/")


@basebp.get("/favicon.ico")
async def favicon(request: Request):
    return empty()

@basebp.get("/temporal")
async def get_temporal_ui(request: Request):
    return redirect("http://localhost:8233")