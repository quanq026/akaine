"""7.3.1 server profile with disposable data and Flask's in-process client."""
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from flask import Flask

from core.bundle import BundleParser
from core.client_compat import character_row_for_app_version, song_download_prefix
from core.client_packs import pack_ids_for_dynamic_user
from core.config_manager import Config
from core.constant import Constant
from core.download import DownloadList, SonglistParser
from core.error import NoAccess
from main import validate_runtime_config
from server import auth, others


class Client73Test(TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.root = Path(root)
        new_root = self.bundle('7.3.1', '7.3.1.1')
        self.enterContext(patch.multiple(
            Config, CLIENT_7_3_ENABLED=True,
            ALLOW_APPVERSION=['7.3.1'],
            BUNDLE_ASSETSET_PROFILES_ENABLED=False,
            BUNDLE_STRICT_MODE=True,
            BUNDLE_MANIFEST_7_3_SHA256=sha256(new_root).hexdigest(),
            FRESH_INSTALL_APP_BUNDLE_OVERRIDES={'7.3.1': '7.3.1.1'},
            FRESH_INSTALL_DEVICE_BUNDLE_OVERRIDES={},
            BUNDLE_DOWNLOAD_LINK_PREFIX_APP_OVERRIDES={'7.3.1': 'https://stage.invalid/v73'},
        ))
        self.enterContext(patch.object(Constant,'CONTENT_BUNDLE_FOLDER_PATH', root))
        self.enterContext(patch.object(Constant,'BUNDLE_DOWNLOAD_LINK_PREFIX','https://stage.invalid/legacy/'))
        for name in ('bundles','max_bundle_version','next_versions','version_tuple_bundles',
                     'profile_bundles','profile_edges','profile_targets','profile_anchors'):
            self.enterContext(patch.object(BundleParser,name,{}))
        BundleParser.get_bundles.cache_clear()
        self.addCleanup(BundleParser.get_bundles.cache_clear)
        BundleParser()
        app = Flask(__name__)
        app.register_blueprint(auth.bp)
        app.register_blueprint(others.bp)
        self.client = app.test_client()

    def bundle(self, app, version, previous=None, tags=True):
        fixture = {'applicationVersionNumber': app, 'versionNumber': version,
                   'previousVersionNumber': previous, 'uuid': 'fixture'}
        if app == '7.3.1' and tags:
            fixture['pathToDetails'] = {f'songs/{name}': b64encode(bytes([i])*32).decode()
                                        for i,name in enumerate(('songlist','packlist','unlocks'))}
        raw = json.dumps(fixture).encode()
        (self.root / f'{version}.json').write_bytes(raw)
        (self.root / f'{version}.cb').write_bytes(b'fixture')
        return raw

    def fetch(self, version='7.3.1', bundle=None):
        headers = {'AppVersion': version, 'DeviceId': 'old-device'}
        if bundle is not None:
            headers['ContentBundle'] = bundle
        return self.client.get('/game/content_bundle', headers=headers)

    def test_opt_in_required_even_with_permissive_legacy_configuration(self):
        for flag, allowed in ((False, []), (True, []), (False, ['7.3.1'])):
            with patch.multiple(Config, CLIENT_7_3_ENABLED=flag, ALLOW_APPVERSION=allowed), \
                    patch('server.auth.Connect') as connect:
                response = self.client.post('/auth/login', headers={'AppVersion': '7.3.1'})
                self.assertEqual(response.get_json()['error_code'], 5)
                connect.assert_not_called()

    def test_own_full_root_for_initial_and_legacy_bundle_no_downgrade(self):
        with patch('server.others.Connect'):
            for value in (None, '', '0.0.0', '0.0.1'):
                response = self.fetch(bundle=value)
                root, = response.get_json()['value']['orderedResults']
                self.assertEqual((root['appVersion'],root['contentBundleVersion']),('7.3.1','7.3.1.1'))
                self.assertEqual(root['bundleUrl'],'https://stage.invalid/v73/7.3.1.1.cb')
                self.assertEqual(response.headers['Cache-Control'],'private, no-store')
            for value in ('7.3.1.1', '7.3.1.2'):
                self.assertEqual(self.fetch(bundle=value).get_json()['value']['orderedResults'],[])
            self.assertEqual(self.fetch(bundle='invalid').status_code,400)

    def test_missing_profile_does_not_return_legacy_root(self):
        with patch.object(Config,'FRESH_INSTALL_APP_BUNDLE_OVERRIDES',{'7.3.1':'0.0.1'}), \
                patch('server.others.Connect'):
            self.assertEqual(self.fetch().status_code,503)
        self.bundle('7.3.1','7.3.1.1',previous='0.0.1')
        with self.assertRaisesRegex(ValueError,'full-root manifest'):
            BundleParser().re_init()

    def test_correctly_pinned_draft_still_cannot_be_served(self):
        draft = self.bundle('7.3.1','7.3.1.1',tags=False)
        with patch.object(Config,'BUNDLE_MANIFEST_7_3_SHA256',sha256(draft).hexdigest()):
            with self.assertRaisesRegex(ValueError,'lacks catalogue authentication tags'):
                BundleParser().re_init()

    def test_runtime_launch_requires_isolated_settings_and_reviewed_inputs(self):
        configuration = dict(
            USERNAME='fixture', PASSWORD='fixture', SECRET_KEY='fixture',
            HOST='127.0.0.1', ALLOW_APPVERSION=['7.3.1'],
            SET_LINKPLAY_SERVER_AS_SUB_PROCESS=False, LINKPLAY_HOST='',
            CHARACTER_FULL_UNLOCK=False, WORLD_SONG_FULL_UNLOCK=False,
            WORLD_SCENERY_FULL_UNLOCK=False, DYNAMIC_PACKS_FULL_CATALOG=False,
            INSECURE_LOCAL_OAUTH_COMPAT_ENABLED=False,
            ALLOW_SCORE_WITH_NO_SONG=False, DOWNLOAD_FORBID_WHEN_NO_ITEM=True,
            DYNAMIC_PACKS_ENABLED=True, DYNAMIC_PACKS_7_3_NATIVE_ACCEPTED=True,
            DOWNLOAD_LINK_PREFIX_7_3_1='https://stage.invalid/songs/',
            SONGLIST_7_3_SHA256='a'*64, SONG_METADATA_7_3_SHA256='b'*64,
        )
        with patch.multiple(Config,**configuration):
            validate_runtime_config()
            for field,value in (('HOST','0.0.0.0'),
                                ('DYNAMIC_PACKS_7_3_NATIVE_ACCEPTED',False),
                                ('DOWNLOAD_LINK_PREFIX_7_3_1','http://stage.invalid/songs/'),
                                ('BUNDLE_MANIFEST_7_3_SHA256','')):
                with self.subTest(field=field), patch.object(Config,field,value):
                    with self.assertRaises(RuntimeError):
                        validate_runtime_config()

    def test_local_bundle_tokens_cannot_use_legacy_cdn_prefix(self):
        with patch.object(Config,'BUNDLE_DOWNLOAD_LINK_PREFIX_APP_OVERRIDES',{}), \
                patch('server.others.Connect') as connection:
            self.client.application.add_url_rule('/bundle_download/<token>',endpoint='bundle_download',
                                                 view_func=lambda token: '')
            root,=self.fetch().get_json()['value']['orderedResults']
            self.assertIn('/bundle_download/',root['bundleUrl'])
            self.assertNotIn('stage.invalid',root['bundleUrl'])
            connection.return_value.__enter__.return_value.executemany.assert_called_once()

    def test_pack_capability_and_amiya_are_version_bound(self):
        row={'character':102,'is_char_uncapped':True}
        self.assertEqual(character_row_for_app_version(row,'0.0.1'),
                         {'character':0,'is_char_uncapped':False})
        self.assertEqual(character_row_for_app_version(row,'7.3.1'),row)
        with self.assertRaises(NoAccess):
            song_download_prefix('7.3.1','https://stage.invalid/legacy/')
        header={'AppVersion':'7.3.1','Akaine-Packs':'dynamic1'}
        with self.assertRaises(NoAccess):
            pack_ids_for_dynamic_user(None,header)
        packlist=self.root/'packlist'
        raw=b'{"packs":[{"id":"base"},{"id":"arknights"}]}'
        packlist.write_bytes(raw)
        with patch.multiple(Config,DYNAMIC_PACKS_ENABLED=True,DYNAMIC_PACKS_7_3_NATIVE_ACCEPTED=True,
                            DYNAMIC_CLIENT_7_3_PACKLIST_PATH=str(packlist),
                            DYNAMIC_CLIENT_7_3_PACKLIST_SHA256=sha256(raw).hexdigest(),
                            DYNAMIC_CLIENT_7_3_CATALOG_EPOCH='fixture'):
            class User:
                def _get_positive_pack_ids(self):
                    return []
            self.assertEqual(pack_ids_for_dynamic_user(User(),header,for_authorization=True),['base'])

    def test_download_catalogue_keeps_world_and_pack_entitlements_separate(self):
        songlist = self.root/'songs.json'
        metadata = self.root/'song_metadata.json'
        rows = [
            {'id':'hascome','set':'arknights','purchase':'arknights','remote_dl':True,
             'difficulties':[{'ratingClass':0}],
             'additional_files':[{'file_name':'video.mp4'},{'file_name':'fx.wav'}]},
            {'id':'renegadeark','set':'base','purchase':'','remote_dl':True,'world_unlock':True,
             'difficulties':[{'ratingClass':0}]},
        ]
        songlist.write_text(json.dumps({'songs':rows}),encoding='utf-8')
        hashes = {
            'hascome': {'files':['base.ogg','0.aff','video.mp4','fx.wav'],
                        'hashes':{'base.ogg':'a'*32,'0.aff':'b'*32,'video.mp4':'c'*32,'fx.wav':'f'*32}},
            'renegadeark': {'files':['base.ogg','0.aff'],
                            'hashes':{'base.ogg':'d'*32,'0.aff':'e'*32}},
        }
        metadata.write_text(json.dumps(hashes),encoding='utf-8')
        original_init = SonglistParser.__init__
        clear = (DownloadList.get_one_song_file_names.cache_clear,
                 DownloadList.get_all_song_ids.cache_clear)
        for clear_cache in clear:
            clear_cache()
            self.addCleanup(clear_cache)
        with patch.multiple(
                Config, SONGLIST_7_3_SHA256=sha256(songlist.read_bytes()).hexdigest(),
                SONG_METADATA_7_3_SHA256=sha256(metadata.read_bytes()).hexdigest(),
                SONG_FILE_HASH_PRE_CALCULATE=False, DOWNLOAD_FORBID_WHEN_NO_ITEM=True,
                DOWNLOAD_LINK_PREFIX_7_3_1='https://stage.invalid/songs/',
        ), patch.multiple(
                SonglistParser, has_songlist=False, songs={}, pack_info={},
                free_songs=set(), world_songs=set(), qa73_waves={},
        ), patch.object(SonglistParser,'__init__',lambda instance: original_init(instance,songlist)), \
                patch('core.download.SONG_METADATA_PATH',metadata), \
                patch('core.download.song_metadata',{}), patch('core.download.reload_dynamic_pack_catalog'):
            with self.assertRaises(NoAccess):
                DownloadList(app_version='7.3.1').add_songs(['hascome'])
            DownloadList.initialize_cache()
            self.assertFalse(SonglistParser.is_available_file('unknown','base.ogg'))
            self.assertTrue(SonglistParser.is_available_file('hascome','fx.wav'))
            self.assertFalse(SonglistParser.is_available_file('hascome','other.wav'))
            for packs,world,expected in (([],[],set()), (['arknights'],[],{'hascome'}),
                                         ([],['renegadeark'],{'renegadeark'})):
                user = SimpleNamespace(owned_pack_ids=packs, singles=[], world_songs=world)
                downloads = DownloadList(user=user,app_version='7.3.1')
                downloads.add_songs(['hascome','renegadeark'])
                self.assertEqual(set(downloads.urls),expected)
                if 'hascome' in expected:
                    self.assertEqual(downloads.urls['hascome']['additional_files'],[
                        {'checksum':'c'*32,'file_name':'video.mp4'},
                        {'checksum':'f'*32,'file_name':'fx.wav'},
                    ])
            metadata.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'reviewed pin'):
                DownloadList.initialize_cache()
            with self.assertRaises(NoAccess):
                DownloadList(app_version='7.3.1').add_songs(['hascome'])
