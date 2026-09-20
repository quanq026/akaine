"""Security regressions for a fresh public checkout."""

import unittest

import main
from core.config_manager import Config
from core.error import NoAccess
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


if __name__ == "__main__":
    unittest.main()
