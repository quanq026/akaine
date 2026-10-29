"""Read-only queries over hash-verified content already installed in the game."""
import base64
import hashlib
import json
import re
import unicodedata

CLASSES = {'pst': 0, 'prs': 1, 'ftr': 2, 'byd': 3, 'etr': 4}
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
LEVEL = re.compile(r'(?:[0-9]|1[0-2])\+?\Z')
FILES = {'meta': ('files/cb/meta.cb', 8 * 1024 * 1024),
         'songs': ('files/cb/active/songs/songlist', 8 * 1024 * 1024),
         'packs': ('files/cb/active/songs/packlist', 1024 * 1024)}


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold()


def text_values(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in text_values(child)]
    if isinstance(value, list):
        return [text for child in value for text in text_values(child)]
    return []


def read_file(adb, deadline, key):
    path, limit = FILES[key]
    # Control/status uses shell v2. Raw file bytes use exec-out without a shell,
    # avoiding the trailing newline introduced by this device's shell channel.
    parents = path.split('/')[:-1]
    checks = ['test -d ' + '/'.join(parents[:n]) + ' && test ! -L ' + '/'.join(parents[:n])
              for n in range(1, len(parents) + 1)]
    adb.shell(' && '.join(checks + [f'test -f {path}', f'test ! -L {path}']), deadline)
    data = adb.call(['exec-out', 'run-as', 'akai.arc.lmao', 'head', '-c', str(limit + 1), path], deadline.remaining()).stdout
    if not data or len(data) > limit:
        raise ValueError('Catalogue file is missing or exceeds its size limit.')
    return data


def load(adb, deadline):
    raw_meta = read_file(adb, deadline, 'meta')
    meta = json.loads(raw_meta)
    if (not isinstance(meta, dict) or meta.get('applicationVersionNumber') != '7.0.255' or
            not isinstance(meta.get('versionNumber'), str) or
            not re.fullmatch(r'7\.0\.255\.[0-9]+', meta['versionNumber']) or
            not isinstance(meta.get('pathToHash'), dict)):
        raise ValueError('The installed catalogue manifest is not a supported 7.0.255 bundle.')
    hashes, objects = {}, {}
    for key, asset in (('songs', 'songs/songlist'), ('packs', 'songs/packlist')):
        raw = read_file(adb, deadline, key)
        expected = meta['pathToHash'].get(asset)
        if not isinstance(expected, str) or len(expected) != 44:
            raise ValueError('Catalogue hash is missing from the active manifest.')
        digest = hashlib.sha256(raw).digest()
        if base64.b64encode(digest).decode('ascii') != expected:
            raise ValueError('Catalogue bytes do not match the active manifest; wait for the bundle transaction.')
        hashes[asset] = digest.hex()
        objects[key] = json.loads(raw.decode('utf-8-sig'))
    if read_file(adb, deadline, 'meta') != raw_meta:
        raise ValueError('The active content manifest changed during the query.')
    if not all(isinstance(value, dict) for value in objects.values()):
        raise ValueError('Invalid catalogue document shape.')
    songs, packs = objects['songs'].get('songs'), objects['packs'].get('packs')
    if not isinstance(songs, list) or not isinstance(packs, list) or len(songs) > 20000 or len(packs) > 1000:
        raise ValueError('Invalid catalogue collection size.')
    for rows in (songs, packs):
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or
                    not ID.fullmatch(row['id']) or row['id'] in seen):
                raise ValueError('Invalid or duplicate catalogue identifier.')
            seen.add(row['id'])
    return {'version': meta['versionNumber'], 'hashes': hashes, 'songs': songs, 'packs': packs}


