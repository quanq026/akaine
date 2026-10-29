"""Guarded production-only runtime. Imported locally for pure offline fixtures."""
import ast
import base64
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time
from urllib.request import Request, urlopen

ROOT = Path('/home/ec2-user/arcaea-server')
STAGE = Path('/home/ec2-user/arcaea-server-test')
ALIAS = '7.0.255-prod-original-base25-20261027'
MANIFEST_SHA = '6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891'
CONTENT_TYPES = ('pack', 'single', 'character', 'course_banner', 'world_song', 'world_unlock')
CONFIG_KEYS = frozenset(('DYNAMIC_PACKS_ENABLED', 'DYNAMIC_PACKS_NATIVE_ACCEPTED', 'DYNAMIC_PACKS_FULL_CATALOG',
    'DYNAMIC_CLIENT_PACKLIST_PATH', 'DYNAMIC_CLIENT_PACKLIST_SHA256', 'DYNAMIC_CLIENT_CATALOG_EPOCH',
    'DYNAMIC_CLIENT_HIDDEN_PACK_IDS', 'DYNAMIC_PACK_ENTITLEMENT_EXPANSIONS',
    'BUNDLE_ASSETSET_PROFILES_ENABLED', 'ASSET_SIGNED_PREFIX'))
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def config_assignments(raw):
    owners = [n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == 'Config']
    require(len(owners) == 1, 'Expected sole Config class')
    nodes = {}
    for n in owners[0].body:
        if isinstance(n, ast.Assign):
            require(len(n.targets) == 1 and isinstance(n.targets[0], ast.Name), 'Nonliteral config assignment')
            name = n.targets[0].id
            require(name not in nodes, 'Duplicate config assignment')
            nodes[name] = n
    return owners[0], nodes


def patch_config(raw, settings, ids):
    require(set(settings) == CONFIG_KEYS, 'Config key allowlist differs')
    owner, nodes = config_assignments(raw)
    old = ast.literal_eval(nodes['ASSET_SIGNING_SONG_IDS'].value)
    require(len(old) == len(set(old)) == 459 and set(old).isdisjoint(ids), 'Production signing preimage differs')
    changes = dict(settings, ASSET_SIGNING_SONG_IDS=old + sorted(ids))
    require(len(changes['ASSET_SIGNING_SONG_IDS']) == 1991, 'Signing union differs')
    lines = raw.splitlines(keepends=True)
    edits, additions = [], []
    for name, value in changes.items():
        if name not in nodes:
            additions.append(b'    ' + name.encode() + b' = ' + repr(value).encode('utf-8'))
            continue
        n = nodes[name].value
        start = sum(map(len, lines[:n.lineno - 1])) + n.col_offset
        end = sum(map(len, lines[:n.end_lineno - 1])) + n.end_col_offset
        edits.append((start, end, repr(value).encode('utf-8')))
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    if additions:
        end = sum(map(len, lines[:owner.end_lineno]))
        edits.append((end, end, (b'' if raw[:end].endswith(b'\n') else newline) + newline.join(additions) + newline))
    candidate = raw
    for start, end, value in sorted(edits, reverse=True):
        candidate = candidate[:start] + value + candidate[end:]
    def masked(data):
        tree = ast.parse(data)
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Config')
        owner.body = [n for n in owner.body if not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in changes)]
        return ast.dump(tree, include_attributes=False)
    require(masked(raw) == masked(candidate), 'Unreviewed config AST change')
    _, after = config_assignments(candidate)
    require(all(ast.literal_eval(after[k].value) == value for k, value in changes.items()), 'Config splice mismatch')
    require(ast.literal_eval(after['DOWNLOAD_LINK_PREFIX_7_0_255'].value) ==
        'https://cdn.akai.id.vn/staging/7.0.255-remotedl-20260908/songs/', 'Production public download prefix changed')
    compile(candidate, 'config.py', 'exec')
    return candidate


