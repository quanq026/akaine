import json
import os
import re
from functools import lru_cache
from time import time

from flask import url_for

from .config_manager import Config
from .constant import Constant
from .error import NoAccess, NoData, RateLimit
from .limiter import ArcLimiter


class ContentBundle:

    def __init__(self) -> None:
        self.version: str = None
        self.prev_version: str = None
        self.app_version: str = None
        self.uuid: str = None

        self.json_size: int = None
        self.bundle_size: int = None
        self.json_path: str = None  # relative path
        self.bundle_path: str = None  # relative path
        self.bundle_paths: list[str] = []  # relative paths, one per part

        self.json_url: str = None
        self.bundle_url: str = None
        self.bundle_urls: list[str] = []
        self.bundle_sizes: list[int] = []

    @staticmethod
    def parse_version(version: str) -> tuple:
        try:
            r = tuple(map(int, version.split('.')))
        except AttributeError:
            r = (0, 0, 0)
        return r

    @property
    def version_tuple(self) -> tuple:
        return self.parse_version(self.version)

    @classmethod
    def from_json(cls, json_data: dict) -> 'ContentBundle':
        x = cls()
        x.version = json_data['versionNumber']
        x.prev_version = json_data['previousVersionNumber']
        x.app_version = json_data['applicationVersionNumber']
        x.uuid = json_data['uuid']
        if x.prev_version is None:
            x.prev_version = '0.0.0'
        return x

    def to_dict(self) -> dict:
        r = {
            'contentBundleVersion': self.version,
            'appVersion': self.app_version,
            'jsonSize': self.json_size,
            'bundleSize': self.bundle_size,
        }
        if self.json_url and self.bundle_url:
            r['jsonUrl'] = self.json_url
            r['bundleUrl'] = self.bundle_url
            if len(self.bundle_urls) > 1:
                r['bundleParts'] = [
                    {
                        'url': url,
                        'size': size,
                        'bundleUrl': url,
                        'bundleSize': size,
                    }
                    for url, size in zip(self.bundle_urls, self.bundle_sizes)
                ]
        return r

    def calculate_size(self) -> None:
        self.json_size = os.path.getsize(os.path.join(
            Constant.CONTENT_BUNDLE_FOLDER_PATH, self.json_path))
        paths = self.bundle_paths if self.bundle_paths else [self.bundle_path]
        self.bundle_sizes = [
            os.path.getsize(os.path.join(
                Constant.CONTENT_BUNDLE_FOLDER_PATH, path))
            for path in paths
        ]
        self.bundle_size = sum(self.bundle_sizes)


