import random
import pytest
import jwt
import time
from sanic import Sanic, response, Request

from launchpad.authentication import Authenticator, User, protected
from launchpad.exceptions import InvalidLogin, OutatedAuthorizationToken, InvalidToken, AccessDenied, AuthorizationTokenRequired

random.seed(10)

@pytest.fixture
def app():
    sanic_app = Sanic("TestSanic")
    sanic_app.config["SECRET"] = "xxx"
    
    @sanic_app.get("/")
    def foo(request):
        return response.text("foo")

    @sanic_app.get("/bar")
    @protected("super user")
    def bar(request):
        return response.text("bar")
    return sanic_app


def test_users():
    user1 = {
        "username": "admin",
        "password": "admin",
        "max_age": 600
    }
    
    user2 = {
        "username": "admin",
        "password": "admin",
        "auth_level": ["super uer"],
        "max_age": 600
    }
    
    user3 = {
        "username": "admin",
        "password": "admin",
        "auth_level": ["super user"],
        "max_age": 600.9
    }    
    
    user4 = {
        "username": "admin",
        "password": "admin",
        "auth_level": ["super user"],
        "max_age": 600
    }
    
    with pytest.raises(TypeError):
        u1 = User(**user1)
        u3 = User(**user3)
        
    with pytest.raises(ValueError):
        u2 = User(**user2)
    
    u4 = User(**user4)
    assert u4.to_sql() == [
        'admin',
        '4a1cebdf32cdb6e13538e665c0586808086d1478a493fc3b7bd37aed49092fe2',
        ['super user'],
        'KcBEKanDFrPZkcHF',
        600
    ]
    

def test_users_db():

    user1 = {
        "username": "admin",
        "password": "admin",
        "auth_level": ["super user"],
        "max_age": 600
    }

    user2 = {
        "username": "admin2",
        "password": "admin2",
        "auth_level": ["user"],
        "max_age": 600
    }
    
    auth = Authenticator.initialize(base_users=[user1, user2])
    
    user = auth.con.execute("SELECT * FROM users").fetchone()
    assert user == {
        'username': 'admin',
        'password_sha256': 'a2aaf7d5cc93bfd1d1f885bba96dbf2d20d0db3fa00263ea11a50365f50da80e',
        'auth_level': ['super user'],
        'salt': 'uepVxcAiMwyAsRqD',
        'max_age': 600
    }
    
    user = auth.get_user("admin2")
    assert user == {
        'password_sha256': 'ecd42166daa97bce71be6a03ddee4b8602c6a2d24191e9fc76b5961e35aed537', 
        'auth_level': ['user'],
        'salt': 'lRtQxiDXpCNycLap',
        'max_age': 600
    }
    
    user = auth.get_user("admin3")
    assert user is None
    

    user4 = {
        "username": "bbb",
        "password": "aaa",
        "auth_level": ["user"],
        "max_age": 1000
    }
    auth.add_user(user4)
    user = auth.get_user("bbb")
    assert user == {
        'password_sha256': 'f05e44f36fc5a9e48926d9871402fe5d8f9132cba1c6966d7b0a4267c1a1f90e',
        'auth_level': ['user'],
        'salt': 'imtIxXpuQJCBEePL',
        'max_age': 1000
    }
    
    # -- update max_age not updating
    # auth.update_user_max_age("bbb", 10)
    # user = auth.get_user("bbb")
    # print(user)

    
def test_auth(app):
    user1 = {
        "username": "admin",
        "password": "admin",
        "auth_level": ["super user"],
        "max_age": 600
    }

    user2 = {
        "username": "admin2",
        "password": "admin2",
        "auth_level": ["user"],
        "max_age": 0
    }    

    request, response = app.test_client.get("/")
    auth = Authenticator.initialize(base_users=[user1, user2])
    
    
    with pytest.raises(InvalidLogin):
        token = auth.authenticate(request, "admin", "admn")
        token = auth.authenticate(request, "admn", "admin")
    
    token = auth.authenticate(request, "admin2", "admin2")
    request.headers.add("Authorization", f"Bearer {token}")
    time.sleep(1)
    with pytest.raises(OutatedAuthorizationToken):
        auth.authorize(request, "user")
    

    request, response = app.test_client.get("/")
    token = auth.authenticate(request, "admin", "admin") + "a"
    request.headers.add("Authorization", f"Bearer {token}")
    with pytest.raises(InvalidToken):
        auth.authorize(request, "super user")
    
    request, response = app.test_client.get("/")
    token = auth.authenticate(request, "admin", "admin")
    request.headers.add("Authorization", f"Bearer {token}")
    with pytest.raises(AccessDenied):
        auth.authorize(request, "user")
    
    request, response = app.test_client.get("/")
    with pytest.raises(AuthorizationTokenRequired):
        auth.authorize(request, "super user")

    # --
    request, response = app.test_client.get("/")
    token = auth.authenticate(request, "admin", "admin")
    request.headers.add("Authorization", f"Bearer {token}")
    assert auth.authorize(request, "super user") == True
    
    
    app.ctx.authenticator = auth
    request, response = app.test_client.get("/")
    token = auth.authenticate(request, "admin", "admin")
    request.headers.add("Authorization", f"Bearer {token}")
    request, response = app.test_client.get("/bar")
    print(response)
    
    
