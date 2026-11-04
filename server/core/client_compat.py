"""Exact client contracts; 7.1 requires explicit server configuration."""
from .config_manager import Config
from .error import LowVersion, NoAccess


def uses_current_contract(app_version):
    if app_version == '7.1.0':
        # Native wire/score/cloud acceptance must precede production enablement.
        if Config.CLIENT_7_1_ENABLED is not True:
            raise LowVersion('The 7.1 client profile is disabled.', 5)
        return True
    return app_version == '7.0.255'


def character_visible_for_app_version(character_id, app_version):
    current = uses_current_contract(app_version)
    if character_id in (100, 101):
        return app_version == '7.1.0'
    return current or character_id not in (97, 98)


def character_row_for_app_version(row, app_version):
    if 'character' not in row or character_visible_for_app_version(row['character'], app_version):
        return row
    projected = dict(row, character=0)
    for field in ('is_char_uncapped', 'is_char_uncapped_override'):
        if field in projected:
            projected[field] = False
    return projected


def song_download_prefix(app_version, legacy_prefix):
    current = uses_current_contract(app_version)
    if app_version == '7.1.0':
        prefix = Config.DOWNLOAD_LINK_PREFIX_7_1_0
        if not isinstance(prefix, str) or not prefix:
            raise NoAccess('The 7.1 song route is not configured.', status=503)
        return prefix
    return Config.DOWNLOAD_LINK_PREFIX_7_0_255 if current else legacy_prefix
