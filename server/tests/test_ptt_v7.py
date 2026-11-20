from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from core.ptt_v7 import potential_v7, stored_potential
from tools.recompute_ptt import recompute


class PotentialV7Tests(unittest.TestCase):
    def test_top_ten_double_and_empty_slots_count_in_divisor(self):
        self.assertEqual(potential_v7([12] * 10 + [9] * 40 + [8]), 10)
        self.assertEqual(potential_v7([12, -1]), 0.4)
        self.assertEqual(stored_potential(potential_v7([12, -1])), 40)

    def test_preview_backup_migration_and_retry_on_wal_database(self):
        with TemporaryDirectory() as folder:
            database = Path(folder) / 'game.db'
            backup = Path(folder) / 'pre-b50.db'
            with closing(sqlite3.connect(database)) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.executescript("""
                    CREATE TABLE user(user_id INTEGER PRIMARY KEY, rating_ptt INTEGER);
                    CREATE TABLE best_score(user_id INTEGER, rating REAL);
                    CREATE TABLE recent30(user_id INTEGER, rating REAL);
                    INSERT INTO user VALUES (1, 345), (2, 0);
                    INSERT INTO best_score VALUES (1, 12), (1, -1);
                    INSERT INTO recent30 VALUES (1, 20);
                """)
                self.assertEqual(recompute(database), (2, 1))
                self.assertEqual(conn.execute('SELECT rating_ptt FROM user WHERE user_id=1').fetchone(), (345,))
                self.assertEqual(recompute(database, backup), (2, 1))
                self.assertEqual(recompute(database, backup), (2, 0))
                self.assertEqual(conn.execute('SELECT rating_ptt FROM user WHERE user_id=1').fetchone(), (40,))
                self.assertEqual(conn.execute('SELECT rating FROM recent30').fetchall(), [(20.0,)])
                self.assertEqual(conn.execute('SELECT rating FROM best_score').fetchall(), [(12.0,), (-1.0,)])
            with closing(sqlite3.connect(backup)) as archived:
                self.assertEqual(archived.execute('SELECT rating_ptt FROM user WHERE user_id=1').fetchone(), (345,))
