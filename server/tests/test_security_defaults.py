"""Security regressions for a fresh public checkout."""

import unittest
import sqlite3
import tempfile
from pathlib import Path

import main
from core.config_manager import Config
from core.error import NoAccess
from core.init import DatabaseInit
from server import auth


class SecurityDefaultsTests(unittest.TestCase):
    def test_fresh_checkout_has_no_shared_credentials(self):
        self.assertEqual(Config.USERNAME, "")
        self.assertEqual(Config.PASSWORD, "")
        self.assertEqual(Config.SECRET_KEY, "")
        self.assertEqual(Config.LINKPLAY_AUTHENTICATION, "")
        self.assertEqual(Config.LINKPLAY_TCP_SECRET_KEY, "")

    def test_server_refuses_to_start_without_security_settings(self):
        with self.assertRaisesRegex(RuntimeError, "missing security settings"):
            main.validate_runtime_config()

    def test_local_oauth_compatibility_is_disabled(self):
        self.assertFalse(Config.INSECURE_LOCAL_OAUTH_COMPAT_ENABLED)
        with self.assertRaises(NoAccess):
            auth._ensure_local_oauth_user(None)

    def test_fresh_database_does_not_seed_a_shared_admin_account(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'new.db'
            init_files = Path(__file__).resolve().parents[1] / 'database' / 'init'
            DatabaseInit(str(database), str(init_files)).init()
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute('select count(*) from user').fetchone()[0], 0)
                self.assertGreater(connection.execute('select count(*) from character').fetchone()[0], 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
