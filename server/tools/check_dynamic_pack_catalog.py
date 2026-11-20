"""Validate one configured dynamic catalog epoch; never edits DB or server files.

Run from the server root after loading the same private operator configuration.
The serving worker reloads through DownloadList.initialize_cache after its usual
clear/initialize operation; this separate checker does not mutate another process.
"""
from importlib import import_module
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_manager import Config, ConfigManager
from core.client_packs import reload_dynamic_pack_catalog


if __name__ == '__main__':
    if Path('config.py').is_file() or Path('config').is_dir():
        ConfigManager.load(import_module('config').Config)
    if not Config.DYNAMIC_PACKS_ENABLED:
        raise SystemExit('Dynamic pack profile is disabled; no catalog loaded.')
    if Config.CLIENT_7_3_ENABLED is not True:
        raise SystemExit('Enable the 7.3.1 profile before checking its packlist.')
    ids = reload_dynamic_pack_catalog('7.3.1')
    print('7.3.1 packlist validated: %d IDs.' % len(ids))
