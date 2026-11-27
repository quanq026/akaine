import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask

SERVER_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = SERVER_ROOT / "tools"
for entry in (str(SERVER_ROOT), str(TOOLS_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import discord_bot_core
from server import external_v1


class ExternalApiV1Tests(unittest.TestCase):
    def _build_fixture(self, *, community_limit: int = 60):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        game_db = root / "arcaea_database.db"
        log_db = root / "arcaea_log.db"
        map_db = root / "discord_bot.db"
        assets = root / "assets"
        (assets / "jackets").mkdir(parents=True)
        (assets / "char").mkdir(parents=True)
        (assets / "jackets" / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (assets / "char" / "0.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        with sqlite3.connect(game_db) as conn:
            conn.executescript(
                """
                CREATE TABLE user (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    join_date TEXT,
                    user_code TEXT,
                    rating_ptt INTEGER,
                    character_id INTEGER,
                    is_char_uncapped INTEGER,
                    is_char_uncapped_override INTEGER,
                    is_hide_rating INTEGER,
                    song_id TEXT,
                    difficulty INTEGER,
                    score INTEGER,
                    shiny_perfect_count INTEGER,
                    perfect_count INTEGER,
                    near_count INTEGER,
                    miss_count INTEGER,
                    health INTEGER,
                    modifier INTEGER,
                    time_played INTEGER,
                    clear_type INTEGER,
                    rating REAL,
                    is_profile_public INTEGER,
                    showcase_characters TEXT
                );
                CREATE TABLE best_score (
                    user_id INTEGER,
                    song_id TEXT,
                    difficulty INTEGER,
                    score INTEGER,
                    shiny_perfect_count INTEGER,
                    perfect_count INTEGER,
                    near_count INTEGER,
                    miss_count INTEGER,
                    health INTEGER,
                    modifier INTEGER,
                    time_played INTEGER,
                    best_clear_type INTEGER,
                    clear_type INTEGER,
                    rating REAL,
                    score_v2 REAL
                );
                CREATE TABLE recent30 (
                    user_id INTEGER,
                    r_index INTEGER,
                    time_played INTEGER,
                    song_id TEXT,
                    difficulty INTEGER,
                    score INTEGER,
                    shiny_perfect_count INTEGER,
                    perfect_count INTEGER,
                    near_count INTEGER,
                    miss_count INTEGER,
                    health INTEGER,
                    modifier INTEGER,
                    clear_type INTEGER,
                    rating REAL
                );
                CREATE TABLE chart (
                    song_id TEXT PRIMARY KEY,
                    name TEXT,
                    rating_pst INTEGER,
                    rating_prs INTEGER,
                    rating_ftr INTEGER,
                    rating_byn INTEGER,
                    rating_etr INTEGER
                );
                INSERT INTO user VALUES
                    (101, 'AlicePub', '2026-01-01', '101010101', 1245, 0, 0, 0, 0, 'test', 2, 9950000, 900, 1000, 2, 0, 100, 0, 1795770000, 2, 12.25, 1, '[]'),
                    (102, 'BobHidden', '2026-01-01', '202020202', 1300, 0, 0, 0, 1, 'test', 2, 9900000, 850, 990, 5, 1, 100, 0, 1795770000, 1, 12.0, 1, '[]'),
                    (103, 'EvePriv', '2026-01-01', '303030303', 1280, 0, 0, 0, 0, 'test', 2, 9990000, 980, 1002, 0, 0, 100, 0, 1795770000, 3, 12.45, 0, '[]');
                INSERT INTO best_score VALUES
                    (101, 'test', 2, 9950000, 900, 1000, 2, 0, 100, 0, 1795770000, 2, 2, 12.25, 0),
                    (103, 'test', 2, 9990000, 980, 1002, 0, 0, 100, 0, 1795770000, 3, 3, 12.45, 0);
                INSERT INTO recent30 VALUES
                    (101, 0, 1795770000, 'test', 2, 9950000, 900, 1000, 2, 0, 100, 0, 2, 12.25),
                    (103, 0, 1795770000, 'test', 2, 9990000, 980, 1002, 0, 0, 100, 0, 3, 12.45);
                INSERT INTO chart VALUES ('test', 'Test Song', 30, 70, 105, -1, -1);
                """
            )
            conn.commit()

        with sqlite3.connect(log_db) as conn:
            conn.executescript(
                """
                CREATE TABLE user_score (
                    user_id INTEGER,
                    song_id TEXT,
                    difficulty INTEGER,
                    time_played INTEGER,
                    score INTEGER,
                    shiny_perfect_count INTEGER,
                    perfect_count INTEGER,
                    near_count INTEGER,
                    miss_count INTEGER,
                    health INTEGER,
                    modifier INTEGER,
                    clear_type INTEGER,
                    rating REAL
                );
                INSERT INTO user_score VALUES
                    (101, 'test', 2, 1795770000, 9950000, 900, 1000, 2, 0, 100, 0, 2, 12.25),
                    (103, 'test', 2, 1795770001, 9990000, 980, 1002, 0, 0, 100, 0, 3, 12.45);
                """
            )
            conn.commit()

        repo = discord_bot_core.BotRepository(game_db, map_db)
        repo.migrate_mapping_schema()
        repo.register_mapping(501, 101, "AlicePub", "101010101")
        repo.register_mapping(502, 102, "BobHidden", "202020202")

        app = Flask("external_test")
        app.register_blueprint(
            external_v1.create_blueprint(
                game_db_path=game_db,
                log_db_path=log_db,
                mapping_db_path=map_db,
                asset_root=assets,
                public_until="2020-01-01T00:00:00Z",
                community_limit=community_limit,
                admin_limit=50,
            )
        )
        return repo, app.test_client()

    def test_community_key_privacy_assets_rate_limit_and_ban(self) -> None:
        repo, client = self._build_fixture(community_limit=4)

        self.assertEqual(client.get("/external/v1").status_code, 401)

        dev_token_1, replaced = repo.issue_community_api_key(501, "my-bot")
        self.assertTrue(dev_token_1.startswith("akdev_"))
        self.assertFalse(replaced)
        dev_token_2, _ = repo.issue_community_api_key(502, "other-bot")
        admin_token = repo.rotate_external_api_key(999)

        h1 = {"Authorization": f"Bearer {dev_token_1}"}
        h2 = {"Authorization": f"Bearer {dev_token_2}"}
        ha = {"Authorization": f"Bearer {admin_token}"}

        # 1. Metadata reflects community scope and omits assets
        meta = client.get("/external/v1", headers=h1)
        self.assertEqual(meta.status_code, 200)
        body = meta.get_json()
        self.assertEqual(body["access"]["scope"], "community")
        self.assertTrue(body["access"]["privacy_filtered"])
        self.assertNotIn("assets", body["resources"])
        self.assertEqual(meta.headers.get("X-External-API-Scope"), "community")

        # 2. /players hides private profiles (103) and masks hidden rating (102 -> -1)
        players = client.get("/external/v1/players", headers=h1)
        self.assertEqual(players.status_code, 200)
        by_id = {row["user_id"]: row for row in players.get_json()["data"]}
        self.assertEqual(set(by_id), {101, 102})
        self.assertEqual(by_id[101]["rating_ptt"], 1245)
        self.assertEqual(by_id[102]["rating_ptt"], -1)

        # 3. Assets forbidden (403) for community keys, then Token 1 hits per-key rate limit (429)
        self.assertEqual(client.get("/external/v1/assets/jackets", headers=h1).status_code, 403)
        best = client.get("/external/v1/best-scores", headers=h1)
        self.assertEqual(best.status_code, 200)
        self.assertEqual([r["user_id"] for r in best.get_json()["data"]], [101])
        self.assertEqual(client.get("/external/v1/best-scores", headers=h1).status_code, 429)

        # Token 2 remains unaffected by Token 1's rate limit and checks privacy filtering
        self.assertEqual(
            [r["user_id"] for r in client.get("/external/v1/best-scores?user_code=303030303", headers=h2).get_json()["data"]],
            [],
        )
        self.assertEqual(
            [r["user_id"] for r in client.get("/external/v1/recent-scores", headers=h2).get_json()["data"]],
            [101],
        )
        self.assertEqual(
            [r["user_id"] for r in client.get("/external/v1/plays", headers=h2).get_json()["data"]],
            [101],
        )
        self.assertEqual(client.get("/external/v1/assets/jackets/test.png", headers=h2).status_code, 403)

        # 4. Admin key still sees all players + assets, and rotating it did not revoke dev keys
        self.assertEqual(
            client.get("/external/v1/players", headers=ha).get_json()["count"],
            3,
        )
        asset_res = client.get("/external/v1/assets/jackets", headers=ha)
        self.assertEqual(asset_res.status_code, 200)
        self.assertEqual(asset_res.get_json()["data"], ["test.png"])

        # 5. Banning 502 immediately revokes & blocks re-issuance
        self.assertTrue(repo.ban_community_api_user(502, 999, "spam"))
        self.assertEqual(client.get("/external/v1", headers=h2).status_code, 401)
        with self.assertRaises(discord_bot_core.PermissionDenied):
            repo.issue_community_api_key(502, "retry")


if __name__ == "__main__":
    unittest.main()
