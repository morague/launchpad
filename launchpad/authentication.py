from __future__ import annotations


import jwt
import time
import json
import random
from string import ascii_letters
from attrs import define, field, validators
from pathlib import Path

from sanic import Request

from sqlite3 import Cursor, Row, PARSE_DECLTYPES
from sqlite3 import connect, register_adapter, register_converter

from hashlib import sha256
from functools import wraps
from sanic.request import Request

from typing import Any, Literal, get_args

from launchpad.exceptions import (
    OutatedAuthorizationToken, 
    AuthorizationTokenRequired, 
    InvalidToken, 
    MissingLogin, 
    InvalidLogin, 
    AccessDenied
)

AuthLevels = Literal["user","super user"]
JwtToken = str
Payload = dict[str, Any]

def protected(auth_level: str):
    def decorator(f):
        @wraps(f)
        async def wrapped(request: Request, *args, **kwargs):
            authenticator: Authenticator = request.app.ctx.authenticator
            
            if authenticator is None:
                response = await f(request, *args, **kwargs)
                return response        
            
            elif authenticator.authorize(request, auth_level):    
                response = await f(request, *args, **kwargs)
                return response  
                  
            else:
                raise AccessDenied()
        return wrapped
    return decorator

def serialize(data: dict | list) -> str:
    return json.dumps(data)

def deserialize(data: str) -> dict | list:
    return json.loads(data)

class _Db(object):
    def __init__(self, db: str | Path = ":memory:") -> None:
        self.con = connect(db, detect_types=PARSE_DECLTYPES)
        self.cursor = self.con.cursor()
        self.con.row_factory = self._row_factory
        self._user_table()     
        register_adapter(list, serialize)
        register_converter("JSONLIST", deserialize)   

    def get_user(self, username: str) -> Payload | None:
        return self.con.execute("SELECT password_sha256, auth_level, salt, max_age FROM users WHERE username=?;", [username]).fetchone()
    
    def _user_table(self) -> None:
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users
            (
                username TEXT PRIMARY KEY,
                password_sha256 TEXT,
                auth_level JSONLIST,
                salt TEXT,
                max_age INTEGER
            );
            """
        )
        self.con.commit()
    
    def _insert_user(self, username: str, password_sha256: str, authlevel: list[str], salt: str, max_age: int) -> None:
        self.cursor.execute(
            "INSERT INTO users(username, password_sha256, auth_level, salt, max_age) VALUES (?, ?, ?, ?, ?)",
            [username, password_sha256, authlevel, salt, max_age]
            )
        self.con.commit()
    
    def _insert_users(self, users: list[list[Any]])  -> None:
        self.cursor.executemany(
            "INSERT INTO users(username, password_sha256, auth_level, salt, max_age) VALUES (?, ?, ?, ?, ?)",
            users
            )
        self.con.commit()
        
    def _update_max_age(self, username: str, max_age: int) -> None:
        self.cursor.execute("UPDATE users SET max_age = ? WHERE username = ?;", [username, max_age])
        self.con.commit()
    
    @staticmethod
    def _row_factory(cursor: Cursor, row: Row) -> Payload:
        fields = [column[0] for column in cursor.description]
        return {key: value for key, value in zip(fields, row)}

class Authenticator(_Db):
    def __init__(self, db: str | Path = ":memory:") -> None:
        super().__init__(db)
    
    @classmethod
    def initialize(cls, base_users: list[Payload] | None = None, db: str | Path = ":memory:") -> Authenticator:
        authenticator = cls(db)
        if base_users is not None:
            authenticator.add_users(base_users)
        return authenticator
    
    def authenticate(self, request: Request, username: str, password: str) -> JwtToken:
        user = self.get_user(username)
        if user is None:
            raise InvalidLogin()
        print("user", user)
        max_age = user.get("max_age")
        auth_level = user.get("auth_level")
        salted_password= user["salt"] + password
        password_sha256 = sha256(salted_password.encode()).hexdigest()

        if password_sha256 != user["password_sha256"]:
            raise InvalidLogin()
        
        return jwt.encode({"auth_level": auth_level, "max_age": self._max_time_age(max_age)}, request.app.config.SECRET)

        
    def authorize(self, request: Request, auth_level: str) -> bool:
        token = request.token        
        if not token:
            raise AuthorizationTokenRequired()

        try:
            payload = jwt.decode(
                token, request.app.config.SECRET, algorithms=["HS256"]
            )
        except jwt.exceptions.InvalidTokenError:
            raise InvalidToken()
        
        if auth_level not in payload["auth_level"]:
            raise AccessDenied()
        
        if int(time.time()) > payload["max_age"]:
            raise OutatedAuthorizationToken()
        
        return True

    def add_user(self, user: Payload) -> None:
        parsed_user = User(**user)
        self._insert_user(*parsed_user.to_sql())
        
    def add_users(self, users: list[Payload]) -> None:
        parsed_users = [User(**user).to_sql() for user in users]
        self._insert_users(parsed_users)
    
    def update_user_max_age(self, username: str, max_age: int) -> None:
        self._update_max_age(username, max_age)
    
    def _max_time_age(self, max_age: int) -> int:
        return int(time.time()) + max_age


@define(slots=True, kw_only=True)
class User:
    username: str = field(validator=[validators.instance_of(str)])
    password: str = field(validator=[validators.instance_of(str)])
    password_sha256: str = field(init=False)
    auth_level: str = field()
    salt: str = field(init=False)
    max_age: int = field(validator=[validators.instance_of(int)])
    
    def __attrs_post_init__(self):
        self.generate_salt()
        self.generate_sha256()
        
    @auth_level.validator
    def validate_auth_level(self, attribute, value):
        if not isinstance(value, list):
            raise TypeError("auth_level must be of type list")
        if not all([a in get_args(AuthLevels) for a in value]):
            raise ValueError("auth_levels elements must be in ['user', 'super user']")
            
    def generate_salt(self):
        self.salt =  "".join([random.choice(ascii_letters) for _ in range(16)])
        
    def generate_sha256(self):
        salted_password = self.salt + self.password
        self.password_sha256 = sha256(salted_password.encode()).hexdigest()
        
    def to_sql(self):
        return [self.username, self.password_sha256, self.auth_level, self.salt, self.max_age]



