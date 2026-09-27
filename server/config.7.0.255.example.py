"""Copy to config.py inside server/ and fill private values before starting."""


class Config:
    HOST = '127.0.0.1'
    PORT = 18080
    USE_PROXY_FIX = True
    GAME_API_PREFIX = '/'
    ALLOW_APPVERSION = ['7.0.255']
    BUNDLE_STRICT_MODE = False
    FRESH_INSTALL_ONLY_BUNDLE_VERSION = ''
    BUNDLE_DOWNLOAD_LINK_PREFIX = 'https://assets.example.com/bundle/'
    DOWNLOAD_LINK_PREFIX_7_0_255 = 'https://assets.example.com/songs/'

    SET_LINKPLAY_SERVER_AS_SUB_PROCESS = False
    LINKPLAY_HOST = ''

    ASSET_SIGNING_ENABLED = True
    ASSET_SIGNED_PREFIX = 'https://assets.example.com/protected/songs/'
    ASSET_SIGNING_PROTECT_ALL_SONGS = False
    ASSET_SIGNING_SONG_IDS = []

    USERNAME = ''
    PASSWORD = ''
    SECRET_KEY = ''
