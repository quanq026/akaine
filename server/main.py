# encoding: utf-8

import os
import time
from importlib import import_module

from core.config_manager import Config, ConfigManager

if os.path.exists('config.py') or os.path.exists('config'):
    # 导入用户自定义配置
    ConfigManager.load(import_module('config').Config)

if Config.DEPLOY_MODE == 'gevent':
    # 异步
    from gevent import monkey
    monkey.patch_all()


import sys
from logging.config import dictConfig
from multiprocessing import Process, set_start_method
from traceback import format_exc

from flask import Flask, make_response, request, send_from_directory

import api
import server
from server import external_v1
import web.index
import web.login
# import webapi
from core.bundle import BundleDownload
from core.constant import Constant
from core.download import UserDownload
from core.error import ArcError, NoAccess, RateLimit
from core.init import FileChecker
from core.sql import Connect
from server.func import error_return

app = Flask(__name__)

if Config.USE_PROXY_FIX:
    # 代理修复
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
if Config.USE_CORS:
    # 服务端跨域
    from flask_cors import CORS
    CORS(app, supports_credentials=True)


os.chdir(sys.path[0])  # 更改工作路径，以便于愉快使用相对路径


app.config.from_mapping(SECRET_KEY=Config.SECRET_KEY)
app.config['SESSION_TYPE'] = 'filesystem'
app.register_blueprint(web.login.bp)
app.register_blueprint(web.index.bp)
app.register_blueprint(api.bp)
list(map(app.register_blueprint, server.get_bps()))
app.register_blueprint(external_v1.create_blueprint())
# app.register_blueprint(webapi.bp)


@app.route('/')
def hello():
    return "Hello World!"


@app.route('/zp/time', methods=['GET'])
def zp_time():
    # Local Aurora compatibility check. This intentionally does not proxy heliosx.
    return str(int(time.time()) + 365 * 24 * 60 * 60)


@app.route('/download/<path:file_path>', methods=['GET'])  # 下载
def download(file_path):
    with Connect(in_memory=True) as c:
        try:
            x = UserDownload(c)
            x.token = request.args.get('t')
            x.song_id, x.file_name = file_path.split('/', 1)
            x.select_for_check()
            if x.is_limited:
                raise RateLimit(
                    f'User `{x.user.user_id}` has reached the download limit.', 903)
            if not x.is_valid:
                raise NoAccess('Expired token.')
            x.download_hit()
            if Config.DOWNLOAD_USE_NGINX_X_ACCEL_REDIRECT:
                # nginx X-Accel-Redirect
                response = make_response()
                response.headers['Content-Type'] = 'application/octet-stream'
                response.headers['X-Accel-Redirect'] = Config.NGINX_X_ACCEL_REDIRECT_PREFIX + file_path
                return response
            return send_from_directory(Constant.SONG_FILE_FOLDER_PATH, file_path, as_attachment=True, conditional=True)
        except ArcError as e:
            if Config.ALLOW_WARNING_LOG:
                app.logger.warning(format_exc())
            return error_return(e)
    return error_return()


@app.route('/bundle_download/<string:token>', methods=['GET'])  # 热更新下载
def bundle_download(token: str):
    with Connect(in_memory=True) as c_m:
        try:
            file_path = BundleDownload(c_m).get_path_by_token(
                token, request.remote_addr)
            if Config.DOWNLOAD_USE_NGINX_X_ACCEL_REDIRECT:
                # nginx X-Accel-Redirect
                response = make_response()
                response.headers['Content-Type'] = 'application/octet-stream'
                response.headers['X-Accel-Redirect'] = Config.BUNDLE_NGINX_X_ACCEL_REDIRECT_PREFIX + file_path
                return response
            return send_from_directory(Constant.CONTENT_BUNDLE_FOLDER_PATH, file_path, as_attachment=True, conditional=True)
        except ArcError as e:
            if Config.ALLOW_WARNING_LOG:
                app.logger.warning(format_exc())
            return error_return(e)
    return error_return()


if Config.DEPLOY_MODE == 'waitress':
    # 给waitress加个日志
    @app.after_request
    def after_request(response):
        app.logger.info(
            f'{request.remote_addr} - - {request.method} {request.path} {response.status_code}')
        return response

# @app.before_request
# def before_request():
#     print(request.path)
#     print(request.headers)
#     print(request.data)


def tcp_server_run():
    if Config.DEPLOY_MODE == 'gevent':
        # 异步 gevent WSGI server
        host_port = (Config.HOST, Config.PORT)
        app.logger.info('Running gevent WSGI server... (%s:%s)' % host_port)
        from gevent.pywsgi import WSGIServer
        WSGIServer(host_port, app, log=app.logger).serve_forever()
    elif Config.DEPLOY_MODE == 'waitress':
        # waitress WSGI server
        import logging
        from waitress import serve  # type: ignore
        logger = logging.getLogger('waitress')
        logger.setLevel(logging.INFO)
        serve(app, host=Config.HOST, port=Config.PORT)
    else:
        if Config.SSL_CERT and Config.SSL_KEY:
            app.run(Config.HOST, Config.PORT, ssl_context=(
                Config.SSL_CERT, Config.SSL_KEY))
        else:
            app.run(Config.HOST, Config.PORT)


