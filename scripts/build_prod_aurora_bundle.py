"""Offline original-quality full base: authentic prod18 plus reviewed Aurora files."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat

import build_content_bundle as bundle
import build_release_profile as release

SCHEMA = 'akaine.prod-aurora-bundle-recipe.v1'
BASELINE_SHA = '804965179bbca3a7dbad8bc0424b568a9d5136b334ba2309164947e20396c53f'
UNION_SONGLIST_SHA = '2f2e22de7ff4eb6794a608e33848844ae177045107321e7c31b6846ebfc2963f'
UNION_SONGLIST_AUTH = 'Y417SCY/cqCOHh0Zh7j2GuPXYkjmbTeFzcVjBS2q8Xw='
MAX_PART = 480 * 1024 * 1024
ACTIVATION_GATES = ('17_lossless_WAV_preview_native_compatibility',
                    '48_original_MP3_native_download_compatibility', 'aggregate_size_over_4GiB_native_and_API_proof')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return bundle.sha256_file(Path(path))


def recipe_digest(recipe):
    value = {key: data for key, data in recipe.items() if key != 'review'}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe_path(name):
    require(isinstance(name, str) and bundle.valid_bundle_path(name)
            and PurePosixPath(name).as_posix() == name and name not in ('.', '..')
            and ':' not in name and all(ord(char) >= 32 for char in name), 'Unsafe bundle path')


def file_identity(path):
    path = Path(path)
    row = path.stat()
    require(stat.S_ISREG(row.st_mode) and not path.is_symlink(), 'Ordinary immutable input file required')
    return row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns


def verified_file(row):
    path = Path(row['file'])
    identity = file_identity(path)
    require(type(row['bytes']) is int and row['bytes'] >= 0 and identity[2] == row['bytes']
            and digest(path) == row['sha256'], 'Input file size or SHA256 differs')
    return path, identity


class SourceParts:
    def __init__(self, parts):
        self.parts = parts

    def __truediv__(self, name):
        match = re.fullmatch(r'source_([0-9]+)[.]cb', name)
        require(match is not None and int(match[1]) in self.parts, 'Unknown source partition')
        return self.parts[int(match[1])]


def partition(specs):
    result, part, offset = [], 0, 0
    require(bool(specs), 'Nonempty full-root path set required')
    for row in specs:
        size = row['bytes']
        require(type(size) is int and 0 <= size <= MAX_PART, 'Payload exceeds partition bound')
        if offset and offset + size > MAX_PART:
            part, offset = part + 1, 0
        result.append({'path': row['path'], 'partIndex': part, 'byteOffset': offset, 'length': size,
                       'sha256HashBase64Encoded': base64.b64encode(bytes.fromhex(row['sha256'])).decode()})
        offset += size
    return result, part + 1


def prepare(recipe):
    require(recipe.get('schema') == SCHEMA, 'Explicit prod18/Aurora recipe required')
    version, alias = recipe['version'], recipe['alias']
    match = re.fullmatch(r'7[.]0[.]255[.]([0-9]+)', version)
    require(match is not None and int(match[1]) > 24, 'Fresh numeric content version above24 required')
    require(isinstance(alias, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', alias)
            and '..' not in alias, 'Safe fresh bundle alias required')
    binding = recipe['review']; review_file = Path(binding['file'])
    require(digest(review_file) == binding['sha256'], 'Independent recipe review digest differs')
    review = json.loads(review_file.read_bytes())
    require(review.get('status') == 'PASS_PROD_AURORA_BUNDLE_RECIPE_REVIEW' and review.get('findings') == []
            and review.get('builder_sha256') == digest(Path(__file__))
            and review.get('payload_helper_sha256') == digest(Path(bundle.__file__))
            and review.get('output_guard_sha256') == digest(Path(release.__file__))
            and review.get('recipe_sha256') == recipe_digest(recipe), 'Exact independent source/recipe review required')
    baseline = recipe['baseline']; manifest_file = Path(baseline['manifest']['file'])
    require(baseline['manifest']['sha256'] == BASELINE_SHA and digest(manifest_file) == BASELINE_SHA,
            'Authentic production18 manifest required')
    manifest = json.loads(manifest_file.read_bytes())
    require(manifest['versionNumber'] == '7.0.255.18' and manifest['applicationVersionNumber'] == '7.0.255'
            and manifest['previousVersionNumber'] is None and not manifest['removed']
            and manifest['totalPartitions'] == 7, 'Production18 complete seven-part root required')
    tracked = {review_file: file_identity(review_file), manifest_file: file_identity(manifest_file),
               Path(__file__): file_identity(Path(__file__)), Path(bundle.__file__): file_identity(Path(bundle.__file__))}
    tracked[Path(release.__file__)] = file_identity(Path(release.__file__))
    parts = {}
    for row in baseline['parts']:
        index = row['partIndex']
        require(type(index) is int and index not in parts, 'Duplicate or invalid source partition')
        path, identity = verified_file(row); parts[index] = path; tracked[path] = identity
    require(set(parts) == set(range(manifest['totalPartitions'])), 'Missing or extra production source partition')
    source = SourceParts(parts)
    bundle.validate_source(source, manifest)
    old = {row['path']: row for row in manifest['added']}
    require(set(old) == set(manifest['pathToHash']), 'Production baseline path inventory differs')
    seen = {name.casefold() for name in old}
    require(len(seen) == len(old), 'Case-ambiguous baseline paths')
    specs = [{'path': name, 'bytes': row['length'], 'sha256': base64.b64decode(row['sha256HashBase64Encoded']).hex(),
              'file': None, 'group': 'preserved_prod18'} for name, row in old.items()]
    by_path = {row['path']: row for row in specs}
    details = deepcopy(manifest['pathToDetails']); overlay_files = {}
    overlays = recipe['overlays']
    require(len(overlays) == 1 and overlays[0]['path'] == 'songs/songlist', 'Only reviewed union songlist may replace production bytes')
    overlay = overlays[0]
    require(overlay['sha256'] == UNION_SONGLIST_SHA and overlay['detail_auth'] == UNION_SONGLIST_AUTH,
            'Exact reviewed union catalog bytes/authentication required')
    path, identity = verified_file(overlay); tracked[path] = identity
    overlay_files['songs/songlist'] = path
    previous = json.loads(bundle.read_span(source, old['songs/songlist']).decode('utf-8-sig'))
    union = json.loads(path.read_bytes().decode('utf-8-sig'))
    require({k: v for k, v in previous.items() if k != 'songs'} == {k: v for k, v in union.items() if k != 'songs'}
            and union['songs'][:len(previous['songs'])] == previous['songs'], 'Existing production song entries or catalog metadata changed')
    added_songs = union['songs'][len(previous['songs']):]
    require(bool(added_songs) and all(song['id'].startswith('aurora_') and song.get('remote_dl') is True for song in added_songs),
            'Aurora catalog additions must retain per-song remote download')
    by_path['songs/songlist'].update(bytes=overlay['bytes'], sha256=overlay['sha256'], file=path, group='reviewed_catalog_union')
    details['songs/songlist'] = overlay['detail_auth']
    for row in recipe['additions']:
        name, kind = row['path'], row['kind']; safe_path(name)
        require(name.casefold() not in seen, 'Aurora addition collides with an existing path')
        require(kind in ('aurora_original', 'aurora_dependency', 'lossless_preview'), 'Unknown Aurora addition kind')
        if kind != 'aurora_dependency':
            require(name.startswith(('songs/aurora_', 'songs/dl_aurora_')), 'Non-Aurora media path')
        if kind in ('aurora_original', 'aurora_dependency'):
            require(row['original_sha256'] == row['sha256'], 'Original bytes must not be converted')
        else:
            require(row.get('lossless_PCM_verified') is True, 'Explicit reviewed lossless preview proof required')
        path, identity = verified_file(row); tracked[path] = identity
        seen.add(name.casefold())
        specs.append({'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'], 'file': path, 'group': kind})
    bundle.validate_catalog(source, old, overlay_files)
    rows, count = partition(specs)
    return manifest, source, old, specs, rows, count, details, tracked


def build(recipe, output):
    output = Path(output)
    manifest, source, old, specs, rows, count, details, tracked = prepare(recipe)
    disk = release.physical_output(output)
    require(all(not path.resolve().is_relative_to(output.resolve()) for path in tracked), 'Output overlaps immutable input')
    parent = next(path for path in output.parents if path.exists())
    require(shutil.disk_usage(parent).free > sum(row['bytes'] for row in specs) + 128 * 1024 * 1024,
            'Insufficient space for complete offline base')
    output.mkdir(parents=True)
    alias = recipe['alias']
    streams = [(output / f'{alias}_{index}.cb').open('xb') for index in range(count)]
    try:
        for spec, row in zip(specs, rows):
            expected = old.get(spec['path'], {'path': spec['path']})
            actual = hashlib.sha256()
            size = bundle.copy_payload(source, expected, spec['file'], streams[row['partIndex']], actual)
            require(size == spec['bytes'] and actual.hexdigest() == spec['sha256'], 'Copied payload differs from reviewed original/source')
    finally:
        for stream in streams:
            stream.close()
    candidate = deepcopy(manifest)
    candidate.update(versionNumber=recipe['version'], previousVersionNumber=None, removed=[], totalPartitions=count,
                     added=rows, pathToHash={row['path']: row['sha256HashBase64Encoded'] for row in rows},
                     pathToDetails=details, uuid=recipe_digest(recipe)[:8], generatedUnixTimestamp=manifest['generatedUnixTimestamp'])
    require(set(old) <= set(candidate['pathToHash']) and len(rows) == len(old) + len(recipe['additions']), 'A production baseline path was omitted')
    require(all(candidate['pathToHash'][name] == manifest['pathToHash'][name] for name in old if name != 'songs/songlist'),
            'Unapproved existing production bytes changed')
    target = output / f'{alias}.json'
    target.write_text(json.dumps(candidate, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    verified = bundle.verify_output(output, alias, candidate)
    require(tracked == {path: file_identity(path) for path in tracked}, 'Frozen source, original or review input changed during build')
    result = {'status': 'OFFLINE_PROD18_AURORA_FULL_BASE_VERIFIED_ACTIVATION_BLOCKED', 'version': recipe['version'],
              'alias': alias, 'previousVersionNumber': None, 'APK_omissions': 0, 'baseline_manifest_sha256': BASELINE_SHA,
              'baseline_paths': len(old), 'preserved_baseline_paths': len(old) - 1, 'catalog_union_overlays': ['songs/songlist'],
              'added_paths': len(recipe['additions']), 'entries': verified['entries'], 'parts': verified['parts'],
              'manifest': {'file': target.name, 'bytes': target.stat().st_size, 'sha256': digest(target)},
              'CB_payload_bytes': sum(row['bytes'] for row in specs), 'total_bytes': target.stat().st_size + sum(row['bytes'] for row in specs),
              'all_original_media_copied_without_reencoding_resizing_or_upscaling': True,
              'all_baseline_part_and_span_hashes_and_output_span_hashes_verified': True,
              'catalog_detail_auth_digests_reused_exactly_no_keys_read': True,
              'per_song_remote_download_mechanism_unchanged': True, 'recipe_sha256': recipe_digest(recipe),
              'review_sha256': recipe['review']['sha256'], 'builder_sha256': digest(Path(__file__)),
              'activation_blocked': True, 'activation_pending': list(ACTIVATION_GATES),
              'source_modified': False, 'device_network_server_or_production_actions': False, 'external_disk': disk}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
    return result