class BundleParser:

    # {app_version: [ List[ContentBundle] ]}
    bundles: 'dict[str, list[ContentBundle]]' = {}
    # {app_version: max bundle version}
    max_bundle_version: 'dict[str, str]' = {}

    # {bundle version: [next versions]} 宽搜索引
    next_versions: 'dict[str, list[str]]' = {}
    # {(bver, b prev version): ContentBundle} 正向索引
    version_tuple_bundles: 'dict[tuple[str, str], ContentBundle]' = {}
    profile_bundles = {}
    profile_edges = {}
    profile_targets = {}
    profile_anchors = {}

    @staticmethod
    def canonical_profile_version(value):
        return isinstance(value, str) and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}', value) is not None

    def __init__(self) -> None:
        if not self.bundles and not self.profile_bundles:
            self.parse()

    def re_init(self) -> None:
        self.bundles.clear()
        self.max_bundle_version.clear()
        self.next_versions.clear()
        self.version_tuple_bundles.clear()
        self.profile_bundles.clear()
        self.profile_edges.clear()
        self.profile_targets.clear()
        self.profile_anchors.clear()
        self.get_bundles.cache_clear()
        self.parse()

    def parse(self) -> None:
        profiles = self.profile_manifest_specs()
        found_profiles = set()
        for root, dirs, files in os.walk(Constant.CONTENT_BUNDLE_FOLDER_PATH):
            for file in files:
                if not file.endswith('.json'):
                    continue

                json_path = os.path.join(root, file)
                with open(json_path, 'rb') as f:
                    data = json.load(f)

                bundle_paths = []
                total_partitions = data.get('totalPartitions', 1)
                if total_partitions is None:
                    total_partitions = 1
                total_partitions = int(total_partitions)
                if total_partitions > 1:
                    for i in range(total_partitions):
                        bundle_paths.append(
                            os.path.join(root, f'{file[:-5]}_{i}.cb'))
                else:
                    bundle_paths.append(os.path.join(root, f'{file[:-5]}.cb'))

                x = ContentBundle.from_json(data)

                x.json_path = os.path.relpath(
                    json_path, Constant.CONTENT_BUNDLE_FOLDER_PATH)
                x.json_path = x.json_path.replace('\\', '/')
                x.bundle_paths = [
                    os.path.relpath(path, Constant.CONTENT_BUNDLE_FOLDER_PATH).replace('\\', '/')
                    for path in bundle_paths
                ]
                x.bundle_path = x.bundle_paths[0]

                missing = [p for p in bundle_paths if not os.path.isfile(p)]
                if missing and Config.BUNDLE_DOWNLOAD_LINK_PREFIX:
                    # Bundle parts are served from a remote origin (nginx
                    # reverse-proxy to the home PC). The .cb files are not
                    # present on this host, so derive part sizes from the
                    # manifest's `added` entries instead of stat-ing files.
                    x.json_size = os.path.getsize(os.path.join(
                        Constant.CONTENT_BUNDLE_FOLDER_PATH, x.json_path))
                    part_sizes = [0] * len(bundle_paths)
                    for e in data.get('added', []):
                        pi = e.get('partIndex', 0) or 0
                        end = e.get('byteOffset', 0) + e.get('length', 0)
                        if 0 <= pi < len(part_sizes) and end > part_sizes[pi]:
                            part_sizes[pi] = end
                    x.bundle_sizes = part_sizes
                    x.bundle_size = sum(part_sizes)
                elif missing:
                    raise FileNotFoundError(
                        f'Bundle file not found: {missing[0]}')
                else:
                    x.calculate_size()

                if x.json_path in profiles:
                    app, profile, target, anchors = profiles[x.json_path]
                    if x.app_version != app:
                        raise ValueError('Profile manifest application version differs')
                    if (not self.canonical_profile_version(x.version)
                            or data['previousVersionNumber'] is not None
                            and not self.canonical_profile_version(data['previousVersionNumber'])):
                        raise ValueError('Profile manifest version must have four canonical numeric components')
                    key = (app, profile)
                    edge = (*key, x.version, x.prev_version)
                    if edge in self.profile_edges:
                        raise ValueError('Duplicate profile bundle edge')
                    self.profile_edges[edge] = x
                    self.profile_bundles.setdefault(key, []).append(x)
                    self.profile_targets[key] = target
                    self.profile_anchors[key] = anchors
                    found_profiles.add(x.json_path)
                    continue
                self.bundles.setdefault(x.app_version, []).append(x)

                self.version_tuple_bundles[(x.version, x.prev_version)] = x
                self.next_versions.setdefault(
                    x.prev_version, []).append(x.version)

        # sort by version
        for k, v in self.bundles.items():
            v.sort(key=lambda x: x.version_tuple)
            self.max_bundle_version[k] = v[-1].version
        if found_profiles != set(profiles):
            raise ValueError('Configured profile manifest is missing')
        for key, rows in self.profile_bundles.items():
            target = self.profile_targets[key]
            versions = {row.version for row in rows}
            if (*key, target, '0.0.0') not in self.profile_edges:
                raise ValueError('Profile target requires a full root')
            for row in rows:
                previous = row.prev_version
                if (ContentBundle.parse_version(row.version) > ContentBundle.parse_version(target)
                        or previous != '0.0.0' and ContentBundle.parse_version(previous) >= row.version_tuple):
                    raise ValueError('Non-forward or cyclic profile bundle edge')
                if previous != '0.0.0' and previous not in versions and previous not in self.profile_anchors[key]:
                    raise ValueError('Profile bundle dependency is missing')

    @staticmethod
    def profile_manifest_specs():
        specs = {}
        if (getattr(Config, 'BUNDLE_ASSETSET_PROFILES_ENABLED', False)
                and (Config.BUNDLE_STRICT_MODE or getattr(Config, 'FRESH_INSTALL_ONLY_BUNDLE_VERSION', '')
                     or getattr(Config, 'FRESH_INSTALL_DEVICE_BUNDLE_OVERRIDES', {}))):
            raise ValueError('Asset profiles conflict with strict or fresh-install bundle controls')
        devices = getattr(Config, 'BUNDLE_ASSETSET_PROFILE_DEVICES', [])
        if devices is not None and (not isinstance(devices, (list, tuple))
                or any(not isinstance(value, str) or not value or len(value) > 256
                       or any(ord(char) < 32 or ord(char) > 126 for char in value) for value in devices)):
            raise ValueError('Explicit profile device scope must be None or printable device IDs')
        config = getattr(Config, 'BUNDLE_ASSETSET_PROFILES', {})
        if not isinstance(config, dict):
            raise ValueError('Bundle asset profile configuration must be an object')
        for app, profiles in config.items():
            if not isinstance(app, str) or not isinstance(profiles, dict) or 'full' not in profiles:
                raise ValueError('Each configured application requires a full profile')
            full = profiles['full']
            if not isinstance(full, dict):
                raise ValueError('Full profile must be an object')
            full_target = full.get('target')
            if not BundleParser.canonical_profile_version(full_target):
                raise ValueError('Full profile version must have four numeric components')
            for profile, value in profiles.items():
                if profile != 'full' and not re.fullmatch('[0-9a-f]{64}', profile):
                    raise ValueError('Asset profile must name an exact SHA256')
                target = value['target']
                if not BundleParser.canonical_profile_version(target):
                    raise ValueError('Asset profile version must have four numeric components')
                if ContentBundle.parse_version(target) <= (7, 0, 255, 20):
                    raise ValueError('Asset profile target must be newer than full20')
                if profile != 'full' and ContentBundle.parse_version(target) >= ContentBundle.parse_version(full_target):
                    raise ValueError('Full recovery target must be newer than the thin profile')
                anchors = tuple(value.get('migration_from', ()))
                if any(not BundleParser.canonical_profile_version(version)
                       for version in anchors):
                    raise ValueError('Invalid profile migration anchor')
                manifests = value['manifests']
                if not isinstance(manifests, (list, tuple)) or not manifests:
                    raise ValueError('Explicit profile manifest allowlist required')
                for name in manifests:
                    if (not isinstance(name, str) or not name.endswith('.json') or name.startswith('/')
                            or '\\' in name or ':' in name or '..' in name.split('/') or name in specs):
                        raise ValueError('Unsafe or duplicate profile manifest path')
                    specs[name] = (app, profile, target, anchors)
        return specs

    @classmethod
    def get_profile_bundles(cls, app_ver, b_ver, assetset):
        profile = assetset if isinstance(assetset, str) and (app_ver, assetset) in cls.profile_bundles else 'full'
        key = (app_ver, profile)
        target = cls.profile_targets.get(key)
        if target is None:
            raise NoData('Configured bundle profile is unavailable', status=404)
        current = b_ver or '0.0.0'
        if ContentBundle.parse_version(current) >= ContentBundle.parse_version(target):
            return []
        queue = [(current, [])]
        visited = {current}
        for version, path in queue:
            for row in cls.profile_bundles[key]:
                if row.prev_version != version:
                    continue
                next_path = [*path, row]
                if row.version == target:
                    return next_path
                if row.version not in visited:
                    visited.add(row.version)
                    queue.append((row.version, next_path))
        return [cls.profile_edges[(*key, target, '0.0.0')]]

    @staticmethod
    def resolve_compat_app_version(app_ver: str) -> str:
        # Temporary compatibility for Akaine PS 6.15.0 while the live
        # content remains on the current 6.14.11 fan bundle line.
        # Also map 6.14.12 (sideloaded IPA) to 6.14.11 bundle line.
        if app_ver not in BundleParser.bundles:
            if '6.14.11' in BundleParser.bundles and app_ver in ('6.15.0', '6.14.12', '6.14.13', '6.14.14'):
                return '6.14.11'
        return app_ver

    @staticmethod
    @lru_cache(maxsize=128)
    def get_bundles(
            app_ver: str, b_ver: str, device_id: str = None, assetset: str = None
    ) -> 'list[ContentBundle]':
        app_ver = BundleParser.resolve_compat_app_version(app_ver)
        devices = getattr(Config, 'BUNDLE_ASSETSET_PROFILE_DEVICES', [])
        if (getattr(Config, 'BUNDLE_ASSETSET_PROFILES_ENABLED', False)
                and (devices is None or isinstance(device_id, str) and device_id in devices)
                and any(key[0] == app_ver for key in BundleParser.profile_bundles)):
            return BundleParser.get_profile_bundles(app_ver, b_ver, assetset)
        overrides = getattr(
            Config, 'FRESH_INSTALL_DEVICE_BUNDLE_OVERRIDES', {})
        device_bundle_version = (
            overrides.get(device_id, '')
            if isinstance(overrides, dict) and device_id else '')
        fresh_bundle_version = device_bundle_version or getattr(
            Config, 'FRESH_INSTALL_ONLY_BUNDLE_VERSION', '')
        if fresh_bundle_version:
            client_version = b_ver if b_ver else '0.0.0'
            if ContentBundle.parse_version(client_version) != (0, 0, 0):
                return []
            fresh_bundle = BundleParser.version_tuple_bundles.get(
                (fresh_bundle_version, '0.0.0'))
            if fresh_bundle is None:
                raise NoData(
                    f'Fresh-install bundle is unavailable: {fresh_bundle_version}',
                    status=404)
            return [fresh_bundle]
        if Config.BUNDLE_STRICT_MODE:
            return BundleParser.bundles.get(app_ver, [])

        k = b_ver if b_ver else '0.0.0'

        target_version = BundleParser.max_bundle_version.get(app_ver, '0.0.0')
        if ContentBundle.parse_version(k) >= ContentBundle.parse_version(target_version):
            return []

        # BFS
        q = [[k]]
        ans = None
        while True:
            qq = []
            for x in q:
                if x[-1] == target_version:
                    ans = x
                    break
                for y in BundleParser.next_versions.get(x[-1], []):
                    if y in x:
                        continue
                    qq.append(x + [y])

            if ans is not None or not qq:
                break
            q = qq

        if not ans:
            root_bundle = BundleParser.version_tuple_bundles.get((target_version, '0.0.0'))
            if root_bundle and ContentBundle.parse_version(k) < ContentBundle.parse_version(target_version):
                return [root_bundle]
            raise NoData(
                f'No bundles found for app version: {app_ver}, bundle version: {b_ver}', status=404)

        r = []
        for i in range(1, len(ans)):
            r.append(BundleParser.version_tuple_bundles[(ans[i], ans[i-1])])

        return r


