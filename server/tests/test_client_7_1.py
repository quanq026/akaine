"""7.1 compatibility boundaries on disposable data; no network or player DB."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from core import client_packs
from core.character import UserCharacter, UserCharacterList
from core.client_compat import (character_row_for_app_version, character_visible_for_app_version,
                                song_download_prefix, uses_current_contract)
from core.config_manager import Config
from core.content_grants import grant_missing_full_characters
from core.error import LowVersion, NoAccess
from core.init import DatabaseInit, FileChecker
from core.score import rating_ptt_for_app_version
from core.sql import Connect
from server import others
from server.func import header_check
from test_bundle_profiles import load_classes, manifest
from test_content_projection_parity import projection_methods


INIT = Path(__file__).resolve().parents[1] / 'database/init'


class Client71Tests(unittest.TestCase):
    def test_exact_version_gate_and_new_partner_assets_preserve_old_clients(self):
        with patch.object(Config, 'CLIENT_7_1_ENABLED', False):
            with self.assertRaises(LowVersion): uses_current_contract('7.1.0')
            self.assertIsInstance(header_check(SimpleNamespace(headers={'AppVersion': '7.1.0'})), LowVersion)
        with patch.object(Config, 'CLIENT_7_1_ENABLED', True):
            for version in ('7.0.255', '7.1.0'):
                self.assertTrue(uses_current_contract(version))
                self.assertEqual(rating_ptt_for_app_version(1234, version), 12340)
            for version in ('7.1.0.0', '7.2.0', None): self.assertFalse(uses_current_contract(version))
            self.assertFalse(character_visible_for_app_version(98, '6.15.0'))
            row = {'character': 101, 'is_char_uncapped': True, 'score': 9876543}
            self.assertIs(character_row_for_app_version(row, '7.1.0'), row)
            projected = character_row_for_app_version(row, '7.0.255')
            self.assertEqual(projected, dict(row, character=0, is_char_uncapped=False))
            self.assertEqual(row['character'], 101)

    def test_7_1_cloud_projection_reuses_current_contract_and_download_route(self):
        methods = projection_methods()
        with patch.multiple(Config, CLIENT_7_1_ENABLED=True,
                            DOWNLOAD_LINK_PREFIX_7_0_255='https://fixture.invalid/old/',
                            DOWNLOAD_LINK_PREFIX_7_1_0='https://fixture.invalid/new/'):
            for version in ('7.0.255', '7.1.0'):
                save = SimpleNamespace(scores_data=[{'song_id': 'testify1', 'score': 9876543}],
                                       clearlamps_data=[], clearedsongs_data=[])
                methods['project_cloud_score_song_ids'](save, version)
                self.assertEqual(save.scores_data, [{'song_id': 'testify', 'score': 9876543}])
            self.assertEqual(song_download_prefix('7.0.255', 'legacy'), 'https://fixture.invalid/old/')
            self.assertEqual(song_download_prefix('7.1.0', 'legacy'), 'https://fixture.invalid/new/')
            with patch.object(Config, 'DOWNLOAD_LINK_PREFIX_7_1_0', ''):
                with self.assertRaises(NoAccess): song_download_prefix('7.1.0', 'legacy')

    def test_separate_pinned_catalogues_require_matching_capability_and_native_acceptance(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.write_text(json.dumps({'packs': [{'id': 'base'}, {'id': 'old'}]}))
            new.write_text(json.dumps({'packs': [{'id': 'base'}, {'id': 'new'}]}))
            settings = dict(CLIENT_7_1_ENABLED=True, DYNAMIC_PACKS_ENABLED=True,
                DYNAMIC_PACKS_NATIVE_ACCEPTED=True, DYNAMIC_PACKS_7_1_NATIVE_ACCEPTED=True,
                DYNAMIC_PACKS_FULL_CATALOG=True, FREE_PACKS=[], DYNAMIC_CLIENT_HIDDEN_PACK_IDS=[],
                DYNAMIC_PACK_ENTITLEMENT_EXPANSIONS={},
                DYNAMIC_CLIENT_PACKLIST_PATH=str(old), DYNAMIC_CLIENT_PACKLIST_SHA256=hashlib.sha256(old.read_bytes()).hexdigest(),
                DYNAMIC_CLIENT_CATALOG_EPOCH='old', DYNAMIC_CLIENT_7_1_PACKLIST_PATH=str(new),
                DYNAMIC_CLIENT_7_1_PACKLIST_SHA256=hashlib.sha256(new.read_bytes()).hexdigest(), DYNAMIC_CLIENT_7_1_CATALOG_EPOCH='new')
            user = SimpleNamespace(_get_positive_pack_ids=lambda: [])
            with patch.multiple(Config, **settings), patch.object(client_packs, '_snapshots', {}):
                for version, wanted in (('7.0.255', ['base', 'old']), ('7.1.0', ['base', 'new'])):
                    self.assertEqual(client_packs.pack_ids_for_dynamic_user(user, {'AppVersion': version, 'Akaine-Packs': 'dynamic1'}), wanted)
                with self.assertRaises(NoAccess): client_packs.pack_ids_for_dynamic_user(user, {'AppVersion': '7.1.0'})
                with patch.object(Config, 'DYNAMIC_PACKS_7_1_NATIVE_ACCEPTED', False):
                    with self.assertRaises(NoAccess): client_packs.pack_ids_for_dynamic_user(user, {'AppVersion': '7.1.0', 'Akaine-Packs': 'dynamic1'})
                new.write_text('{}')
                with self.assertRaises(ValueError): client_packs.reload_dynamic_pack_catalog('7.1.0')
                self.assertEqual(client_packs.dynamic_catalog_pack_ids('7.1.0'), ('base', 'new'))

    def test_full_bundle_supports_cached_7_0_upgrade_and_never_downgrades(self):
        with TemporaryDirectory() as directory, patch.object(Config, 'CLIENT_7_1_ENABLED', True):
            folder = Path(directory)
            (folder / 'old.json').write_text(json.dumps(manifest('7.0.255.28')))
            (folder / 'new.json').write_text(json.dumps(manifest('7.1.0.1', app='7.1.0')))
            config = SimpleNamespace(BUNDLE_STRICT_MODE=False, BUNDLE_DOWNLOAD_LINK_PREFIX='https://fixture.invalid/bundle/',
                BUNDLE_ASSETSET_PROFILES_ENABLED=True, BUNDLE_ASSETSET_PROFILE_DEVICES=None,
                BUNDLE_ASSETSET_PROFILES={app: {'full': {'target': target, 'manifests': [name]}}
                    for app, target, name in (('7.0.255', '7.0.255.28', 'old.json'), ('7.1.0', '7.1.0.1', 'new.json'))})
            parser = load_classes(config, folder)['BundleParser']; parser()
            self.assertEqual([row.version for row in parser.get_bundles('7.1.0', '7.0.255.28')], ['7.1.0.1'])
            self.assertEqual(parser.get_bundles('7.1.0', '7.1.0.1'), [])
            self.assertEqual(parser.get_bundles('7.0.255', '7.1.0.1'), [])
            with patch.object(Config, 'CLIENT_7_1_ENABLED', False):
                with self.assertRaises(LowVersion): parser.get_bundles('7.1.0', '0.0.0')

    def setUp(self):
        self.directory = TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'fixture.db'
        with patch.object(Config, 'CLIENT_7_1_ENABLED', False): DatabaseInit(str(self.database), str(INIT)).init()

    def seed(self, connection):
        initializer = DatabaseInit(str(self.database), str(INIT)); initializer.c = connection.cursor()
        initializer.client_7_1_character_init()

    def test_character_seed_is_additive_idempotent_and_preserves_recorded_maya_form(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('INSERT INTO user(user_id,character_id,is_char_uncapped,is_char_uncapped_override) VALUES(7,71,0,1)')
            db.execute('INSERT INTO user_char VALUES(7,71,11,2400.5,1,1,1)')
            db.execute('INSERT INTO user_char_full VALUES(7,71,18,9000.5,0,1,1)'); db.commit()
            with patch.multiple(Config, CLIENT_7_1_ENABLED=True, CHARACTER_FULL_UNLOCK=True):
                db.execute('BEGIN IMMEDIATE'); self.seed(db); db.commit()
                self.assertEqual(db.execute('SELECT level,exp,is_uncapped,is_uncapped_override,skill_flag FROM user_char_full WHERE user_id=7 AND character_id=71').fetchone(), (18,9000.5,1,1,1))
                self.assertEqual(db.execute('SELECT is_char_uncapped,is_char_uncapped_override FROM user WHERE user_id=7').fetchone(), (1,1))
                before = db.iterdump(); before = list(before)
                db.execute('BEGIN IMMEDIATE'); self.seed(db); db.commit()
                self.assertEqual(list(db.iterdump()), before)
                self.assertEqual(db.execute('SELECT count(*) FROM character WHERE character_id IN(100,101)').fetchone()[0], 2)
                db.execute('BEGIN IMMEDIATE'); grant_missing_full_characters(db.cursor(), 7); db.rollback()

    def test_character_collision_rolls_back_without_automatic_schema_migration(self):
        with closing(sqlite3.connect(self.database)) as db, patch.object(Config, 'CLIENT_7_1_ENABLED', True):
            db.execute("INSERT INTO character(character_id,name) VALUES(100,'other')"); db.commit()
            before = list(db.iterdump()); db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError): self.seed(db)
            db.rollback(); self.assertEqual(list(db.iterdump()), before)
            db.execute("UPDATE config SET value='legacy' WHERE id='version'"); db.commit()
            with patch('core.init.DatabaseMigrator') as migrate:
                self.assertFalse(FileChecker(Mock())._check_update_database_main(str(self.database)))
                migrate.assert_not_called()

    def test_native_awakening_returns_character_rows_and_failed_serialization_rolls_back(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE character SET skill_id_uncap='skill_maya_uncap' WHERE character_id=71")
            db.execute('INSERT INTO user(user_id,character_id) VALUES(7,71)')
            db.execute("INSERT INTO login VALUES('fixture-token',7,0,'127.0.0.1','fixture')")
            for table in ('user_char', 'user_char_full'): db.execute('INSERT INTO '+table+' VALUES(7,71,11,2400.5,0,1,1)')
            db.commit()
        app = Flask(__name__); app.register_blueprint(others.bp)
        connect = lambda *args, **kwargs: Connect(str(self.database), logger=Mock())
        with patch.multiple(Config, CLIENT_7_1_ENABLED=True, CHARACTER_FULL_UNLOCK=True), \
                patch.object(UserCharacter, 'database_table_name', 'user_char_full'), \
                patch.object(UserCharacterList, 'database_table_name', 'user_char_full'), \
                patch('server.auth.Connect', side_effect=connect), patch('server.others.Connect', side_effect=connect):
            with patch.object(UserCharacter, 'to_dict', side_effect=RuntimeError('fixture failure')):
                response = app.test_client().post('/unlock/me/awaken_maya', headers={'AppVersion':'7.1.0','Authorization':'Bearer fixture-token'})
                self.assertFalse(response.get_json()['success'])
            with closing(sqlite3.connect(self.database)) as db:
                self.assertEqual(db.execute('SELECT is_uncapped FROM user_char WHERE user_id=7 AND character_id=71').fetchone()[0], 0)
            response = app.test_client().post('/unlock/me/awaken_maya', headers={'AppVersion':'7.1.0','Authorization':'Bearer fixture-token'})
            result = response.get_json(); self.assertTrue(result['success'])
            self.assertEqual(result['value']['updated_characters'][0]['character_id'], 71)


if __name__ == '__main__': unittest.main()
