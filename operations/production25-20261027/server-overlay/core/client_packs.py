"""Default-off dynamic pack profile; catalog I/O is cached by pinned epoch."""
import hashlib
import json
from pathlib import Path
from threading import RLock

from .config_manager import Config
from .error import NoAccess
from .pack_contract import dynamic_pack_profile_enabled, project_owned_catalog_packs, validated_catalog_pack_ids

_lock = RLock()
_snapshot = None
_MAX_CATALOG_BYTES = 4 * 1024 * 1024


def uses_dynamic_packs(headers):
    return dynamic_pack_profile_enabled(headers.get('AppVersion'), headers.get('Akaine-Packs'),
                                        Config.DYNAMIC_PACKS_ENABLED)


def _catalog_key():
    expected = Config.DYNAMIC_CLIENT_PACKLIST_SHA256
    epoch = Config.DYNAMIC_CLIENT_CATALOG_EPOCH
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in '0123456789abcdef' for c in expected)
            or not isinstance(epoch, str) or not epoch):
        raise ValueError('dynamic catalog pin/epoch is missing')
    return str(Path(Config.DYNAMIC_CLIENT_PACKLIST_PATH).absolute()), expected, epoch


def _read_catalog(key):
    with Path(key[0]).open('rb') as stream:
        raw = stream.read(_MAX_CATALOG_BYTES + 1)
    if len(raw) > _MAX_CATALOG_BYTES or hashlib.sha256(raw).hexdigest() != key[1]:
        raise ValueError('dynamic catalog byte/hash limit failed')
    document = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document, dict) or not isinstance(document.get('packs'), list):
        raise ValueError('dynamic catalog shape is invalid')
    return key, validated_catalog_pack_ids(document['packs'])


def reload_dynamic_pack_catalog():
    """Explicit startup/reload entry; failed reload never replaces good bytes."""
    global _snapshot
    if not Config.DYNAMIC_PACKS_ENABLED:
        return None
    key = _catalog_key()
    candidate = _read_catalog(key)
    with _lock:
        _snapshot = candidate
    return candidate[1]


def dynamic_catalog_pack_ids():
    global _snapshot
    key = _catalog_key()
    with _lock:
        if _snapshot is None or _snapshot[0] != key:
            _snapshot = _read_catalog(key)
        return _snapshot[1]


def pack_ids_for_dynamic_user(user, headers, for_authorization=False):
    """None means legacy. Header never contributes an ownership grant."""
    if not uses_dynamic_packs(headers):
        return None
    try:
        catalog = dynamic_catalog_pack_ids()
        expansions = Config.DYNAMIC_PACK_ENTITLEMENT_EXPANSIONS
        raw_grants = set(user._get_positive_pack_ids()) | set(Config.FREE_PACKS) | {'base'}
        if Config.DYNAMIC_PACKS_FULL_CATALOG is True:
            raw_grants.update(catalog)
        packs = project_owned_catalog_packs(
            catalog, raw_grants, free_pack_ids=[*Config.FREE_PACKS, 'base'],
            hidden_pack_ids=() if for_authorization else Config.DYNAMIC_CLIENT_HIDDEN_PACK_IDS,
            entitlement_expansions=expansions, profile_enabled=True,
            capacity_accepted=Config.DYNAMIC_PACKS_NATIVE_ACCEPTED)
        if for_authorization:
            # Preserve only explicitly declared, actually granted server aliases.
            packs.extend(sorted((set(expansions) & raw_grants) - set(packs)))
        return packs
    except (OSError, ValueError, TypeError, KeyError):
        raise NoAccess('Dynamic pack catalog/policy unavailable.', status=503) from None
