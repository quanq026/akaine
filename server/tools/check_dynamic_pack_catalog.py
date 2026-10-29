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
    ids = reload_dynamic_pack_catalog()
    print('Dynamic pack catalog validated: %d IDs; no DB/server files modified.' % len(ids))