def validate_parameters(p):
    require(p['alias'] == ALIAS and p['manifest_sha256'] == MANIFEST_SHA, 'Wrong bundle identity')
    require(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-before-prod25', p['operation_id']) is not None, 'Invalid operation ID')
    ids = [r['id'] for r in p['data']['server_entries']]
    require(len(ids) == len(set(ids)) == 1532 and all(re.fullmatch(r'aurora_[A-Za-z0-9_-]{1,120}', v) for v in ids), 'Aurora membership differs')
    require(set(p['data']['metadata_additions']) == set(ids) == set(p['data']['signing_ids_add_only']), 'Metadata/signing membership differs')
    rows = p['data']['chart_rows']
    require(len(rows) == 1532 and {r[0] for r in rows} == set(ids) and all(len(r) == 7 and r[2:] == [-1] * 5 for r in rows), 'Unranked chart contract differs')
    require(len(p['code']) == 12 and set(p['code']) == set(p['code_hashes']), 'Code set differs')
    for name, encoded in p['code'].items():
        require(name.startswith(('core/', 'server/', 'tools/')) and '..' not in name.split('/') and name.endswith('.py'), 'Unsafe code path')
        raw = base64.b64decode(encoded, validate=True)
        require(sha(raw) == p['code_hashes'][name], 'Candidate code digest differs')
        compile(raw, name, 'exec')
    raw = base64.b64decode(p['manifest'], validate=True)
    require(sha(raw) == MANIFEST_SHA and len(raw) == 5450689, 'Manifest byte identity differs')
    m = json.loads(raw)
    require(m['versionNumber'] == '7.0.255.25' and m['applicationVersionNumber'] == '7.0.255'
        and m['previousVersionNumber'] is None and m['totalPartitions'] == 10
        and len(m['added']) == 20903 and m['removed'] == [], 'Manifest shape differs')
    catalog = p['catalog']['text'].encode('utf-8')
    require(sha(catalog) == p['catalog']['sha256'] == p['settings']['DYNAMIC_CLIENT_PACKLIST_SHA256']
        and len(json.loads(catalog)['packs']) == 63, 'Pinned pack catalog differs')
    require(p['catalog']['path'] == './database/client_catalogs/7.0.255/packlist', 'Unexpected catalog destination')
    return set(ids)


def confined(root, name):
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root), 'Unsafe destination')
    return path


def digest_file(path):
    require(not path.is_symlink(), 'Symlink file rejected')
    return sha(path.read_bytes()) if path.exists() else None


def fingerprint(root):
    paths = []
    for folder in ('core', 'server', 'tools'):
        paths.extend((root / folder).rglob('*.py'))
    paths.extend(root / n for n in ('config.py', 'database/song_metadata.json', 'database/remote70/song_metadata.json',
                                   'database/songs/songlist', 'database/remote70/songs/songlist'))
    require(all(not x.is_symlink() and x.resolve().is_relative_to(root) for x in paths), 'Source symlink rejected')
    return {x.relative_to(root).as_posix(): sha(x.read_bytes()) for x in paths if x.is_file()}


def manifests(root):
    folder = root / 'database/bundle'
    paths = list(folder.rglob('*.json'))
    require(all(not x.is_symlink() and x.resolve().is_relative_to(folder) for x in paths), 'Manifest symlink rejected')
    return {x.relative_to(folder).as_posix(): sha(x.read_bytes()) for x in paths}


def service(name):
    result = subprocess.run(['systemctl', 'show', name, '--property=ActiveState', '--property=MainPID',
        '--property=WorkingDirectory', '--property=ExecMainStartTimestampMonotonic'], capture_output=True, text=True, check=True, timeout=10)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def api(version, staging=False, app='7.0.255'):
    origin = 'http://127.0.0.1:18081/t' if staging else 'http://127.0.0.1:18080'
    with urlopen(Request(origin + '/game/content_bundle', headers={'AppVersion': app, 'ContentBundle': version,
                 'User-Agent': 'AkaineReviewedProduction25/1'}), timeout=12) as response:
        data = json.loads(response.read(262144))
        require(response.status == 200 and data.get('success') is True, 'Local API health failed')
        return data['value']['orderedResults']