def charts(song):
    rows = song.get('difficulties', [])
    if not isinstance(rows, list) or len(rows) > 5:
        raise ValueError('Invalid difficulty collection.')
    result = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get('ratingClass')) is not int or row['ratingClass'] not in CLASSES.values():
            raise ValueError('Invalid chart difficulty.')
        rating = row.get('rating')
        if type(rating) is not int or not -3 <= rating <= 12:
            raise ValueError('Invalid chart level.')
        result.append({'difficulty': next(name for name, number in CLASSES.items() if number == row['ratingClass']),
                       'rating_class': row['ratingClass'], 'level': str(rating) + ('+' if row.get('ratingPlus') is True else ''),
                       'hidden': row.get('hidden') is True})
    return result


def song_row(song, available_charts):
    titles = song.get('title_localized', {})
    return {'id': song['id'], 'titles': titles if isinstance(titles, dict) else {},
            'artist': song.get('artist'), 'pack': song.get('set'), 'bpm': song.get('bpm'),
            'side': song.get('side'), 'difficulties': available_charts}


def query(catalogue, kind, options):
    if kind not in ('songs', 'packs'):
        raise ValueError('Unknown catalogue query.')
    options = dict(options or {})
    limit, offset = options.get('limit', 30), options.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 20000:
        raise ValueError('Use a limit of 1–100 and a nonnegative offset up to 20000.')
    difficulty, level, side = options.get('difficulty'), options.get('level'), options.get('side')
    if difficulty is not None and difficulty not in CLASSES:
        raise ValueError('Unknown difficulty; use pst, prs, ftr, byd or etr.')
    if level is not None and (not isinstance(level, str) or not LEVEL.fullmatch(level)):
        raise ValueError('Use a displayed level such as 9, 9+ or 10+.')
    if side is not None and side not in (0, 1, 2):
        raise ValueError('Unknown song side.')
    pack = options.get('pack')
    if pack is not None and pack not in {row['id'] for row in catalogue['packs']}:
        raise ValueError('The requested pack is absent from the active catalogue.')
    term = options.get('query', '')
    if not isinstance(term, str) or len(term) > 256 or any(ord(ch) < 32 for ch in term):
        raise ValueError('Search text must be at most 256 printable characters.')
    term = normalized(term.strip())
    rows = []
    if kind == 'packs':
        for row in catalogue['packs']:
            titles = row.get('name_localized', {})
            if term and not any(term in normalized(text) for text in [row['id'], *text_values(titles)]):
                continue
            rows.append({'id': row['id'], 'titles': titles, 'section': row.get('section'),
                         'song_count': sum(song.get('set') == row['id'] for song in catalogue['songs'])})
    else:
        selected = options.get('id')
        if selected is not None and (not isinstance(selected, str) or not ID.fullmatch(selected)):
            raise ValueError('Invalid song identifier.')
        for row in catalogue['songs']:
            if selected is not None and row['id'] != selected:
                continue
            if pack is not None and row.get('set') != pack:
                continue
            if side is not None and row.get('side') != side:
                continue
            search = [row['id'], *text_values(row.get('title_localized')), *text_values(row.get('artist')),
                      *text_values(row.get('search_title')), *text_values(row.get('search_artist'))]
            if term and not any(term in normalized(text) for text in search):
                continue
            available = [chart for chart in charts(row) if (difficulty is None or chart['difficulty'] == difficulty)
                         and (level is None or chart['level'] == level)]
            if not available:
                continue
            rows.append(song_row(row, available))
        if selected is not None and not rows:
            raise ValueError('The requested song is absent from the active catalogue.')
    if options.get('sort', 'id') not in ('id', 'title'):
        raise ValueError('Sort must be id or title.')
    rows.sort(key=lambda row: normalized(row['id'] if options.get('sort', 'id') == 'id'
                                        else row['titles'].get('en', row['id'])))
    return {'ok': True, 'command': 'pack list' if kind == 'packs' else 'song catalogue',
            'catalogue_version': catalogue['version'], 'verified_hashes': catalogue['hashes'],
            'selection_changed': False, 'ownership_verified': False,
            'total': len(rows), 'offset': offset, 'limit': limit, 'results': rows[offset:offset + limit]}
