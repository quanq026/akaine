"""Create an offline byte-original delivery ledger; never copy or publish media."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DATA = ROOT / 'data/aurora-library-20261023'
OLD = DATA / 'delivery-hidden-base/DELIVERY_STAGING_CANDIDATE.json'
NORM = DATA / 'AUDIO_NORMALIZATION_RECEIPT.json'
ORIGINALS = HERE.parent / 'AURORA_ORIGINAL_SOURCE_FILES.jsonl'
PREFIX = 'private/candidates/aurora-full-base-20261025-original/songs/'


def load(path):
    return json.loads(path.read_bytes())


def identity(path):
    return os.path.normcase(str(Path(path).resolve()))


HASHES = {}


def hashes(path):
    path = Path(path)
    key = identity(path)
    if key not in HASHES:
        before = path.stat()
        sha, md5 = hashlib.sha256(), hashlib.md5()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                sha.update(block)
                md5.update(block)
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        HASHES[key] = (after.st_size, sha.hexdigest(), md5.hexdigest())
    return HASHES[key]


def write_json(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    old, norm = load(OLD), load(NORM)
    assert old['song_count'] == 1532 and old['object_count'] == len(old['objects']) == 6434
    normalized = {identity(row['output']): row for row in norm['files']}
    originals = [json.loads(line) for line in ORIGINALS.read_text(encoding='utf-8').splitlines()]
    originals = {(row['target_song_id'], row['filename']): row for row in originals
                 if row['role'] in ('remote_audio', 'remote_additional')}
    assert len(originals) == 1574
    metadata = deepcopy(old['song_metadata'])
    rows, changed, seen = [], [], set()
    kinds, original_containers = Counter(), Counter()
    old_bytes, new_bytes, shim_count = 0, 0, 0
    base_audio_unchanged = additional_audio_unchanged = 0
    for number, source_row in enumerate(old['objects'], 1):
        row = deepcopy(source_row)
        target, name = row['target_song_id'], row['file']
        member = (target, name)
        assert member not in seen
        seen.add(member)
        assert row['key'] == f'private/songs/{target}/{name}' and row['private'] is True
        assert row['kind'] in ('chart', 'audio', 'additional')
        old_bytes += row['bytes']
        normalized_row = normalized.get(identity(row['local_file']))
        if normalized_row:
            assert row['kind'] != 'chart'
            assert row['sha256'] == normalized_row['output_sha256']
            assert row['bytes'] == normalized_row['output_bytes']
            size, sha, md5 = hashes(normalized_row['source'])
            assert (size, sha, md5) == (normalized_row['source_bytes'],
                normalized_row['source_sha256'], normalized_row['source_md5'])
            row.update(local_file=normalized_row['source'], source=normalized_row['source'],
                       bytes=size, sha256=sha, source_bytes=size, source_sha256=sha,
                       plaintext_md5=md5, copied=False)
            if normalized_row['source_format'] == 'mp3':
                row['content_type'] = 'audio/mpeg'
            change = {'target_song_id': target, 'file': name,
                      'removed_derivative_action': normalized_row['action'],
                      'old_sha256': source_row['sha256'], 'old_bytes': source_row['bytes'],
                      'original_sha256': sha, 'original_bytes': size,
                      'original_md5': md5, 'original_source': normalized_row['source'],
                      'original_container': normalized_row['source_format']}
            changed.append(change)
            metadata[target]['hashes'][name] = md5
            row['original_container'] = normalized_row['source_format']
            row['original_byte_replacement'] = normalized_row['action']
        else:
            size, sha, md5 = hashes(row['local_file'])
            assert (size, sha) == (row['bytes'], row['sha256'])
            if row['kind'] == 'chart':
                plain_size, plain_sha, plain_md5 = hashes(row['source'])
                assert (plain_size, plain_sha, plain_md5) == (row['source_bytes'],
                    row['source_sha256'], row['plaintext_md5'])
                with Path(row['local_file']).open('rb') as stream:
                    assert stream.read(4) == b'AKFC'
            else:
                assert md5 == row['plaintext_md5']
                if row['kind'] == 'audio':
                    base_audio_unchanged += 1
                elif name.endswith('.ogg'):
                    additional_audio_unchanged += 1
            row['original_byte_replacement'] = None
        if row['kind'] != 'chart':
            original = originals[member]
            assert row['sha256'] == original['sha256']
            assert identity(row['local_file']) == identity(original['source'])
            original_containers[f"{row['kind']}:{original['header']}"] += 1
        assert metadata[target]['hashes'][name] == row['plaintext_md5']
        assert name in metadata[target]['files']
        row.update(active_logical_key=source_row['key'],
                   key=PREFIX + target + '/' + name,
                   canonical_local_file=str(Path(row['local_file']).resolve()),
                   object_md5=md5, private=True, publication_planned_only=True)
        kinds[row['kind']] += 1
        shim_count += row.get('completion_shim') is True
        new_bytes += row['bytes']
        rows.append(row)
        if number % 2000 == 0:
            print(json.dumps({'phase': 'delivery_originals', 'verified': number}), flush=True)
    assert kinds == {'chart': 4860, 'audio': 1532, 'additional': 42} and shim_count == 40
    assert len(changed) == 50
    assert Counter(row['removed_derivative_action'] for row in changed) == {
        'mp3_to_vorbis_q5': 48, 'vorbis_audio_only_remux': 2}
    assert {row['target_song_id'] for row in rows} == set(metadata)
    for target, value in metadata.items():
        members = {row['file'] for row in rows if row['target_song_id'] == target}
        assert set(value['files']) == set(value['hashes']) == members
        assert value['files'] == old['song_metadata'][target]['files']
    differences = [(target, name) for target in metadata for name in metadata[target]['hashes']
                   if metadata[target]['hashes'][name] != old['song_metadata'][target]['hashes'][name]]
    assert set(differences) == {(row['target_song_id'], row['file']) for row in changed}
    selected = {identity(row['local_file']) for row in old['objects']}
    unselected = [{'source_song_id': row['song_id'], 'file': row['resource'],
                   'action': row['action'], 'original_source': row['source'],
                   'original_sha256': row['source_sha256']}
                  for row in norm['files'] if identity(row['output']) not in selected]
    assert len(unselected) == 1 and unselected[0]['source_song_id'] == 'fadb43e7'
    object_path = HERE / 'ORIGINAL_DELIVERY_OBJECTS.jsonl'
    with object_path.open('x', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    meta_path = HERE / 'song_metadata_original_additions.json'
    write_json(meta_path, metadata)
    write_json(HERE / 'ORIGINAL_AUDIO_REPLACEMENTS.json', changed)
    report = {'schema': 'akaine.aurora-original-remote-delivery.v1',
        'status': 'OFFLINE_ORIGINAL_BYTE_DELIVERY_LEDGER_VERIFIED_NOT_PUBLISHED',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Per-song remote downloads retained; fresh private candidate namespace only.',
        'private_candidate_prefix': PREFIX, 'active_object_keys_overwritten': False,
        'songs': len(metadata), 'objects': len(rows), 'object_counts': dict(kinds),
        'real_charts': 4820, 'hidden_completion_shims': shim_count,
        'original_total_object_bytes': old_bytes, 'candidate_total_object_bytes': new_bytes,
        'byte_delta': new_bytes - old_bytes, 'changed_raw_objects': len(changed),
        'replacement_actions': dict(Counter(row['removed_derivative_action'] for row in changed)),
        'changed_base_audio_objects': sum(row['file'] == 'base.ogg' for row in changed),
        'changed_additional_audio_objects': sum(row['file'] != 'base.ogg' for row in changed),
        'unchanged_base_audio_original_identity_verified': base_audio_unchanged,
        'unchanged_additional_ogg_audio_original_identity_verified': additional_audio_unchanged,
        'all_1574_raw_objects_original_source_SHA256_identity_verified': True,
        'all_4860_encrypted_chart_objects_SHA256_and_plaintext_source_MD5_SHA256_verified': True,
        'chart_objects_reencrypted': False, 'chart_membership_changed': False,
        'metadata_files_lists_unchanged': True, 'metadata_hash_entries_changed': len(differences),
        'metadata_chart_hashes_are_plaintext_MD5_not_AKFC_object_MD5': True,
        'original_container_counts': dict(original_containers),
        'unselected_normalization_receipt_rows': unselected,
        'membership_boundary': 'Only1532 accepted imported songs.829 sourceIDs uncovered by exact prod+import union are not invented or added.',
        'compatibility_limits': ['48 original MP3 objects retain their accepted logical filenames, including base.ogg and an override. Container bytes are MP3; no native compatibility claim.',
            'Two selected original Ogg files restore pre-remux bytes; their prior playback/container concerns require a separate compatibility decision.',
            'Original fadb43e7 remux source remains retained but excluded because no accepted real class; it is not silently added.',
            'No upload, live Worker mapping, endpoint metadata, native gameplay or new decrypt test performed.'],
        'outputs': {object_path.name: hashes(object_path)[1], meta_path.name: hashes(meta_path)[1],
                    'ORIGINAL_AUDIO_REPLACEMENTS.json': hashes(HERE / 'ORIGINAL_AUDIO_REPLACEMENTS.json')[1]},
        'inputs': {str(path): hashes(path)[1] for path in (OLD, NORM, ORIGINALS, Path(__file__))},
        'actions': {'media_copied': False, 'media_modified': False, 'resized': False,
                    'reencoded': False, 'decrypted': False, 'keys_accessed': False,
                    'network': False, 'devices': False, 'builds': False}}
    target = HERE / 'ORIGINAL_DELIVERY_RECEIPT.json'
    write_json(target, report)
    print(json.dumps({'status': report['status'], 'report_sha256': hashes(target)[1],
                      'objects': len(rows), 'songs': len(metadata), 'changed': len(changed),
                      'bytes': new_bytes}), flush=True)


if __name__ == '__main__':
    main()