def control(action):
    subprocess.run(['sudo', '-n', 'systemctl', action, 'arcaea-server'], capture_output=True, check=True, timeout=45)


def healthy():
    for _ in range(20):
        try:
            current = service('arcaea-server')
            require(current['ActiveState'] == 'active' and current['WorkingDirectory'] == str(ROOT), 'Production service root differs')
            api('7.0.255.25')
            return current
        except Exception:
            time.sleep(1)
    raise RuntimeError('Production health did not recover')


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_json(path, value, exclusive=False):
    temporary = path if exclusive else path.with_name(path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, separators=(',', ':'))
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    if not exclusive:
        os.replace(temporary, path)
    fsync_directory(path.parent)


def protected_db(db, ids):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    result = {}
    for name in tables:
        if name not in ('chart', 'user_item'):
            rows = db.execute('SELECT * FROM "' + name.replace('"', '""') + '"')
            result[name] = sha('\n'.join(sorted(repr(tuple(r)) for r in rows)).encode())
    result['old_charts'] = sha('\n'.join(sorted(repr(tuple(r)) for r in db.execute('SELECT * FROM chart') if r[0] not in ids)).encode())
    return result


def authorize(action, first, second, database_name, trigger):
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE) and first not in ('chart', 'user_item'):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def grant_content(db, policy, enabled):
    changes, counts = [], {'users_checked': 0, 'users_changed': 0, 'inserted': 0, 'raised': 0}
    if not enabled:
        return changes, counts
    expected = policy['expected_content'](db.cursor())
    for (user_id,) in db.execute('SELECT user_id FROM user ORDER BY user_id').fetchall():
        counts['users_checked'] += 1
        before = {}
        for item_id, item_type in expected:
            rows = db.execute('SELECT amount FROM user_item WHERE user_id=? AND item_id=? AND type=?', (user_id, item_id, item_type)).fetchall()
            require(len(rows) <= 1, 'Ambiguous ownership blocks promotion')
            before[(item_id, item_type)] = rows
        result = policy['grant_missing_content'](db.cursor(), user_id)
        counts['inserted'] += result['inserted']; counts['raised'] += result['raised_null_or_zero_to_one']
        if result['inserted'] or result['raised_null_or_zero_to_one']:
            counts['users_changed'] += 1
        require(policy['missing_content_count'](db.cursor(), user_id) == 0, 'Incomplete additive grants')
        for (item_id, item_type), rows in before.items():
            if not rows or rows[0][0] in (None, 0):
                changes.append({'user_id': user_id, 'item_id': item_id, 'type': item_type,
                                'before_exists': bool(rows), 'before_amount': rows[0][0] if rows else None})
    return changes, counts


def expected_items(before, changes, inverse=False):
    expected = Counter(tuple(r) for r in before)
    for row in changes:
        key = (row['user_id'], row['item_id'], row['type'])
        old, new = (*key, row['before_amount']), (*key, 1)
        remove, add = (new, old if row['before_exists'] else None) if inverse else (old if row['before_exists'] else None, new)
        if remove is not None:
            require(expected[remove] == 1, 'Owned grant preimage differs')
            expected[remove] -= 1
            if not expected[remove]: del expected[remove]
        if add is not None:
            expected[add] += 1
    return expected


