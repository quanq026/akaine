"""Execute actual User/UserLogin classes against disposable SQLite sessions."""
import ast
import base64
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / 'core/user.py'


class AuthError(Exception):
    pass


def login_classes(source):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.ClassDef) and node.name in ('User', 'UserLogin')]
    namespace = {'hashlib': hashlib, 'hmac': hmac, 'base64': base64, 'time': SimpleNamespace(time=lambda: 1234),
                 'urandom': Mock(return_value=b'fixture!'), 'ArcLimiter': lambda *unused: SimpleNamespace(hit=lambda name: True),
                 'Config': SimpleNamespace(GAME_LOGIN_RATE_LIMIT='fixture', LOGIN_DEVICE_NUMBER_LIMIT=1,
                     ALLOW_LOGIN_SAME_DEVICE=False, ALLOW_BAN_MULTIDEVICE_USER_AUTO=False),
                 'Constant': SimpleNamespace(BAN_TIME=(1, 2)),
                 'NoAccess': AuthError, 'NoData': AuthError, 'RateLimit': AuthError, 'UserBan': AuthError}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['UserLogin'], namespace['urandom']


class PasswordGuardTests(unittest.TestCase):
    def exercise(self, source, password):
        cls, random_bytes = login_classes(source)
        with closing(sqlite3.connect(':memory:')) as db:
            db.executescript('CREATE TABLE user(user_id,name,password,ban_flag); '
                             'CREATE TABLE login(access_token,user_id,login_time,ip,login_device); '
                             "INSERT INTO login VALUES('retained-fixture-session',7,123,'fixture','same-device');")
            db.execute('INSERT INTO user VALUES(7,?,?,NULL)',
                       ('FixtureUser', hashlib.sha256(b'synthetic9').hexdigest()))
            db.commit()
            before = list(db.iterdump())
            actor = cls(db.cursor())
            check_device = Mock(wraps=actor._check_device)
            actor._check_device = check_device
            if password != 'synthetic9':
                with self.assertRaisesRegex(AuthError, 'Wrong password'):
                    actor.login('FixtureUser', password, 'same-device', 'fixture')
                self.assertIsNone(actor.token)
                random_bytes.assert_not_called()
                check_device.assert_not_called()
                self.assertEqual(list(db.iterdump()), before)
                self.assertFalse(db.in_transaction)
            else:
                actor.login('FixtureUser', password, 'same-device', 'fixture')
                self.assertIsNotNone(actor.token)
                random_bytes.assert_called_once_with(8)
                check_device.assert_called_once_with(['same-device'])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM login').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT access_token FROM login').fetchone()[0], actor.token)

    def test_wrong_password_preserves_existing_session_and_has_no_session_side_effects(self):
        self.exercise(SOURCE.read_bytes(), 'incorrect9')

    def test_correct_password_preserves_normal_session_replacement(self):
        self.exercise(SOURCE.read_bytes(), 'synthetic9')

    def test_historical_disabled_guard_is_caught_by_negative_fixture(self):
        source = SOURCE.read_text(encoding='utf-8')
        guard = ("if (not isinstance(self.password, str) or not isinstance(x[1], str)\n"
                 "                or not hmac.compare_digest(x[1], self.hash_pwd)):")
        self.assertEqual(source.count(guard), 1)
        source = source.replace(guard, 'if False:')
        with self.assertRaises(AssertionError):
            self.exercise(source, 'incorrect9')


if __name__ == '__main__':
    unittest.main()