def generate_log_file_dict(level: str, filename: str) -> dict:
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "maxBytes": 1024 * 1024,
        "backupCount": 1,
        "encoding": "utf-8",
        "level": level,
        "formatter": "default",
        "filename": filename
    }


def validate_runtime_config():
    required = {
        'USERNAME': Config.USERNAME,
        'PASSWORD': Config.PASSWORD,
        'SECRET_KEY': Config.SECRET_KEY,
    }
    if Config.LINKPLAY_HOST and Config.SET_LINKPLAY_SERVER_AS_SUB_PROCESS:
        required.update({
            'LINKPLAY_AUTHENTICATION': Config.LINKPLAY_AUTHENTICATION,
            'LINKPLAY_TCP_SECRET_KEY': Config.LINKPLAY_TCP_SECRET_KEY,
        })
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            'Refusing to start with missing security settings: '
            + ', '.join(missing)
        )

    if Config.CLIENT_7_3_ENABLED is True:
        import re
        from urllib.parse import urlsplit

        def https_prefix(value):
            if not isinstance(value, str) or any(c.isspace() for c in value):
                return False
            try:
                url = urlsplit(value)
                return bool(url.scheme == 'https' and url.hostname and url.username is None
                            and not url.query and not url.fragment)
            except ValueError:
                return False

        if (Config.HOST not in ('127.0.0.1', '::1')
                or Config.ALLOW_APPVERSION != ['7.3.1']
                or Config.SET_LINKPLAY_SERVER_AS_SUB_PROCESS or Config.LINKPLAY_HOST
                or Config.INSECURE_LOCAL_OAUTH_COMPAT_ENABLED
                or Config.ALLOW_SCORE_WITH_NO_SONG or not Config.DOWNLOAD_FORBID_WHEN_NO_ITEM):
            raise RuntimeError('The 7.3.1 profile requires the standalone server policy')
        target = Config.FRESH_INSTALL_APP_BUNDLE_OVERRIDES.get('7.3.1', '')
        if (not re.fullmatch(r'7\.3\.1\.[1-9][0-9]{0,8}', target)
                or not re.fullmatch(r'[0-9a-f]{64}', Config.BUNDLE_MANIFEST_7_3_SHA256)
                or not all(isinstance(pin, str) and re.fullmatch(r'[0-9a-f]{64}', pin) for pin in
                           (Config.SONGLIST_7_3_SHA256, Config.SONG_METADATA_7_3_SHA256))
                or Config.DYNAMIC_PACKS_ENABLED is not True
                or Config.DYNAMIC_PACKS_7_3_NATIVE_ACCEPTED is not True
                or not https_prefix(Config.DOWNLOAD_LINK_PREFIX_7_3_1)):
            raise RuntimeError('The 7.3.1 profile requires reviewed bundle, song and native pack inputs')
        bundle_prefix = Config.BUNDLE_DOWNLOAD_LINK_PREFIX_APP_OVERRIDES.get('7.3.1', '')
        if bundle_prefix and not https_prefix(bundle_prefix):
            raise RuntimeError('The 7.3.1 bundle prefix must use HTTPS')

def main():
    validate_runtime_config()

    log_dict = {
        'version': 1,
        'root': {
            'level': 'INFO',
            'handlers': ['wsgi', 'error_file']
        },
        'handlers': {
            'wsgi': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://flask.logging.wsgi_errors_stream',
                'formatter': 'default'
            },
            "error_file": generate_log_file_dict('ERROR', './log/error.log')
        },
        'formatters': {
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
            }
        }
    }
    if Config.ALLOW_INFO_LOG:
        log_dict['root']['handlers'].append('info_file')
        log_dict['handlers']['info_file'] = generate_log_file_dict(
            'INFO', './log/info.log')
    if Config.ALLOW_WARNING_LOG:
        log_dict['root']['handlers'].append('warning_file')
        log_dict['handlers']['warning_file'] = generate_log_file_dict(
            'WARNING', './log/warning.log')

    dictConfig(log_dict)

    Connect.logger = app.logger
    if not FileChecker(app.logger).check_before_run():
        app.logger.error('Some errors occurred. The server will not run.')
        input('Press ENTER key to exit.')
        sys.exit()

    if Config.LINKPLAY_HOST and Config.SET_LINKPLAY_SERVER_AS_SUB_PROCESS:
        from linkplay_server import link_play
        process = [Process(target=link_play, args=(
            Config.LINKPLAY_HOST, int(Config.LINKPLAY_UDP_PORT), int(Config.LINKPLAY_TCP_PORT)))]
        [p.start() for p in process]
        app.logger.info(
            f"Link Play UDP server is running on {Config.LINKPLAY_HOST}:{Config.LINKPLAY_UDP_PORT} ...")
        app.logger.info(
            f"Link Play TCP server is running on {Config.LINKPLAY_HOST}:{Config.LINKPLAY_TCP_PORT} ...")
        tcp_server_run()
        [p.join() for p in process]
    else:
        tcp_server_run()


if __name__ == '__main__':
    set_start_method("spawn")
    main()


# Made By Lost  2020.9.11