def rollback_db(db, rows, changes):
    ids = {r[0] for r in rows}
    before = protected_db(db, ids)
    items = list(db.execute('SELECT user_id,item_id,type,amount FROM user_item'))
    target = expected_items(items, changes, inverse=True)
    for row in rows:
        observed = db.execute('SELECT * FROM chart WHERE song_id=?', (row[0],)).fetchone()
        require(observed is not None and list(observed) == row, 'Foreign chart edit blocks rollback')
    for row in reversed(changes):
        key = (row['user_id'], row['item_id'], row['type'])
        observed = db.execute('SELECT amount FROM user_item WHERE user_id=? AND item_id=? AND type=?', key).fetchall()
        require(observed == [(1,)], 'Foreign grant edit blocks rollback')
        if row['before_exists']:
            db.execute('UPDATE user_item SET amount=? WHERE user_id=? AND item_id=? AND type=? AND amount=1', (row['before_amount'], *key))
        else:
            db.execute('DELETE FROM user_item WHERE user_id=? AND item_id=? AND type=? AND amount=1', key)
        require(db.execute('SELECT changes()').fetchone()[0] == 1, 'Grant rollback affected unexpected rows')
    db.executemany('DELETE FROM chart WHERE song_id=?', [(r[0],) for r in rows])
    require(protected_db(db, ids) == before, 'Rollback changed protected state')
    require(Counter(tuple(r) for r in db.execute('SELECT user_id,item_id,type,amount FROM user_item')) == target, 'Rollback grant inverse differs')


def import_check(interpreter, expected):
    script = """import importlib,json,pathlib,sys
root=pathlib.Path.cwd();sys.path.insert(0,str(root))
from core.config_manager import Config,ConfigManager
ConfigManager.load(importlib.import_module('config').Config)
names=['core.bundle','core.client_packs','core.content_grants','core.download','core.pack_contract','core.user','server.others','server.purchase','server.user','tools.create_user_cli']
for name in names:
 module=importlib.import_module(name)
 assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
from core.client_packs import reload_dynamic_pack_catalog
assert len(reload_dynamic_pack_catalog())==63
assert Config.DYNAMIC_PACKS_ENABLED and Config.DYNAMIC_PACKS_NATIVE_ACCEPTED and Config.DYNAMIC_PACKS_FULL_CATALOG
assert not Config.BUNDLE_ASSETSET_PROFILES_ENABLED and Config.CLIENT_PACK_LIMIT==62
assert Config.DOWNLOAD_LINK_PREFIX_7_0_255=='https://cdn.akai.id.vn/staging/7.0.255-remotedl-20260908/songs/'
print(json.dumps({'imports':len(names),'catalog':63,'production_paths':True}))
"""
    result = subprocess.run([interpreter, '-B', '-c', script], cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                            capture_output=True, text=True, timeout=45)
    require(result.returncode == 0, 'Actual production interpreter import check failed')
    return {'imports': 10, 'catalog': 63, 'production_paths': True}