class BundleDownload:

    limiter = ArcLimiter(
        Constant.BUNDLE_DOWNLOAD_TIMES_LIMIT, 'bundle_download')

    def __init__(self, c_m=None):
        self.c_m = c_m

        self.client_app_version = None
        self.client_bundle_version = None
        self.device_id = None
        self.assetset = None

    def set_client_info(self, app_version: str, bundle_version: str, device_id: str = None, assetset: str = None) -> None:
        self.client_app_version = app_version
        self.client_bundle_version = bundle_version
        self.device_id = device_id
        self.assetset = assetset if isinstance(assetset, str) and re.fullmatch('[0-9a-f]{64}', assetset) else None

    def get_bundle_list(self) -> list:
        bundles: 'list[ContentBundle]' = BundleParser.get_bundles(
            self.client_app_version, self.client_bundle_version, self.device_id, self.assetset)

        if not bundles:
            return []

        now = time()

        if Constant.BUNDLE_DOWNLOAD_LINK_PREFIX:
            prefix = Constant.BUNDLE_DOWNLOAD_LINK_PREFIX
            if prefix[-1] != '/':
                prefix += '/'

            def url_func(x): return f'{prefix}{x}'
        else:
            def url_func(x): return url_for(
                'bundle_download', token=x, _external=True)

        sql_list = []
        r = []
        for x in bundles:
            if x.version_tuple <= ContentBundle.parse_version(self.client_bundle_version):
                continue
            part_paths = x.bundle_paths if x.bundle_paths else [x.bundle_path]

            if Constant.BUNDLE_DOWNLOAD_LINK_PREFIX:
                x.json_url = url_func(x.json_path)
                x.bundle_urls = [url_func(path) for path in part_paths]
            else:
                t1 = os.urandom(64).hex()

                x.json_url = url_func(t1)
                x.bundle_urls = []

                sql_list.append((t1, x.json_path, now, self.device_id))
                for path in part_paths:
                    t2 = os.urandom(64).hex()
                    x.bundle_urls.append(url_func(t2))
                    sql_list.append((t2, path, now, self.device_id))
            x.bundle_url = x.bundle_urls[0] if x.bundle_urls else None
            bundle_dict = x.to_dict()
            if self.client_app_version == '6.15.0' and bundle_dict.get('appVersion') == '6.14.11':
                bundle_dict['appVersion'] = '6.15.0'
            r.append(bundle_dict)

        if not Constant.BUNDLE_DOWNLOAD_LINK_PREFIX:
            if not sql_list:
                return []

            self.clear_expired_token()

            self.c_m.executemany(
                '''insert into bundle_download_token values (?, ?, ?, ?)''', sql_list)

        return r

    def get_path_by_token(self, token: str, ip: str) -> str:
        r = self.c_m.execute(
            '''select file_path, time, device_id from bundle_download_token where token = ?''', (token,)).fetchone()
        if not r:
            raise NoAccess('Invalid token.', status=403)
        file_path, create_time, device_id = r

        if time() - create_time > Constant.BUNDLE_DOWNLOAD_TIME_GAP_LIMIT:
            raise NoAccess('Expired token.', status=403)

        if file_path.endswith('.cb') and not self.limiter.hit(ip):
            raise RateLimit(
                f'Too many content bundle downloads, IP: {ip}, DeviceID: {device_id}', status=429)

        return file_path

    def clear_expired_token(self) -> None:
        self.c_m.execute(
            '''delete from bundle_download_token where time < ?''', (int(time() - Constant.BUNDLE_DOWNLOAD_TIME_GAP_LIMIT),))
