"""Add a signed staging route for original audio without changing existing routes."""
import hashlib
import json
import re

BASELINE_SHA256 = '54748325983a7c1bfc7e1b3486446a2d279f4782f68ce54218aff3ebed9f7402'
PREFIX = '/protected/songs/original25/'
STORAGE = 'private/candidates/aurora-full-base-20261025-original/songs/'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def patch(source: bytes, replacements: list[dict]) -> bytes:
    require(hashlib.sha256(source).hexdigest() == BASELINE_SHA256, 'Worker baseline changed')
    keys = {}
    for row in replacements:
        identity = row['target_song_id'] + '/' + row['file']
        require(re.fullmatch(r'aurora_[A-Za-z0-9_-]{1,120}', row['target_song_id']), 'Invalid song ID')
        require(row['file'] in ('base.ogg', '3.ogg', '4.ogg'), 'Invalid audio filename')
        require(row['key'] == STORAGE + identity, 'Storage key mismatch')
        require(identity not in keys, 'Duplicate audio identity')
        keys[identity] = row['key']
    require(len(keys) == 50, 'Expected exactly 50 original audio keys')
    marker = b'var encoder = new TextEncoder();'
    require(source.count(marker) == 1, 'Worker encoder marker changed')
    candidate = source.replace(marker, b'var ORIGINAL25_AUDIO_KEYS = ' + json.dumps(keys, sort_keys=True, separators=(',', ':')).encode() + b';\n' + marker)
    old = b'  const prefix = pathname.startsWith("/protected/songs/")'
    new = b'  const prefix = pathname.startsWith("' + PREFIX.encode() + b'") ? "' + PREFIX.encode() + b'" : pathname.startsWith("/protected/songs/")'
    require(source.count(old) == 1, 'Worker path parser changed')
    candidate = candidate.replace(old, new)
    old = b'    const key = `private/songs/${verified.songId}/${verified.fileName}`;'
    new = (b'    const identity = `${verified.songId}/${verified.fileName}`;\n'
           b'    const key = url.pathname.startsWith("' + PREFIX.encode() + b'") && Object.hasOwn(ORIGINAL25_AUDIO_KEYS, identity)\n'
           b'      ? ORIGINAL25_AUDIO_KEYS[identity] : `private/songs/${verified.songId}/${verified.fileName}`;')
    require(candidate.count(old) == 1, 'Worker storage selector changed')
    return candidate.replace(old, new)