def run(p):
    ids = validate_parameters(p)
    require(ROOT.resolve() == ROOT and STAGE.resolve() == STAGE, 'Unexpected service roots')
    for root in (ROOT, STAGE):
        for folder in (*root.parents, root, root / 'core', root / 'server', root / 'tools', root / 'database',
                       root / 'database/remote70', root / 'database/songs', root / 'database/bundle', root / 'database/backups'):
            require(not (folder / 'AGENTS.md').exists(), 'New server instructions require review')
    require(fingerprint(ROOT) == p['prod_hashes'] and fingerprint(STAGE) == p['stage_hashes'], 'Source drift since reviewed preflight')
    require(manifests(ROOT) == p['prod_manifests'] and manifests(STAGE) == p['stage_manifests'], 'Manifest drift')
    for name, expected in p['services'].items():
        require(service(name) == expected, 'Service drift since reviewed preflight')
    require(api('0.0.0') == p['prod_api'] and api('0.0.0', True) == p['stage_api'], 'Bundle selection drift')
    old_apps = {app: api('0.0.0', app=app) for app in ('6.14.11', '6.15.0')}
    interpreter = os.readlink('/proc/' + p['services']['arcaea-server']['MainPID'] + '/exe')
    require(Path(interpreter).is_file(), 'Actual service interpreter unavailable')
    code = {name: base64.b64decode(raw, validate=True) for name, raw in p['code'].items()}
    candidates = dict(code)
    config_raw = (ROOT / 'config.py').read_bytes()
    _, config_nodes = config_assignments(config_raw)
    require(ast.literal_eval(config_nodes['SAVE_FULL_UNLOCK'].value) is True, 'SAVE_FULL_UNLOCK reviewed state differs')
    candidates['config.py'] = patch_config(config_raw, p['settings'], ids)
    for name, old_count in (('database/song_metadata.json', 1002), ('database/remote70/song_metadata.json', 1011)):
        old = json.loads((ROOT / name).read_bytes())
        require(len(old) == old_count and ids.isdisjoint(old), 'Metadata collision or preimage differs')
        new = dict(old); new.update(p['data']['metadata_additions'])
        require({k: new[k] for k in old} == old, 'Old metadata changed')
        candidates[name] = (json.dumps(new, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    catalog = json.loads((ROOT / 'database/songs/songlist').read_bytes())
    require(len(catalog['songs']) == 992 and ids.isdisjoint(row['id'] for row in catalog['songs']), 'Server catalog preimage differs')
    new_catalog = dict(catalog, songs=catalog['songs'] + p['data']['server_entries'])
    require(len({r['id'] for r in new_catalog['songs']}) == len({r['idx'] for r in new_catalog['songs']}) == 2524, 'Catalog index collision')
    candidates['database/songs/songlist'] = (json.dumps(new_catalog, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    catalog_name = p['catalog']['path'].removeprefix('./')
    require(digest_file(confined(ROOT, catalog_name)) is None, 'Pinned catalog target already exists; review preimage')
    candidates[catalog_name] = p['catalog']['text'].encode('utf-8')
    paths = {name: confined(ROOT, name) for name in candidates}
    before = {name: digest_file(path) for name, path in paths.items()}
    require(all(before[name] == p['prod_hashes'].get(name) for name in candidates), 'Candidate target preimage drift')
    manifest_path = confined(ROOT, 'database/bundle/' + ALIAS + '.json')
    require(not manifest_path.exists(), 'New manifest alias exists')
    database = confined(ROOT, 'database/arcaea_database.db')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        require([list(r) for r in db.execute('SELECT * FROM chart')] == p['prod_charts'], 'Production chart content drift')
        require([list(r) for r in db.execute('PRAGMA table_info(user_item)')] == p['user_item_schema'], 'Ownership schema drift')
    required = database.stat().st_size + sum(path.stat().st_size for path in paths.values() if path.exists()) + sum(map(len, candidates.values())) + 64 * 1024 * 1024
    require(shutil.disk_usage(ROOT).free > required, 'Insufficient backup space')
    backup = confined(ROOT, 'database/backups/' + p['operation_id'])
    require(not backup.exists(), 'Operation backup exists')
    backup.mkdir(mode=0o700)
    raw, attributes = {}, {}
    reference = (ROOT / 'database/songs/songlist').stat()
    for name, path in paths.items():
        if before[name] is not None:
            raw[name] = path.read_bytes(); attributes[name] = path.stat()
            dest = backup / 'files' / name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest); os.chmod(dest, 0o600)
            require(sha(dest.read_bytes()) == before[name], 'Backup digest differs')
        else:
            raw[name] = None; attributes[name] = reference
    for name, digest in p['prod_manifests'].items():
        dest = backup / 'manifests' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'database/bundle' / name, dest)
        require(sha(dest.read_bytes()) == digest, 'Manifest backup differs')
    durable_json(backup / 'absence-markers.json', [name for name in candidates if before[name] is None], exclusive=True)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(backup / 'database.sqlite3')) as destination:
            source.backup(destination)
    os.chmod(backup / 'database.sqlite3', 0o600)
    receipt = {'status': 'BACKED_UP', 'deployed': False, 'backup': str(backup), 'before_hashes': before,
               'candidate_hashes': {name: sha(data) for name, data in candidates.items()}, 'db_committed': False,
               'stage_or_bot_changed': False, 'parameters_sha256': p['parameter_content_sha256']}
    checkpoint = lambda: durable_json(backup / 'RECEIPT.json', receipt)
    checkpoint()
    owned, committed, created_manifest, changes = [], False, False, []
    def replace(name, data, rollback=False):
        path = paths[name]
        require(confined(ROOT, name) == path, 'Replacement path escaped production root')
        require(digest_file(path) == (sha(candidates[name]) if rollback else before[name]), 'Foreign edit blocks replacement')
        path.parent.mkdir(parents=True, exist_ok=True)
        require(confined(ROOT, name) == path, 'New parent escaped production root')
        if data is None:
            path.unlink(); fsync_directory(path.parent); return
        temp = path.with_name('.' + path.name + '.' + p['operation_id'] + '.tmp')
        require(not temp.exists() and not temp.is_symlink(), 'Temporary path collision')
        original = attributes[name]
        try:
            with temp.open('xb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temp, stat.S_IMODE(original.st_mode))
            if (temp.stat().st_uid, temp.stat().st_gid) != (original.st_uid, original.st_gid):
                subprocess.run(['sudo', '-n', 'chown', str(original.st_uid) + ':' + str(original.st_gid), '--', str(temp)], capture_output=True, check=True, timeout=10)
            require(sha(temp.read_bytes()) == sha(data), 'Temporary digest differs')
            os.replace(temp, path)
            if not rollback: owned.append(name)
            fsync_directory(path.parent)
        finally:
            if temp.exists(): temp.unlink()
    try:
        require(fingerprint(ROOT) == p['prod_hashes'] and fingerprint(STAGE) == p['stage_hashes'], 'Drift during backup')
        control('stop'); require(service('arcaea-server')['ActiveState'] == 'inactive', 'Production stop failed')
        for name, data in candidates.items(): replace(name, data)
        receipt['imports'] = import_check(interpreter, p['code_hashes'])
        policy = {}; exec(compile(code['core/content_grants.py'], '<reviewed-content-policy>', 'exec'), policy)
        require(policy['CONTENT_TYPES'] == CONTENT_TYPES, 'Grant policy types differ')
        with closing(sqlite3.connect(database, timeout=30)) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                require([list(r) for r in db.execute('SELECT * FROM chart')] == p['prod_charts'], 'Chart drift before transaction')
                protected = protected_db(db, ids)
                old_items = list(db.execute('SELECT user_id,item_id,type,amount FROM user_item'))
                db.set_authorizer(authorize)
                db.executemany('INSERT INTO chart(song_id,name,rating_pst,rating_prs,rating_ftr,rating_byn,rating_etr) VALUES(?,?,?,?,?,?,?)', p['data']['chart_rows'])
                changes, counts = grant_content(db, policy, True)
                require(protected_db(db, ids) == protected, 'Protected table changed')
                require(Counter(tuple(r) for r in db.execute('SELECT user_id,item_id,type,amount FROM user_item')) == expected_items(old_items, changes), 'Unexpected ownership change')
                durable_json(backup / 'private-grant-ledger.json', changes, exclusive=True)
                receipt.update(status='DB_PREPARED_LEDGER_DURABLE', grant_counts=counts, private_ledger_rows=len(changes),
                    private_ledger_sha256=sha((backup / 'private-grant-ledger.json').read_bytes()), protected_tables_preserved=True)
                checkpoint(); db.commit(); committed = True
            finally:
                if db.in_transaction: db.rollback()
        receipt.update(status='FILES_AND_DB_APPLIED', db_committed=True); checkpoint()
        temp = manifest_path.with_name('.' + manifest_path.name + '.' + p['operation_id'] + '.tmp')
        require(not temp.exists() and not temp.is_symlink(), 'Manifest temporary collision')
        try:
            with temp.open('xb') as stream:
                stream.write(base64.b64decode(p['manifest'], validate=True)); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temp, 0o644); os.link(temp, manifest_path); created_manifest = True; fsync_directory(manifest_path.parent)
        finally:
            if temp.exists(): temp.unlink()
        control('start'); post = healthy()
        require(post['MainPID'] != p['services']['arcaea-server']['MainPID'], 'Production worker did not restart')
        matrix = {}
        for current in ('0.0.0', '7.0.255.18', '7.0.255.20', '7.0.255.24', '7.0.255.25', '7.0.255.26'):
            values = api(current); matrix[current] = values
            if current in ('7.0.255.25', '7.0.255.26'):
                require(values == [], 'Target or newer bundle offered an update')
            else:
                require(len(values) == 1, 'Expected one full update')
                value = values[0]
                require(value['contentBundleVersion'] == '7.0.255.25' and len(value['bundleParts']) == 10
                    and value['bundleSize'] == 4532838207 and value['jsonSize'] == 5450689
                    and value['jsonUrl'] == 'https://cdn.akai.id.vn/bundle/' + ALIAS + '.json', 'Production bundle wire differs')
        require(all(api('0.0.0', app=app) == value for app, value in old_apps.items()), 'Old app bundle behavior changed')
        expected = dict(p['prod_hashes']); expected.update({name: sha(data) for name, data in candidates.items() if name.endswith('.py') or name in p['prod_hashes']})
        require(fingerprint(ROOT) == expected and fingerprint(STAGE) == p['stage_hashes'], 'Source preservation gate failed')
        require(manifests(ROOT) == dict(p['prod_manifests'], **{ALIAS + '.json': MANIFEST_SHA}) and manifests(STAGE) == p['stage_manifests'], 'Manifest preservation gate failed')
        require(all(service(n) == p['services'][n] for n in ('arcaea-server-test', 'lygus-bot')) and api('0.0.0', True) == p['stage_api'], 'Staging or bot preservation failed')
        require(digest_file(ROOT / catalog_name) == p['catalog']['sha256'], 'Pinned catalog changed')
        receipt.update(status='APPLIED_PRODUCTION25', deployed=True, service=post, API_matrix=matrix,
                       chart_rows_added=1532, staging_and_bot_preserved=True, accounts_progress_scores_currency_preserved=True)
        checkpoint()
    except BaseException as error:
        receipt.update(status='FAILED_ROLLING_BACK', error_type=type(error).__name__, db_committed=committed); checkpoint()
        try:
            control('stop'); require(service('arcaea-server')['ActiveState'] == 'inactive', 'Rollback stop failed')
            require(all(digest_file(paths[name]) == sha(candidates[name]) for name in owned), 'Foreign source edit blocks rollback')
            if created_manifest: require(digest_file(manifest_path) == MANIFEST_SHA, 'Foreign manifest edit blocks rollback')
            if committed:
                with closing(sqlite3.connect(database, timeout=30)) as db:
                    try:
                        db.execute('BEGIN IMMEDIATE'); db.set_authorizer(authorize)
                        rollback_db(db, p['data']['chart_rows'], changes); db.commit()
                    finally:
                        if db.in_transaction: db.rollback()
            for name in reversed(owned): replace(name, raw[name], rollback=True)
            if created_manifest: manifest_path.unlink(); fsync_directory(manifest_path.parent)
            require(fingerprint(ROOT) == p['prod_hashes'] and manifests(ROOT) == p['prod_manifests'], 'Rollback source readback failed')
            control('start'); healthy()
            require(api('0.0.0') == p['prod_api'] and api('7.0.255.18') == [], 'Old production18 API not restored')
            require(fingerprint(STAGE) == p['stage_hashes'] and all(service(n) == p['services'][n] for n in ('arcaea-server-test', 'lygus-bot')), 'Rollback controls changed')
            receipt.update(status='ROLLED_BACK_PRODUCTION_ONLY', deployed=False, owned_DB_changes_reversed=committed)
        except BaseException as rollback_error:
            receipt.update(status='ROLLBACK_BLOCKED_REQUIRES_INSPECTION', rollback_error_type=type(rollback_error).__name__)
        checkpoint()
    return receipt
