


from sanic import Blueprint
from sanic import Request
from sanic.response import empty, redirect

from launchpad.authentication import protected
from launchpad.temporal.temporal_server import TemporalServersManager

basebp = Blueprint("basebp", url_prefix="/")


@basebp.get("/favicon.ico")
async def favicon(request: Request):
    return empty()

@basebp.get("/temporal")
@protected("user")
async def get_temporal_ui(request: Request):
    temporal: TemporalServersManager = request.app.ctx.temporal

    server_name = request.ctx.params.server_name
    server = temporal.get_server(server_name)
    return redirect(f"http://{server.gui_address}")
