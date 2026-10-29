"""Read-only native-chart intake gate; keeps existing catalog/metadata formats."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

ID = re.compile(r'[a-z0-9_]{1,64}\Z')
EVENT = re.compile(r'(?:([A-Za-z_][A-Za-z0-9_]*)\s*)?\(')
KNOWN = {'timing': 3, 'hold': 3, 'arc': 10, 'arctap': 1, 'camera': 9, 'scenecontrol': None, 'timinggroup': None, 'tap': 2}
ALLOWED_FILES = re.compile(r'(?:[0-4]\.aff|base\.ogg|preview\.ogg|(?:1080_)?base(?:_256)?\.(?:jpg|jpeg|png))\Z')


def file_limit(name):
    return 512 * 1024**2 if name.endswith('.ogg') else 32 * 1024**2


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_aff(raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('AFF is not UTF8 plaintext') from error
    header, separator, body = text.partition('\n-')
    if not separator or not re.search(r'^AudioOffset:-?[0-9]+\s*$', header, re.M):
        raise ValueError('AFF AudioOffset/body separator missing')
    unsupported, counts = set(), Counter()
    position, groups, playable_notes = 0, [], 0
    while position < len(body):
        if body[position].isspace(): position += 1; continue
        if body.startswith('};', position):
            if not groups: raise ValueError('AFF closes an absent timinggroup')
            groups.pop(); position += 2; continue
        match = EVENT.match(body, position)
        if not match: raise ValueError('AFF contains malformed or non-event input')
        name = match[1] or 'tap'
        if name == 'arctap': raise ValueError('Arctap must be attached to an arc')
        end = body.find(')', match.end())
        if end < 0 or '(' in body[match.end():end]: raise ValueError('AFF event parentheses malformed')
        arguments = [value.strip() for value in body[match.end():end].split(',')]
        if arguments == ['']: arguments = []
        position = end + 1
        while position < len(body) and body[position].isspace(): position += 1
        counts[name] += 1
        if name not in KNOWN: unsupported.add('event:' + name)
        elif KNOWN[name] is not None and len(arguments) != KNOWN[name]:
            raise ValueError('AFF event argument count differs: ' + name)
        if name == 'timinggroup':
            if position >= len(body) or body[position] != '{': raise ValueError('timinggroup body missing')
            if arguments and arguments != ['noinput']: unsupported.add('timinggroup-options')
            groups.append(bool(groups and groups[-1]) or 'noinput' in arguments)
            position += 1; continue
        if name == 'scenecontrol': unsupported.add('scenecontrol-consumer-proof-required')
        if name == 'arc' and len(arguments) == 10:
            if arguments[8] != 'none': unsupported.add('custom-arc-sample')
            if arguments[9] not in ('true', 'false'): raise ValueError('Arc trace flag malformed')
            if arguments[4] not in ('s', 'b', 'si', 'so', 'sisi', 'siso', 'sosi', 'soso'):
                unsupported.add('arc-curve:' + arguments[4])
        numeric = {'tap': (0, 1), 'timing': (0, 1, 2), 'hold': (0, 1, 2),
                   'arc': (0, 1, 2, 3, 5, 6, 7), 'arctap': (0,), 'camera': (0, 1, 2, 3, 4, 5, 6, 8)}
        for index in numeric.get(name, ()):
            try: value = float(arguments[index])
            except (ValueError, IndexError) as error: raise ValueError('AFF numeric argument malformed') from error
            if not math.isfinite(value): raise ValueError('AFF nonfinite numeric argument')
        attached_arctaps = 0
        if name == 'arc' and position < len(body) and body[position] == '[':
            close = body.find(']', position)
            if close < 0: raise ValueError('Arctap list missing closing bracket')
            inner = body[position + 1:close].strip()
            if inner and not re.fullmatch(r'arctap\(-?[0-9]+\)(?:\s*,\s*arctap\(-?[0-9]+\))*', inner):
                raise ValueError('Arc child event is not a native arctap list')
            attached_arctaps = inner.count('arctap(')
            counts['arctap'] += attached_arctaps
            position = close + 1
        while position < len(body) and body[position].isspace(): position += 1
        if position >= len(body) or body[position] != ';': raise ValueError('AFF event semicolon missing')
        position += 1
        if not groups or not groups[-1]:
            playable_notes += int(name in ('tap', 'hold'))
            if name == 'arc': playable_notes += int(arguments[9] == 'false') + attached_arctaps
    if groups: raise ValueError('AFF timinggroup is unclosed')
    if not playable_notes: raise ValueError('AFF contains no playable note events outside noinput groups')
    return {'events': dict(sorted(counts.items())), 'playable_note_events': playable_notes, 'unsupported': sorted(unsupported),
            'status': 'quarantine' if unsupported else 'native-grammar-subset-validated'}


def safe_name(name):
    path = PurePosixPath(name)
    return bool(path.parts) and path.as_posix() == name and not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name


def source_files(source):
    if source.is_symlink() or getattr(source.lstat(), 'st_file_attributes', 0) & 1024:
        raise ValueError('Native intake source cannot be a link/reparse point')
    source = source.resolve()
    initial = source.stat()
    files = {}
    if source.is_file() and source.suffix.lower() == '.zip':
        if initial.st_size > 1024**3: raise ValueError('Native ZIP exceeds bounded input size')
        with zipfile.ZipFile(source) as archive:
            if len(archive.infolist()) > 512 or sum(item.file_size for item in archive.infolist()) > 1024**3:
                raise ValueError('Native ZIP exceeds bounded intake size')
            names = set()
            for item in archive.infolist():
                if item.is_dir(): continue
                name = item.filename
                if not safe_name(name) or '/' in name or name.casefold() in names or stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Unsafe/duplicate native ZIP member; use one flat song folder')
                names.add(name.casefold())
                if not ALLOWED_FILES.fullmatch(name):
                    files[name] = None
                    continue
                if item.file_size > file_limit(name):
                    raise ValueError('Native source file exceeds size bound')
                files[name] = archive.read(item)
        with source.open('rb') as stream: archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        if (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns) != (
                source.stat().st_dev, source.stat().st_ino, source.stat().st_size, source.stat().st_mtime_ns):
            raise ValueError('ZIP changed during read-only intake')
        origin = {'kind': 'zip', 'sha256': archive_sha}
    elif source.is_dir():
        paths = sorted(source.iterdir())
        if len(paths) > 512 or sum(path.lstat().st_size for path in paths) > 1024**3:
            raise ValueError('Native folder exceeds bounded intake size')
        for path in paths:
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 1024 or not path.is_file():
                raise ValueError('Native intake requires a flat regular-file folder')
            if path.name.casefold() in {name.casefold() for name in files}: raise ValueError('Casefold duplicate source file')
            if not ALLOWED_FILES.fullmatch(path.name): files[path.name] = None; continue
            limit = file_limit(path.name)
            before = path.stat()
            if before.st_size > limit:
                raise ValueError('Native source file exceeds size bound')
            with path.open('rb') as stream: files[path.name] = stream.read(limit + 1)
            after = path.stat()
            if (len(files[path.name]) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise ValueError('Source file changed during read-only intake')
        if [path.name for path in sorted(source.iterdir())] != [path.name for path in paths]:
            raise ValueError('Source folder membership changed during intake')
        origin = {'kind': 'folder'}
    else: raise ValueError('Native source must be a song folder or ZIP')
    return files, origin


def write_report(path, source, result):
    if source.is_dir() and path.resolve().is_relative_to(source.resolve()):
        raise ValueError('Report must remain outside the immutable source folder')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def chart_constants(value, song_id, classes):
    rows = value if isinstance(value, list) else [value] if value is not None else []
    selected = [row for row in rows if row.get('song_id') == song_id]
    if len(selected) > 1: raise ValueError('Duplicate constants song identity')
    constants = {index: -1 for index in classes}
    if selected:
        seen = set()
        for row in selected[0].get('charts', []):
            index, constant = row['difficulty'], row['chart_const']
            if type(index) is not int or index not in range(5) or type(constant) not in (int, float) or not math.isfinite(constant):
                raise ValueError('Existing Song.to_dict constant format invalid')
            if index in seen: raise ValueError('Duplicate constants difficulty')
            seen.add(index)
            if index not in classes and constant > 0: raise ValueError('Positive constant has no real playable source chart')
            if index in classes: constants[index] = constant if constant > 0 else -1
    return constants


def validate(source, song_id, songlist_path, packlist_path, metadata_path, constants_path, catalog_validator):
    if not ID.fullmatch(song_id): raise ValueError('Invalid stable native song ID')
    references = dict(songlist=songlist_path, packlist=packlist_path, metadata=metadata_path)
    if constants_path: references['constants'] = constants_path
    snapshots = {name: path.read_bytes() for name, path in references.items()}
    catalog_validator.validate_catalog(Path('.'), {}, {'songs/songlist': songlist_path, 'songs/packlist': packlist_path})
    songs = json.loads(snapshots['songlist'])['songs']
    song = next((row for row in songs if row['id'] == song_id), None)
    if song is None: raise ValueError('Song is absent from prepared songlist')
    metadata = json.loads(snapshots['metadata']).get(song_id)
    if metadata is None: raise ValueError('Song is absent from prepared DownloadList metadata')
    if not isinstance(metadata, dict) or not isinstance(metadata.get('files'), list) or not isinstance(metadata.get('hashes'), dict):
        raise ValueError('Existing DownloadList files/hashes format invalid')
    files, origin = source_files(source)
    if files.get('base.ogg', b'')[:4] != b'OggS': raise ValueError('Native OGG source missing or invalid signature')
    jackets = [name for name in files if re.fullmatch(r'(?:1080_)?base(?:_256)?\.(?:jpg|jpeg|png)', name)]
    if not jackets: raise ValueError('Native jacket dependency is missing')
    classes, charts, unsupported = set(), [], {name for name, raw in files.items() if raw is None}
    for name, raw in sorted(files.items()):
        if not re.fullmatch(r'[0-4]\.aff', name): continue
        index = int(name[0]); classes.add(index)
        result = native_aff(raw)
        charts.append({'difficulty': index, 'file': name, 'sha256': sha(raw), **result})
        unsupported.update(result['unsupported'])
    if not classes: raise ValueError('No canonical native AFF file')
    if len(metadata.get('files', [])) != len(set(metadata.get('files', []))): raise ValueError('Duplicate metadata file')
    for name in metadata['files']:
        if name not in files or files[name] is None: raise ValueError('DownloadList dependency missing from native payload')
        if hashlib.md5(files[name]).hexdigest() != metadata['hashes'].get(name): raise ValueError('DownloadList plaintext MD5 differs')
    difficulties = {row['ratingClass']: row for row in song.get('difficulties', [])}
    if len(difficulties) != len(song.get('difficulties', [])): raise ValueError('Duplicate ratingClass')
    if any(type(index) is not int or index not in range(5) for index in difficulties): raise ValueError('Invalid ratingClass')
    for row in difficulties.values():
        for flag in ('audioOverride', 'jacketOverride'):
            if row.get(flag): unsupported.add('unsupported-difficulty-' + flag)
    exposed = {index for index, row in difficulties.items() if row.get('rating', 0) > 0 and row.get('hidden_until') != 'always'}
    if not exposed or not exposed <= classes: raise ValueError('Visible playable class lacks a real source AFF')
    if not {'base.ogg', *(str(index) + '.aff' for index in exposed)} <= set(metadata['files']):
        raise ValueError('DownloadList omits a visible playable source dependency')
    if 3 in exposed and difficulties[3].get('world_unlock') is not False: raise ValueError('Native BYD difficulty must explicitly set world_unlock=false')
    constants = chart_constants(json.loads(snapshots['constants']) if constants_path else None, song_id, exposed)
    rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items()) if raw is not None]
    origin['supported_file_set_sha256'] = sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode())
    origin['quarantined_uninspected_files'] = sorted(name for name, raw in files.items() if raw is None)
    if any(path.read_bytes() != snapshots[name] for name, path in references.items()):
        raise ValueError('Input catalog/metadata/constants changed during intake')
    return {'status': 'QUARANTINED_NOT_PLAYABLE' if unsupported else 'VALIDATED_NATIVE_INTAKE_NOT_GAMEPLAY_ACCEPTED',
            'song_id': song_id, 'source': origin, 'files': rows, 'charts': charts, 'quarantine_reasons': sorted(unsupported),
            'chart_constants': constants, 'ranked_classes': [] if unsupported else [index for index in sorted(constants) if constants[index] > 0],
            'blocked_ranked_classes': [index for index in sorted(constants) if constants[index] > 0] if unsupported else [],
            'unranked_classes': [index for index in sorted(constants) if constants[index] <= 0],
            'constants_inferred_from_level': False, 'catalog_song_count': len(songs),
            'catalog_pack_count': len(json.loads(snapshots['packlist'])['packs']), 'fixed_pack_limit_applied': False,
            'input_refs': {label: {'sha256': sha(raw)} for label, raw in snapshots.items()},
            'audio_check_scope': 'OGG signature and DownloadList hash only; ffprobe/decode and game audio remain required.',
            'image_check_scope': 'Required jacket dependency only; image decode/dimensions/alpha remain required.',
            'source_modified': False, 'build_encrypt_publish_or_server_actions': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('validate', 'dry-run'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--song-id', required=True)
    parser.add_argument('--songlist', type=Path, required=True)
    parser.add_argument('--packlist', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--constants', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    import build_content_bundle
    result = validate(args.source, args.song_id, args.songlist, args.packlist, args.metadata, args.constants, build_content_bundle)
    if args.report:
        write_report(args.report, args.source, result)
    print(json.dumps({'status': result['status'], 'song_id': result['song_id'], 'ranked_classes': result['ranked_classes'],
                      'quarantine_reasons': result['quarantine_reasons']}, ensure_ascii=False))
    raise SystemExit(2 if result['status'] == 'QUARANTINED_NOT_PLAYABLE' else 0)
