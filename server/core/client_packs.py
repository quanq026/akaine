"""Default-off dynamic pack profile; catalog I/O is cached by pinned epoch."""
import hashlib
import json
from pathlib import Path
from threading import RLock

from .config_manager import Config
from .client_compat import uses_current_contract
from .error import NoAccess
from .pack_contract import dynamic_pack_profile_enabled, project_owned_catalog_packs, validated_catalog_pack_ids

_lock = RLock()
_snapshots = {}
_MAX_CATALOG_BYTES = 4 * 1024 * 1024


def uses_dynamic_packs(headers):
    app_version = headers.get('AppVersion')
    uses_current_contract(app_version)
    if app_version == '7.1.0' and (Config.DYNAMIC_PACKS_ENABLED is not True
                                  or headers.get('Akaine-Packs') != 'dynamic1'):
        raise NoAccess('The 7.1 native pack capability is required.', status=503)
    return dynamic_pack_profile_enabled(headers.get('AppVersion'), headers.get('Akaine-Packs'),
                                        Config.DYNAMIC_PACKS_ENABLED)


def _catalog_key(app_version):
    if app_version == '7.1.0':
        uses_current_contract(app_version)
        path = Config.DYNAMIC_CLIENT_7_1_PACKLIST_PATH
        expected = Config.DYNAMIC_CLIENT_7_1_PACKLIST_SHA256
        epoch = Config.DYNAMIC_CLIENT_7_1_CATALOG_EPOCH
    elif app_version == '7.0.255':
        path = Config.DYNAMIC_CLIENT_PACKLIST_PATH
        expected = Config.DYNAMIC_CLIENT_PACKLIST_SHA256
        epoch = Config.DYNAMIC_CLIENT_CATALOG_EPOCH
    else:
        raise ValueError('Unsupported dynamic catalog client')
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in '0123456789abcdef' for c in expected)
            or not isinstance(epoch, str) or not epoch
            or app_version == '7.1.0' and not path):
        raise ValueError('dynamic catalog pin/epoch is missing')
    return str(Path(path).absolute()), expected, epoch


def _read_catalog(key):
    with Path(key[0]).open('rb') as stream:
        raw = stream.read(_MAX_CATALOG_BYTES + 1)
    if len(raw) > _MAX_CATALOG_BYTES or hashlib.sha256(raw).hexdigest() != key[1]:
        raise ValueError('dynamic catalog byte/hash limit failed')
    document = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document, dict) or not isinstance(document.get('packs'), list):
        raise ValueError('dynamic catalog shape is invalid')
    return key, validated_catalog_pack_ids(document['packs'])


def reload_dynamic_pack_catalog(app_version=None):
    """Reload pinned client catalogs; a failed catalog never replaces its snapshot."""
    if not Config.DYNAMIC_PACKS_ENABLED:
        return None
    if app_version is None:
        versions = ['7.0.255']
        if Config.CLIENT_7_1_ENABLED is True:
            versions.append('7.1.0')
            if Config.ALLOW_APPVERSION:
                versions = [version for version in versions if version in Config.ALLOW_APPVERSION]
        catalogs = [reload_dynamic_pack_catalog(version) for version in versions]
        return catalogs[0] if catalogs else None
    key = _catalog_key(app_version)
    candidate = _read_catalog(key)
    with _lock:
        _snapshots[app_version] = candidate
    return candidate[1]


def dynamic_catalog_pack_ids(app_version='7.0.255'):
    key = _catalog_key(app_version)
    with _lock:
        snapshot = _snapshots.get(app_version)
        if snapshot is None or snapshot[0] != key:
            snapshot = _read_catalog(key)
            _snapshots[app_version] = snapshot
        return snapshot[1]


def pack_ids_for_dynamic_user(user, headers, for_authorization=False):
    """None means legacy. Header never contributes an ownership grant."""
    if not uses_dynamic_packs(headers):
        return None
    try:
        app_version = headers.get('AppVersion')
        catalog = dynamic_catalog_pack_ids(app_version)
        expansions = Config.DYNAMIC_PACK_ENTITLEMENT_EXPANSIONS
        raw_grants = set(user._get_positive_pack_ids()) | set(Config.FREE_PACKS) | {'base'}
        if Config.DYNAMIC_PACKS_FULL_CATALOG is True:
            raw_grants.update(catalog)
        packs = project_owned_catalog_packs(
            catalog, raw_grants, free_pack_ids=[*Config.FREE_PACKS, 'base'],
            hidden_pack_ids=() if for_authorization else Config.DYNAMIC_CLIENT_HIDDEN_PACK_IDS,
            entitlement_expansions=expansions, profile_enabled=True,
            capacity_accepted=(Config.DYNAMIC_PACKS_7_1_NATIVE_ACCEPTED
                               if app_version == '7.1.0' else Config.DYNAMIC_PACKS_NATIVE_ACCEPTED))
        if for_authorization:
            # Preserve only explicitly declared, actually granted server aliases.
            packs.extend(sorted((set(expansions) & raw_grants) - set(packs)))
        return packs
    except (OSError, ValueError, TypeError, KeyError):
        raise NoAccess('Dynamic pack catalog/policy unavailable.', status=503) from None
