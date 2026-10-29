"""Pure data-literal patching for the captured protected-assets Worker."""
from copy import deepcopy
import json
import re


MARKER = 'var RELEASE1002_ASSET_MANIFEST = '
SONG = re.compile(r'aurora_[A-Za-z0-9_-]{1,120}\Z', re.ASCII)
FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z', re.ASCII)


def unique_pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError('duplicate_manifest_key')
        value[key] = item
    return value


def split(source: str) -> tuple[str, dict, str]:
    if source.count(MARKER) != 1:
        raise ValueError('unexpected_static_manifest_assignment')
    start = source.index(MARKER) + len(MARKER)
    value, length = json.JSONDecoder(object_pairs_hook=unique_pairs).raw_decode(source[start:])
    if not isinstance(value, dict) or not source[start + length:].startswith(';'):
        raise ValueError('unexpected_manifest_shape_or_terminator')
    return source[:start], value, source[start + length:]


def validate_additions(additions: dict) -> None:
    if not isinstance(additions, dict) or not additions:
        raise ValueError('empty_additions')
    for identity, files in additions.items():
        if not SONG.fullmatch(identity) or not isinstance(files, list) or not files:
            raise ValueError('invalid_new_song_or_files')
        if (len(files) != len(set(files)) or 'base.ogg' not in files
                or any(not isinstance(name, str) or not FILE.fullmatch(name) for name in files)):
            raise ValueError('invalid_or_duplicate_filename')
        if any(name.endswith('.aff') and name not in {'0.aff', '1.aff', '2.aff', '3.aff', '4.aff'} for name in files):
            raise ValueError('unsupported_new_chart_filename')


def patch(source: str, additions: dict) -> tuple[str, dict]:
    validate_additions(additions)
    prefix, baseline, suffix = split(source)
    if set(baseline) & set(additions):
        raise ValueError('new_song_collision')
    merged = deepcopy(baseline)
    merged.update(deepcopy(additions))
    candidate = prefix + json.dumps(merged, separators=(',', ':'), ensure_ascii=True) + suffix
    new_prefix, parsed, new_suffix = split(candidate)
    assert prefix == new_prefix and suffix == new_suffix
    assert {key: value for key, value in parsed.items() if key not in additions} == baseline
    return candidate, {'added_ids': sorted(additions), 'before_song_count': len(baseline), 'after_song_count': len(parsed)}


def rollback(source: str, additions: dict, added_ids: list[str]) -> str:
    validate_additions(additions)
    if set(added_ids) != set(additions) or len(added_ids) != len(set(added_ids)):
        raise ValueError('rollback_ownership_mismatch')
    prefix, current, suffix = split(source)
    if any(current.get(identity) != additions[identity] for identity in added_ids):
        raise ValueError('rollback_owned_entry_changed')
    remaining = {key: value for key, value in current.items() if key not in added_ids}
    return prefix + json.dumps(remaining, separators=(',', ':'), ensure_ascii=True) + suffix
