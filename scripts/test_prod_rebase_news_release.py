"""V36 sibling orchestration contracts; no private inputs or compiler calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_prod_rebase_news_release as news
import build_prod_rebase_release as release


class NewsReleaseTests(unittest.TestCase):
    def test_scoped_bindings_restore_v34_even_after_failure(self):
        previous = release.PROFILE, release.CHECKOUT, release.PLAN, release.build_prod_rebase_core, release.ACTIVE_MODULES
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            with news.bindings():
                self.assertEqual(release.PROFILE, news.PROFILE)
                self.assertIs(release.build_prod_rebase_core, news.news_core)
                self.assertIn(news.build_news_core, release.ACTIVE_MODULES)
                raise RuntimeError('synthetic')
        self.assertEqual(previous, (release.PROFILE, release.CHECKOUT, release.PLAN,
                                   release.build_prod_rebase_core, release.ACTIVE_MODULES))

    def test_payload_stop_checks_five_outputs_and_never_assembles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / 'payload-kit/final/payload'
            expected = {}
            for name in release.PAYLOAD_NAMES:
                target = payload / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(name.encode())
                expected[name] = hashlib.sha256(name.encode()).hexdigest()
            (root / 'core').mkdir()
            (root / 'core/BUILD_RECEIPT.json').write_text('{}')
            base = root / 'base.apk'; base.write_bytes(b'base')
            profile = root / 'profile'; profile.write_bytes(b'profile')
            lock = {'expected_replacements': [{'role': 'final/payload/' + name, 'sha256': pin}
                                              for name, pin in expected.items()]}

            def engine(*unused):
                release.build_android_client.build(base, {}, root / 'payload-kit', root / 'unsigned.apk')

            original = release.build_android_client.build
            with patch.object(release, 'build', side_effect=engine), patch.object(news, 'verify'), \
                    patch.object(news, 'PROFILE', profile), patch.object(news, 'CHECKOUT', profile):
                result = news.payloads_only(lock, {}, root)
            self.assertEqual(result['payload_sha256'], expected)
            self.assertFalse(result['APK_assembled'])
            self.assertFalse((root / 'unsigned.apk').exists())
            self.assertIs(release.build_android_client.build, original)

    def test_payload_mismatch_restores_assembler_and_propagates(self):
        original = release.build_android_client.build
        with patch.object(release, 'build', side_effect=ValueError('payload mismatch')):
            with self.assertRaisesRegex(ValueError, 'payload mismatch'):
                news.payloads_only({}, {}, Path('unused'))
        self.assertIs(release.build_android_client.build, original)


if __name__ == '__main__':
    unittest.main()
