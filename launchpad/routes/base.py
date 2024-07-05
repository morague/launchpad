


from sanic import Blueprint
from sanic import Request
from sanic.response import empty, redirect

from launchpad.authentication import protected

basebp = Blueprint("basebp", url_prefix="/")


@basebp.get("/favicon.ico")
async def favicon(request: Request):
    return empty()

@basebp.get("/temporal")
@protected("user")
async def get_temporal_ui(request: Request):
    gui = request.app.config.TEMPORAL_GUI_ADDRESS
    return redirect(f"http://{gui}")