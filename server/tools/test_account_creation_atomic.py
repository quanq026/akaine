"""Disposable SQLite account/link transactions and safe CLI credential input."""
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import create_user_cli as provision
import discord_bot_core as core


SCHEMA = '''
CREATE TABLE user(user_id INTEGER PRIMARY KEY,name TEXT UNIQUE,password TEXT,join_date TEXT,user_code TEXT UNIQUE,
rating_ptt INT,character_id INT,is_skill_sealed INT,is_char_uncapped INT,is_char_uncapped_override INT,
is_hide_rating INT,favorite_character INT,max_stamina_notification_enabled INT,current_map TEXT,ticket INT,prog_boost INT,email TEXT);
CREATE TABLE character(character_id INT PRIMARY KEY,max_level INT,is_uncapped INT);
INSERT INTO character VALUES(0,20,0),(1,30,1);
CREATE TABLE user_char(user_id INT,character_id INT,level INT,exp INT,is_uncapped INT,is_uncapped_override INT,skill_flag INT);
CREATE TABLE user_char_full(user_id INT,character_id INT,level INT,exp INT,is_uncapped INT,is_uncapped_override INT,skill_flag INT,PRIMARY KEY(user_id,character_id));
CREATE TABLE user_mission(user_id INT,mission_id TEXT,status INT,PRIMARY KEY(user_id,mission_id));
CREATE TABLE purchase_item(item_id TEXT,type TEXT,amount INT);
INSERT INTO purchase_item VALUES('known-pack','pack',1);
CREATE TABLE item(item_id TEXT,type TEXT,is_available INT);
INSERT INTO item VALUES('known-scenery','world_unlock',1);
CREATE TABLE user_item(user_id INT,item_id TEXT,type TEXT,amount INT,PRIMARY KEY(user_id,item_id,type));
'''


class AtomicAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game, self.mapping = self.root / 'game.db', self.root / 'mapping.db'
        with closing(sqlite3.connect(self.game)) as connection:
            connection.executescript(SCHEMA)
        self.repository = core.BotRepository(self.game, self.mapping)
        self.repository.migrate_mapping_schema()
        for mock in (patch.object(provision, 'configured_default_memories', return_value=67),
                     patch.object(provision, 'bootstrap_mission_ids', return_value=('known-mission',))):
            mock.start()
            self.addCleanup(mock.stop)

    def counts(self):
        with closing(sqlite3.connect(self.game)) as connection:
            counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                      for table in ('user', 'user_char', 'user_char_full', 'user_mission', 'user_item')}
        with closing(sqlite3.connect(self.mapping)) as connection:
            counts['mapping'] = connection.execute('SELECT COUNT(*) FROM user_mapping').fetchone()[0]
        return counts

    def test_success_and_duplicate_retry_keep_one_complete_account(self):
        account = self.repository.create_account(100, 'QaPlayer', 'synthetic9')
        self.assertEqual(account.username, 'QaPlayer')
        self.assertEqual(self.counts(), {'user': 1, 'user_char': 2, 'user_char_full': 2,
                                      'user_mission': 1, 'user_item': 2, 'mapping': 1})
        with closing(sqlite3.connect(self.game)) as connection:
            self.assertEqual(connection.execute('SELECT password FROM user').fetchone()[0], hashlib.sha256(b'synthetic9').hexdigest())
        with self.assertRaises(core.AccountConflict):
            self.repository.create_account(100, 'QaPlayer', 'synthetic9')
        self.assertEqual(self.counts()['user'], 1)
        self.assertEqual(self.counts()['mapping'], 1)

    def test_mapping_failure_rolls_back_all_account_tables(self):
        with closing(sqlite3.connect(self.mapping)) as connection:
            connection.executescript("CREATE TRIGGER fail_mapping BEFORE INSERT ON user_mapping BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
        with self.assertRaises(core.AccountConflict):
            self.repository.create_account(100, 'QaPlayer', 'synthetic9')
        self.assertEqual(set(self.counts().values()), {0})
        with closing(sqlite3.connect(self.mapping)) as connection:
            connection.execute('DROP TRIGGER fail_mapping')
        self.assertEqual(self.repository.create_account(100, 'QaPlayer', 'synthetic9').user_id, 2000001)

    def test_provision_failure_rolls_back_and_caller_owns_transaction(self):
        with patch.object(provision, 'verify_created_account', side_effect=RuntimeError('synthetic verify failure')):
            with self.assertRaises(RuntimeError):
                self.repository.create_account(100, 'QaPlayer', 'synthetic9')
        self.assertEqual(set(self.counts().values()), {0})
        with closing(sqlite3.connect(self.game)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            provision.provision_account(connection.cursor(), 'QaPlayer', 'synthetic9')
            self.assertTrue(connection.in_transaction)
            connection.rollback()
        self.assertEqual(self.counts()['user'], 0)

    def test_shared_password_policy_rejects_whitespace_without_creating_accounts(self):
        for password in (' synthetic9', 'synthetic9 ', 'short'):
            for create in (lambda: provision.create_account(self.game, 'QaPlayer', password),
                           lambda: self.repository.create_account(100, 'QaPlayer', password)):
                with self.assertRaises(core.ValidationError):
                    create()
        self.assertEqual(set(self.counts().values()), {0})

    def test_wal_mapping_fails_closed_before_provision(self):
        with closing(sqlite3.connect(self.mapping)) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        with self.assertRaisesRegex(RuntimeError, 'rollback-journal'):
            self.repository.create_account(100, 'QaPlayer', 'synthetic9')
        self.assertEqual(set(self.counts().values()), {0})

    def test_cli_bounded_stdin_has_no_password_argument_or_output(self):
        argv = [sys.executable, str(Path(provision.__file__)), 'QaPlayer', '--password-stdin', '--database', str(self.game)]
        self.assertNotIn('synthetic9', argv)
        result = subprocess.run(argv, input=b'synthetic9\n', capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'success')
        self.assertNotIn(b'synthetic9', result.stdout + result.stderr)
        self.assertEqual(self.counts()['user'], 1)

    def test_standalone_dry_run_leaves_every_account_table_empty(self):
        result = provision.create_account(self.game, 'QaPlayer', 'synthetic9', dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertEqual(set(self.counts().values()), {0})

    def test_cli_rejects_legacy_password_argv_and_overlong_stdin_without_writes(self):
        helper = str(Path(provision.__file__))
        for args, stdin in ((['QaPlayer', 'synthetic9'], b''),
                            (['QaPlayer', '--password-stdin'], b'x' * 131)):
            result = subprocess.run([sys.executable, helper, *args, '--database', str(self.game)],
                                    input=stdin, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)['status'], 'error')
            self.assertNotIn(b'synthetic9', result.stdout + result.stderr)
        self.assertEqual(set(self.counts().values()), {0})

    def test_bot_creation_calls_one_in_process_transaction_without_password_argv(self):
        source = Path(__file__).with_name('discord_bot.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        modal = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'CreateAccountModal')
        submit = next(node for node in modal.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'on_submit')
        calls = [node for node in ast.walk(submit) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == 'asyncio' and node.func.attr == 'to_thread']
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0].args[0], ast.Attribute)
        self.assertEqual(calls[0].args[0].attr, 'create_account')
        self.assertNotIn('run_create_cli', source)
        settings = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'BotSettings')
        fields = [node for node in settings.body if isinstance(node, ast.AnnAssign)]
        self.assertEqual(len(fields), 5)
        retained = ast.parse(Path(__file__).with_name('test_discord_bot.py').read_text(encoding='utf-8'))
        constructors = [node for node in ast.walk(retained) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute) and node.func.attr == 'BotSettings']
        self.assertEqual(len(constructors), 1)
        self.assertEqual(len(constructors[0].args), len(fields))


if __name__ == '__main__':
    unittest.main()
