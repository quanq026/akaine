"""Check a prepared 7.3.1 bundle and local song files before starting the server."""
from pathlib import Path


def check_song_files(root, metadata, *, is_remote):
    root = root.resolve(strict=True)
    available = 0
    missing = []
    for song_id, data in metadata.items():
        if is_remote(song_id):
            continue
        for name in data['files']:
            path = (root / song_id / name).resolve()
            if not path.is_relative_to(root):
                raise ValueError('A song file resolves outside the configured songs directory.')
            if path.is_file() and path.stat().st_size > 0:
                available += 1
            else:
                missing.append(f'{song_id}/{name}')
    if missing:
        sample = ', '.join(missing[:5])
        raise ValueError(f'{len(missing)} local song files missing or empty. First entries: {sample}')
    return available


def main():
    from main import validate_runtime_config
    from core.bundle import BundleParser
    from core.client_packs import dynamic_catalog_pack_ids
    from core.config_manager import Config
    from core.constant import Constant
    from core.download import DownloadList, is_asset_signing_enabled, song_metadata
    from core.error import ArcError

    try:
        if Config.CLIENT_7_3_ENABLED is not True or Config.ALLOW_APPVERSION != ['7.3.1']:
            raise ValueError('Copy and fill config.7.3.1.example.py first.')
        validate_runtime_config()
        BundleParser()
        bundle, = BundleParser.get_bundles('7.3.1', '0.0.0')
        DownloadList.initialize_cache()
        packs = dynamic_catalog_pack_ids('7.3.1')
        files = check_song_files(Path(Constant.SONG_FILE_FOLDER_PATH), song_metadata,
                                 is_remote=is_asset_signing_enabled)
    except (ArcError, OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise SystemExit(f'Content check stopped: {error}') from None
    print(f'7.3.1 content ready: {bundle.version}, {len(packs)} packs, {files} local song files.')


if __name__ == '__main__':
    main()
