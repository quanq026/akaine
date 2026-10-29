"""Synthetic SQLite parity of actual API/tool/bot callers; no live database/PII."""
import ast
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

CANDIDATE = Path(__file__).resolve().parents[2]
CORE = CANDIDATE / 'server/core'
sys.path.insert(0, str(Path(__file__).resolve().parent))
package = types.ModuleType('core')
package.__path__ = [str(CORE)]
sys.modules['core'] = package
import create_user_cli as provision
import discord_bot_core as bot
from core import content_grants as grants


def methods(path, owner, names, namespace):
    tree = ast.parse(path.read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    nodes = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return {name: namespace[name] for name in names}


def snapshot(connection, table):
    return [tuple(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]


class PolicyParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game, self.mapping = self.root / 'synthetic-game.db', self.root / 'synthetic-bot.db'
        # The retained atomic fixture defines actual provisioner field/table shape.
        tree = ast.parse(Path(__file__).with_name('test_account_creation_atomic.py').read_bytes())
        schema = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'SCHEMA' for target in node.targets))
        with closing(sqlite3.connect(self.game)) as db:
            db.executescript(schema + '''
                CREATE TABLE user_save(user_id INT,data TEXT);
                CREATE TABLE best_score(user_id INT,score INT);
                CREATE TABLE recent30(user_id INT,score INT);
            ''')
            db.execute("INSERT INTO user(user_id,name,password,user_code,rating_ptt,ticket) VALUES(7,'ExistingFixture','synthetic','100000007',1234,17)")
            db.execute("INSERT INTO user_save VALUES(7,'synthetic progress')")
            db.execute('INSERT INTO best_score VALUES(7,9876543)')
            db.execute('INSERT INTO recent30 VALUES(7,9765432)')
            db.execute("INSERT INTO user_mission VALUES(7,'existing-progress',2)")
            db.execute("INSERT INTO item VALUES('diein','world_song',1)")
            db.execute("INSERT INTO purchase_item VALUES('scenery','world_unlock',1)")
            db.execute("INSERT INTO purchase_item VALUES('single-fixture','single',9)")
            db.execute("INSERT INTO purchase_item VALUES('memory-fixture','memory',9999)")
            db.execute("INSERT INTO purchase_item VALUES('pick-fixture','pick_ticket',777)")
            db.execute("INSERT INTO user_item VALUES(7,'memory-fixture','memory',4)")
            db.execute("INSERT INTO user_item VALUES(7,'pick-fixture','pick_ticket',3)")
            db.execute("INSERT INTO user_item VALUES(7,'legacy-kept','pack',5)")
            db.execute("INSERT INTO user_item VALUES(7,'single-fixture','single',7)")
            db.execute("INSERT INTO user_item VALUES(7,'known-pack','pack',0)")
            db.execute("INSERT INTO user_item VALUES(7,'known-scenery','world_unlock',NULL)")
            for number in range(100): db.execute('INSERT INTO purchase_item VALUES(?,?,1)', ('pack%03d' % number, 'pack'))
            db.commit()
        self.bot = bot.BotRepository(self.game, self.mapping)
        self.bot.migrate_mapping_schema()
        for replacement in (patch.object(provision, 'configured_default_memories', return_value=67),
                            patch.object(provision, 'bootstrap_mission_ids', return_value=('fixture-mission',))):
            replacement.start(); self.addCleanup(replacement.stop)

    def api_create(self, user_id=8):
        config = types.SimpleNamespace(DEFAULT_MEMORIES=67)
        class Missions:
            def __init__(self, cur, user): self.cur, self.user = cur, user
            def ensure_bootstrap_missions(self):
                self.cur.execute('INSERT OR IGNORE INTO user_mission VALUES(?,?,4)', (self.user.user_id, 'fixture-mission'))
        namespace = {'time': __import__('time'), 'Config': config, 'grant_missing_content': grants.grant_missing_content,
                     'UserMissionList': Missions}
        actual = methods(CORE / 'user.py', 'UserRegister', ('register', '_insert_user_char'), namespace)
        # Real core.sql.Connect yields a caller-owned sqlite3.Cursor transaction.
        sql = ast.parse((CORE / 'sql.py').read_bytes())
        connect = next(node for node in sql.body if isinstance(node, ast.ClassDef) and node.name == 'Connect')
        transport = {'sqlite3': sqlite3, 'Constant': types.SimpleNamespace(SQLITE_DATABASE_PATH=str(self.game)),
                     'ArcError': type('FixtureArcError', (Exception,), {}), 'traceback': __import__('traceback')}
        exec(compile(ast.Module(body=[connect], type_ignores=[]), '<actual-Connect>', 'exec'), transport)
        with transport['Connect'](str(self.game), logger=types.SimpleNamespace(error=lambda *unused: None)) as cur:
            actor = types.SimpleNamespace(c=cur, user_id=user_id, user_code='100000008', name='ApiFixture',
                                          hash_pwd='synthetic', email='fixture@example.local')
            actor._insert_user_char = types.MethodType(actual['_insert_user_char'], actor)
            actual['register'](actor)
            self.assertTrue(cur.connection.in_transaction)
        return user_id

    def items(self, db, user_id):
        return {(row[0], row[1]): row[2] for row in db.execute('SELECT item_id,type,amount FROM user_item WHERE user_id=?', (user_id,))}

    def test_API_tool_bot_and_existing_repair_share_additive_content_and_runtime_projection(self):
        api = self.api_create()
        tool = provision.create_account(self.game, 'ToolFixture', 'synthetic9')['user_id']
        bot_user = self.bot.create_account(999, 'BotFixture', 'synthetic9').user_id
        with closing(sqlite3.connect(self.game)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            provision.repair_existing_users(db.cursor(), '7')
            expected = grants.expected_content(db.cursor())
            for user in (7, api, tool, bot_user):
                owned = self.items(db, user)
                self.assertTrue(all(type(owned.get(key)) is int and owned[key] >= 1 for key in expected))
                self.assertNotIn(('pick-fixture', 'pick_ticket'), owned if user != 7 else {})
                if user != 7: self.assertNotIn(('memory-fixture', 'memory'), owned)
                self.assertEqual(grants.missing_content_count(db.cursor(), user), 0)
            self.assertEqual(self.items(db, 7)[('single-fixture', 'single')], 7)
            self.assertEqual(self.items(db, 7)[('legacy-kept', 'pack')], 5)
            self.assertEqual(self.items(db, 7)[('memory-fixture', 'memory')], 4)
            self.assertEqual(self.items(db, 7)[('pick-fixture', 'pick_ticket')], 3)
            self.assertEqual(db.execute('SELECT ticket FROM user WHERE user_id=?', (api,)).fetchone()[0], 67)
            self.assertEqual(db.execute('SELECT ticket FROM user WHERE user_id=?', (tool,)).fetchone()[0], 67)
            self.assertEqual(db.execute('SELECT ticket FROM user WHERE user_id=?', (bot_user,)).fetchone()[0], 67)
            # Reuse the accepted dynamic pure projection: Config virtual grants
            # are representation policy, never inferred from a client header.
            path = CORE / 'pack_contract.py'
            spec = importlib.util.spec_from_file_location('candidate_dynamic_contract', path)
            contract = importlib.util.module_from_spec(spec); spec.loader.exec_module(contract)
            catalog = ['base', 'known-pack', *('pack%03d' % i for i in range(100)), 'virtual-free', 'unowned-extra']
            projected = []
            for user in (7, api, tool, bot_user):
                raw = [name for (name, kind), amount in self.items(db, user).items() if kind == 'pack' and amount and amount > 0]
                projected.append(contract.project_owned_catalog_packs(catalog, raw, free_pack_ids=('base', 'virtual-free'),
                    profile_enabled=True, capacity_accepted=True))
            self.assertTrue(all(value == projected[0] for value in projected))
            self.assertEqual(len(projected[0]), 103)
            self.assertNotIn('unowned-extra', projected[0])
            db.rollback()

    def test_existing_repair_idempotent_diff_only_preserves_scores_progress_defaults_and_consumables(self):
        with closing(sqlite3.connect(self.game)) as db:
            db.row_factory = sqlite3.Row
            tables = ('user', 'best_score', 'recent30', 'user_save', 'user_char', 'user_char_full', 'user_mission', 'item', 'purchase_item')
            protected = {name: snapshot(db, name) for name in tables}
            existing = self.items(db, 7)
            db.execute('BEGIN IMMEDIATE')
            first = grants.grant_missing_content(db.cursor(), 7)
            after_first = snapshot(db, 'user_item')
            second = grants.grant_missing_content(db.cursor(), 7)
            self.assertGreater(first['inserted'], 0)
            self.assertEqual(first['raised_null_or_zero_to_one'], 2)
            self.assertEqual(second['inserted'], 0)
            self.assertEqual(second['raised_null_or_zero_to_one'], 0)
            self.assertEqual(snapshot(db, 'user_item'), after_first)
            for key, amount in existing.items():
                if amount is not None and amount > 0: self.assertEqual(self.items(db, 7)[key], amount)
            self.assertEqual({name: snapshot(db, name) for name in tables}, protected)
            db.rollback()
            self.assertEqual(self.items(db, 7), existing)

    def test_requires_caller_transaction_and_shared_caller_failure_rolls_back(self):
        with closing(sqlite3.connect(self.game)) as db:
            with self.assertRaises(RuntimeError): grants.grant_missing_content(db.cursor(), 7)
        with patch.object(provision, 'grant_missing_content', side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError): provision.create_account(self.game, 'FailedFixture', 'synthetic9')
        with closing(sqlite3.connect(self.game)) as db:
            self.assertIsNone(db.execute("SELECT user_id FROM user WHERE name='FailedFixture'").fetchone())

    def test_all_six_nonconsumable_types_ignore_purchase_amount_and_unavailable_items(self):
        with closing(sqlite3.connect(self.game)) as db:
            for kind in grants.CONTENT_TYPES:
                db.execute('INSERT INTO purchase_item VALUES(?,?,999)', ('purchase-' + kind, kind))
                db.execute('INSERT INTO item VALUES(?,?,1)', ('available-' + kind, kind))
                db.execute('INSERT INTO item VALUES(?,?,0)', ('unavailable-' + kind, kind))
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            grants.grant_missing_content(db.cursor(), 7)
            owned = self.items(db, 7)
            for kind in grants.CONTENT_TYPES:
                self.assertEqual(owned[('purchase-' + kind, kind)], 1)
                self.assertEqual(owned[('available-' + kind, kind)], 1)
                self.assertNotIn(('unavailable-' + kind, kind), owned)
            db.rollback()

    def test_ambiguous_or_invalid_amount_fails_and_caller_can_roll_back_prior_changes(self):
        for amount in (-1, 'bad-amount'):
            with self.subTest(amount=amount), closing(sqlite3.connect(self.game)) as db:
                db.execute("UPDATE user_item SET amount=? WHERE user_id=7 AND item_id='single-fixture'", (amount,))
                db.commit()
                before = snapshot(db, 'user_item')
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(ValueError):
                    grants.grant_missing_content(db.cursor(), 7)
                db.rollback()
                self.assertEqual(snapshot(db, 'user_item'), before)
        with closing(sqlite3.connect(':memory:')) as db:
            db.executescript('CREATE TABLE purchase_item(item_id,type,amount); CREATE TABLE item(item_id,type,is_available); '
                             'CREATE TABLE user_item(user_id,item_id,type,amount); '
                             "INSERT INTO purchase_item VALUES('duplicate','pack',1); "
                             "INSERT INTO user_item VALUES(7,'duplicate','pack',1),(7,'duplicate','pack',1);")
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                grants.grant_missing_content(db.cursor(), 7)


if __name__ == '__main__':
    unittest.main()
