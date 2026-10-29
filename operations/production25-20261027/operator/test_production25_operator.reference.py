"""Synthetic apply/rollback and bad-input fixtures. No SSH, sockets or live DB."""
import base64
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(os.environ['AKAINE_PROD25_OPERATOR_DIR']).resolve()
BASE = HERE.parent
(HERE / 'tmp').mkdir(exist_ok=True)
tempfile.tempdir = str(HERE / 'tmp')
sha = lambda data: hashlib.sha256(data).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.runtime = module('runtime_fixture', 'production25_runtime.py')
        self.p = json.loads((HERE / 'OPERATION_PARAMETERS.json').read_bytes())
        self.p['parameter_content_sha256'] = sha((HERE / 'OPERATION_PARAMETERS.json').read_bytes())

    def fixture(self, fail_api=False, foreign_edit=False, trigger=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'production'; stage = Path(temporary.name) / 'staging'
        self.runtime.ROOT, self.runtime.STAGE = root.resolve(), stage.resolve()
        root, stage = self.runtime.ROOT, self.runtime.STAGE
        for folder in (root / 'core', root / 'server', root / 'tools', root / 'database/bundle',
                       root / 'database/backups', root / 'database/remote70/songs', root / 'database/songs',
                       stage / 'core', stage / 'server', stage / 'tools', stage / 'database/bundle'):
            folder.mkdir(parents=True, exist_ok=True)
        old_pin = json.loads((BASE / 'LIVE_PREFLIGHT.json').read_bytes())['roots']['production']['hashes']
        for name in self.p['code']:
            if name in old_pin:
                (root / name).write_bytes((BASE / 'snapshots/production' / name).read_bytes())
        config = ('class Config:\n    SAVE_FULL_UNLOCK = True\n    ASSET_SIGNING_SONG_IDS = ' + repr(['legacy' + str(i) for i in range(459)]) +
                  "\n    DOWNLOAD_LINK_PREFIX_7_0_255 = 'https://cdn.akai.id.vn/staging/7.0.255-remotedl-20260908/songs/'\n" +
                  "    BUNDLE_DOWNLOAD_LINK_PREFIX = 'https://cdn.akai.id.vn/bundle/'\n    BUNDLE_STRICT_MODE = False\n    FRESH_INSTALL_ONLY_BUNDLE_VERSION = ''\n")
        (root / 'config.py').write_text(config, encoding='utf-8')
        (stage / 'config.py').write_text('class Config:\n    STAGE = True\n', encoding='utf-8')
        for name, count in (('database/song_metadata.json', 1002), ('database/remote70/song_metadata.json', 1011)):
            (root / name).write_text(json.dumps({'official' + str(i): {'files': ['base.ogg'], 'hashes': {'base.ogg': 'f' * 32}} for i in range(count)}), encoding='utf-8')
        (root / 'database/songs/songlist').write_text(json.dumps({'songs': [{'id': 'official' + str(i), 'idx': i} for i in range(992)]}), encoding='utf-8')
        (root / 'database/remote70/songs/songlist').write_text(json.dumps({'songs': [{'id': 'official' + str(i)} for i in range(553)]}), encoding='utf-8')
        (root / 'database/bundle/old18.json').write_text('{"versionNumber":"7.0.255.18"}', encoding='utf-8')
        database = root / 'database/arcaea_database.db'
        with closing(sqlite3.connect(database)) as db, db:
            db.executescript('CREATE TABLE chart(song_id TEXT PRIMARY KEY,name TEXT,rating_pst INT,rating_prs INT,rating_ftr INT,rating_byn INT,rating_etr INT); '
                'CREATE TABLE user(user_id INT); CREATE TABLE user_item(user_id INT,item_id TEXT,type TEXT,amount INT); '
                'CREATE TABLE item(item_id TEXT,type TEXT,is_available INT); CREATE TABLE purchase_item(item_id TEXT,type TEXT,amount INT); '
                'CREATE TABLE progress(score INT,currency INT,save TEXT);')
            db.executemany('INSERT INTO chart VALUES(?,?,?,?,?,?,?)', self.p['prod_charts'])
            db.execute('INSERT INTO user VALUES(7)'); db.execute("INSERT INTO progress VALUES(9876543,67,'fixture')")
            for typ in self.runtime.CONTENT_TYPES:
                db.execute('INSERT INTO purchase_item VALUES(?,?,99)', (typ, typ))
            db.executemany('INSERT INTO user_item VALUES(7,?,?,?)', [('pack', 'pack', 5), ('single', 'single', 0), ('character', 'character', None), ('memory', 'memory', 8)])
            db.execute("INSERT INTO purchase_item VALUES('memory','memory',99999)")
            if trigger:
                db.execute("CREATE TRIGGER bad_grant AFTER INSERT ON user_item BEGIN UPDATE progress SET currency=0; END")
            self.p['user_item_schema'] = [list(r) for r in db.execute('PRAGMA table_info(user_item)')]
        self.p['prod_hashes'] = self.runtime.fingerprint(root)
        self.p['stage_hashes'] = self.runtime.fingerprint(stage)
        self.p['prod_manifests'] = self.runtime.manifests(root)
        self.p['stage_manifests'] = self.runtime.manifests(stage)
        for key, path in (('arcaea-server', root), ('arcaea-server-test', stage)):
            self.p['services'][key]['WorkingDirectory'] = str(path)
        services = deepcopy(self.p['services']); old_pid = services['arcaea-server']['MainPID']
        def control(action):
            services['arcaea-server']['ActiveState'] = 'inactive' if action == 'stop' else 'active'
            if action == 'start': services['arcaea-server']['MainPID'] = str(int(old_pid) + 10)
        injected = [False]
        def api(version, staging=False, app='7.0.255'):
            if staging: return self.p['stage_api']
            if app != '7.0.255': return []
            activated = (root / 'database/bundle' / (self.runtime.ALIAS + '.json')).exists()
            if activated and version == '0.0.0' and fail_api and not injected[0]:
                injected[0] = True
                with closing(sqlite3.connect(database)) as db, db:
                    db.execute('UPDATE progress SET score=9999999')
                if foreign_edit:
                    (root / 'core/user.py').write_text('# concurrent foreign source edit\n', encoding='utf-8')
                raise ValueError('Injected API failure after DB commit')
            if version in ('7.0.255.25', '7.0.255.26'): return []
            if not activated: return self.p['prod_api'] if version == '0.0.0' else []
            return [{'contentBundleVersion': '7.0.255.25', 'bundleParts': [{}] * 10,
                     'bundleSize': 4532838207, 'jsonSize': 5450689,
                     'jsonUrl': 'https://cdn.akai.id.vn/bundle/' + self.runtime.ALIAS + '.json'}]
        self.runtime.service = lambda name: deepcopy(services[name])
        self.runtime.control = control
        self.runtime.api = api
        self.runtime.import_check = lambda *unused: {'fixture_only': True}
        # Production retains real POSIX directory fsync and /proc interpreter checks.
        self.runtime.fsync_directory = lambda path: None
        return root, database, patch.object(self.runtime.os, 'readlink', return_value=sys.executable)

    def test_apply_preserves_progress_old_chart_rows_and_positive_ownership(self):
        root, database, interpreter = self.fixture()
        with interpreter: result = self.runtime.run(self.p)
        self.assertEqual(result['status'], 'APPLIED_PRODUCTION25', result)
        self.assertEqual(result['grant_counts']['inserted'], 3)
        self.assertEqual(result['grant_counts']['raised'], 2)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chart').fetchone()[0], 2544)
            self.assertEqual(db.execute("SELECT amount FROM user_item WHERE item_id='pack'").fetchone(), (5,))
            self.assertEqual(db.execute('SELECT * FROM progress').fetchone(), (9876543, 67, 'fixture'))
            self.assertIsNone(db.execute("SELECT 1 FROM chart WHERE song_id='jtr_desultorysignal'").fetchone())
        self.assertTrue((Path(result['backup']) / 'database.sqlite3').is_file())
        self.assertTrue((Path(result['backup']) / 'private-grant-ledger.json').is_file())

    def test_postcommit_failure_inverse_keeps_concurrent_score_progress(self):
        root, database, interpreter = self.fixture(fail_api=True)
        with interpreter: result = self.runtime.run(self.p)
        self.assertEqual(result['status'], 'ROLLED_BACK_PRODUCTION_ONLY', result)
        self.assertEqual(self.runtime.fingerprint(root), self.p['prod_hashes'])
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chart').fetchone()[0], 1012)
            self.assertEqual(db.execute('SELECT score FROM progress').fetchone()[0], 9999999)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_item').fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT amount FROM user_item WHERE item_id='character'").fetchone(), (None,))

    def test_trigger_writing_protected_table_rolls_back_uncommitted_transaction(self):
        root, database, interpreter = self.fixture(trigger=True)
        with interpreter: result = self.runtime.run(self.p)
        self.assertEqual(result['status'], 'ROLLED_BACK_PRODUCTION_ONLY', result)
        self.assertFalse(result['db_committed'])
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chart').fetchone()[0], 1012)
            self.assertEqual(db.execute('SELECT currency FROM progress').fetchone()[0], 67)

    def test_foreign_source_edit_blocks_automatic_rollback(self):
        root, database, interpreter = self.fixture(fail_api=True, foreign_edit=True)
        with interpreter: result = self.runtime.run(self.p)
        self.assertEqual(result['status'], 'ROLLBACK_BLOCKED_REQUIRES_INSPECTION')
        self.assertEqual((root / 'core/user.py').read_text(encoding='utf-8'), '# concurrent foreign source edit\n')
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT score FROM progress').fetchone()[0], 9999999)

    def test_bad_membership_constants_manifest_and_code_rejected(self):
        for kind in ('JTR', 'ranked', 'metadata', 'manifest', 'code'):
            p = deepcopy(self.p)
            if kind == 'JTR': p['data']['server_entries'][0]['id'] = 'jtr_desultorysignal'
            if kind == 'ranked': p['data']['chart_rows'][0][4] = 100
            if kind == 'metadata': p['data']['metadata_additions'].pop(next(iter(p['data']['metadata_additions'])))
            if kind == 'manifest': p['manifest'] = base64.b64encode(b'{}').decode()
            if kind == 'code': p['code'][next(iter(p['code']))] = base64.b64encode(b'broken !').decode()
            with self.subTest(kind=kind), self.assertRaises((ValueError, SyntaxError)):
                self.runtime.validate_parameters(p)

    def test_config_splice_preserves_other_AST_and_rejects_foreign_key(self):
        raw = (b'class Config:\n    SAVE_FULL_UNLOCK = True\n    KEEP = 42\n    ASSET_SIGNING_SONG_IDS = ' +
               repr(['legacy' + str(i) for i in range(459)]).encode() +
               b"\n    DOWNLOAD_LINK_PREFIX_7_0_255 = 'https://cdn.akai.id.vn/staging/7.0.255-remotedl-20260908/songs/'\n")
        ids = {r['id'] for r in self.p['data']['server_entries']}
        candidate = self.runtime.patch_config(raw, self.p['settings'], ids)
        self.assertIn(b'KEEP = 42', candidate)
        with self.assertRaises(ValueError): self.runtime.patch_config(raw, dict(self.p['settings'], SECRET_KEY='invalid'), ids)

    def test_source_drift_stops_before_backup_or_service_action(self):
        root, database, interpreter = self.fixture()
        (root / 'server/user.py').write_text('# foreign\n', encoding='utf-8')
        with interpreter, self.assertRaisesRegex(ValueError, 'Source drift'):
            self.runtime.run(self.p)
        self.assertEqual(list((root / 'database/backups').iterdir()), [])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OperatorTests))
    receipt = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests': result.testsRun,
               'failures': len(result.failures), 'errors': len(result.errors), 'network': False, 'live_DB': False,
               'POSIX_directory_fsync': 'Production function retained; Windows offline orchestration fixture substitutes no-op.',
               'actual_import_graph': 'Runtime gate implemented; synthetic fixtures replace it. Root must run real interpreter gate during guarded apply.',
               'operation_sha256': sha((HERE / 'operate_production25.py').read_bytes()),
               'runtime_sha256': sha((HERE / 'production25_runtime.py').read_bytes())}
    (HERE / 'OPERATOR_TESTS.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
