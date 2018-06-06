from flask import session, request, abort, redirect
from functools import wraps
import time


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.method == 'POST' :
            if not is_authenticated():
                abort(401)
            else:
                return func(*args, **kwargs)
        else:
            if not is_authenticated():
                return redirect("/login/" + "?next=" + request.path)
            else:
                return func(*args, **kwargs)
    return wrapper

def is_authenticated(validtime = 3600):
    if "username" in session and "login-time" in session:
        login_time = session['login-time']
        if time.time()-login_time <= 3600:
            return True
    return False

