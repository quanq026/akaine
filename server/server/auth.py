import base64
import hashlib
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from core.config_manager import Config
from core.error import ArcError, NoAccess
from core.sql import Connect
from core.user import UserAuth, UserLogin, UserRegister

from .func import arc_try, error_return, header_check

bp = Blueprint('auth', __name__, url_prefix='/auth')

def _ensure_local_oauth_user(c) -> None:
    if not Config.INSECURE_LOCAL_OAUTH_COMPAT_ENABLED:
        raise NoAccess('Local OAuth compatibility is disabled.', 104)
    if not all((Config.LOCAL_OAUTH_NAME, Config.LOCAL_OAUTH_PASSWORD,
                Config.LOCAL_OAUTH_EMAIL)):
        raise NoAccess('Local OAuth compatibility is not configured.', 104)
    c.execute('''select user_id from user where name = :name''',
              {'name': Config.LOCAL_OAUTH_NAME})
    row = c.fetchone()
    if row is None:
        user = UserRegister(c)
        user.set_name(Config.LOCAL_OAUTH_NAME)
        user.set_password(Config.LOCAL_OAUTH_PASSWORD)
        user.set_email(Config.LOCAL_OAUTH_EMAIL)
        user.register('localps-oauth', '127.0.0.1')
        user_id = user.user_id
    else:
        user_id = row[0]

    password_hash = hashlib.sha256(
        Config.LOCAL_OAUTH_PASSWORD.encode('utf8')).hexdigest()
    c.execute('''update user set password = :password, ticket = :ticket
                 where user_id = :user_id''',
              {'password': password_hash, 'ticket': Config.LOCAL_OAUTH_ITEMS, 'user_id': user_id})
    c.execute('''insert or replace into user_item(user_id, item_id, type, amount)
                 values(:user_id, 'fragment', 'fragment', :amount)''',
              {'user_id': user_id, 'amount': Config.LOCAL_OAUTH_ITEMS})
    c.execute('''insert or replace into user_item(user_id, item_id, type, amount)
                 values(:user_id, 'pick_ticket', 'pick_ticket', :amount)''',
              {'user_id': user_id, 'amount': Config.LOCAL_OAUTH_ITEMS})
    c.execute('''insert or replace into user_item(user_id, item_id, type, amount)
                 select :user_id, item_id, type, 1 from item
                 where type in ('pack', 'single', 'world_song') and is_available = 1''',
              {'user_id': user_id})


@bp.route('/login', methods=['POST'])  # 登录接口
@arc_try
def login():
    headers = request.headers
    e = header_check(request)
    if e is not None:
        raise e

    request.form['grant_type']
    with Connect() as c:
        id_pwd = headers['Authorization']
        id_pwd = base64.b64decode(id_pwd[6:]).decode()
        name, password = id_pwd.split(':', 1)
        if 'DeviceId' in headers:
            device_id = headers['DeviceId']
        else:
            device_id = 'low_version'

        user = UserLogin(c)
        user.login(name, password, device_id, request.remote_addr)
        current_app.logger.info(f'User `{user.user_id}` log in')
        return jsonify({"success": True, "token_type": "Bearer", 'user_id': user.user_id, 'access_token': user.token})


@bp.route('/login/oauth/google', methods=['POST'])
@arc_try
def login_oauth_google():
    if not Config.INSECURE_LOCAL_OAUTH_COMPAT_ENABLED:
        raise NoAccess('Local OAuth compatibility is disabled.', 104)
    if not request.form.get('access_token'):
        raise NoAccess('Missing OAuth access token.', 104)

    device_id = request.headers.get(
        'DeviceId') or request.form.get('device_id') or 'localps-oauth'
    with Connect() as c:
        _ensure_local_oauth_user(c)

        user = UserLogin(c)
        user.login(Config.LOCAL_OAUTH_NAME, Config.LOCAL_OAUTH_PASSWORD,
                   device_id, request.remote_addr)
        current_app.logger.info(
            f'Local OAuth user `{user.user_id}` logged in via google')
        return jsonify({"success": True, "token_type": "Bearer", 'user_id': user.user_id, 'access_token': user.token})


def auth_required(req):
    # arcaea登录验证，写成了修饰器
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):

            headers = req.headers

            e = header_check(req)
            if e is not None:
                current_app.logger.warning(
                    f' - {e.error_code}|{e.api_error_code}: {e}')
                return error_return(e)

            with Connect() as c:
                try:
                    user = UserAuth(c)
                    token = headers.get('Authorization')
                    if not token:
                        raise NoAccess('No token.', -4)
                    user.token = token[7:]
                    user_id = user.token_get_id()
                    g.user = user
                except ArcError as e:
                    return error_return(e)
            return view(user_id, *args, **kwargs)

        return wrapped_view
    return decorator
