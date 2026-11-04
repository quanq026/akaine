"""Copy to config.py, fill private settings and bind your prepared 7.1 content."""


class Config:
    HOST = '127.0.0.1'
    PORT = 18080
    USE_PROXY_FIX = True
    GAME_API_PREFIX = '/'
    ALLOW_APPVERSION = ['7.1.0']
    CLIENT_7_1_ENABLED = True

    BUNDLE_STRICT_MODE = False
    BUNDLE_DOWNLOAD_LINK_PREFIX = 'https://assets.example.com/bundle/'
    BUNDLE_ASSETSET_PROFILES_ENABLED = True
    BUNDLE_ASSETSET_PROFILE_DEVICES = None
    BUNDLE_ASSETSET_PROFILES = {
        '7.1.0': {'full': {'target': '7.1.0.1', 'manifests': ['7.1.0-full.json']}}
    }
    DOWNLOAD_LINK_PREFIX_7_1_0 = 'https://assets.example.com/songs/'

    DYNAMIC_PACKS_ENABLED = True
    DYNAMIC_PACKS_FULL_CATALOG = True
    DYNAMIC_PACKS_7_1_NATIVE_ACCEPTED = True
    DYNAMIC_CLIENT_7_1_PACKLIST_PATH = './database/client_catalogs/7.1.0/packlist'
    DYNAMIC_CLIENT_7_1_PACKLIST_SHA256 = '<SHA256_OF_YOUR_7_1_PACKLIST>'
    DYNAMIC_CLIENT_7_1_CATALOG_EPOCH = '7.1.0.1:full'

    SET_LINKPLAY_SERVER_AS_SUB_PROCESS = False
    LINKPLAY_HOST = ''
    ASSET_SIGNING_ENABLED = True
    ASSET_SIGNED_PREFIX = 'https://assets.example.com/protected/songs/'
    ASSET_SIGNING_PROTECT_ALL_SONGS = False
    ASSET_SIGNING_SONG_IDS = []

    USERNAME = ''
    PASSWORD = ''
    SECRET_KEY = ''
