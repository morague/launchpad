

from sanic import Blueprint
from sanic import Request
from sanic.response import json, html

from launchpad.authentication import Authenticator
from launchpad.exceptions import MissingLogin

loginbp = Blueprint("loginbp", url_prefix="/")

@loginbp.get("login")
async def login(request: Request):
    return html(
    """
        <html>
        <body>
            <form action="/setJwtToken" method="post">
                <label for="username">username:</label>
                <input type="text" name="username">
                <label for="password">password:</label>
                <input type="password" name="password">
                <input type="submit" value="Login">
            </form>
        </body>
        </html>
    """
    )

@loginbp.post("authenticate")
async def authenticate(request: Request):
    authenticator: Authenticator = request.app.ctx.authenticator
    payload = request.load_json()
    username = payload.get("username", None)
    password = payload.get("password", None)
    if not all([username, password]):
        raise MissingLogin()
    if authenticator is None:
        raise ValueError()
    token = authenticator.authenticate(request, username, password)
    return json({"status": 200, "reasons": "OK", "data": {"token": token, "cookie": False}})

@loginbp.post("setJwtToken")
async def setJwtToken(request: Request):
    authenticator: Authenticator = request.app.ctx.authenticator
    form = request.get_form()
    username = form.get("username", None)
    password = form.get("password", None)
    if not all([username, password]):
        raise MissingLogin()
    if authenticator is None:
        raise ValueError()
    token = authenticator.authenticate(request, username, password)
    max_age = authenticator.get_user(username).get("max_age", 600)
    response = json({"status": 200, "reasons": "OK", "data": {"token": token, "cookie": True}})
    response.add_cookie("Authorization", f"Bearer {token}", max_age=max_age)
    return response