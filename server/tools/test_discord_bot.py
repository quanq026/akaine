"""Regression tests for Discord interaction response helpers."""

import asyncio
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import discord_bot  # noqa: E402
import discord_bot_core  # noqa: E402
import b30_generator  # noqa: E402
import score_card_renderer  # noqa: E402
import b30n_generator  # noqa: E402
from PIL import Image


class _Response:
    def __init__(self, done: bool) -> None:
        self._done = done
        self.sent: list[dict] = []
        self.deferred: list[dict] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, **kwargs) -> None:
        if "view" in kwargs and kwargs["view"] is None:
            raise AssertionError("Discord rejects an explicit view=None")
        self.sent.append(kwargs)

    async def defer(self, **kwargs) -> None:
        self.deferred.append(kwargs)


class _Followup:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs) -> None:
        if "view" in kwargs and kwargs["view"] is None:
            raise AssertionError("Discord rejects an explicit view=None")
        self.sent.append(kwargs)


class _Interaction:
    def __init__(self, done: bool, user_id: int = 100) -> None:
        self.response = _Response(done)
        self.followup = _Followup()
        self.user = _User(user_id)


class SendEphemeralTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_response_omits_unspecified_view(self) -> None:
        interaction = _Interaction(done=False)

        await discord_bot.send_ephemeral(interaction, content="test")

        self.assertEqual(len(interaction.response.sent), 1)
        self.assertNotIn("view", interaction.response.sent[0])
        self.assertTrue(interaction.response.sent[0]["ephemeral"])

    async def test_followup_omits_unspecified_view(self) -> None:
        interaction = _Interaction(done=True)

        await discord_bot.send_ephemeral(interaction, content="test")

        self.assertEqual(len(interaction.followup.sent), 1)
        self.assertNotIn("view", interaction.followup.sent[0])
        self.assertTrue(interaction.followup.sent[0]["ephemeral"])

    async def test_anti_raid_skips_autocomplete_interactions(self) -> None:
        import discord
        interaction = _Interaction(done=False, user_id=999999)
        interaction.type = discord.InteractionType.autocomplete
        self.assertTrue(await discord_bot._anti_raid(interaction))
        self.assertTrue(await discord_bot._anti_raid(interaction))
        self.assertEqual(interaction.response.sent, [])


class _User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _Repository:
    def list_accounts(self, discord_id: int):
        if discord_id in (200, 697075731842203728):
            return [type("Account", (), {"user_id": 97})()]
        return []


class _PublicRepository(_Repository):
    def get_profile(self, user_id: int):
        return discord_bot.Profile(
            user_id=user_id,
            username="TaggedPlayer",
            user_code="123456789",
            ptt="12.34",
            character_id=0,
            character_level=20,
            joined_at=None,
            best_score_count=1,
            recent_play_count=1,
            is_public=True,
        )

    def get_recent_scores(self, user_id: int, limit: int):
        return []


class ResolveTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_profile_resolves_linked_account(self) -> None:
        bot = type("Bot", (), {"repository": _Repository()})()
        interaction = type("Interaction", (), {"user": _User(100)})()

        user_id, is_owner = await discord_bot.resolve_target_user(
            bot, interaction, None, _User(200)
        )

        self.assertEqual(user_id, 97)
        self.assertFalse(is_owner)

    async def test_discord_mention_in_username_field_resolves_linked_account(self) -> None:
        bot = type("Bot", (), {"repository": _Repository()})()
        interaction = type("Interaction", (), {"user": _User(100)})()

        for mention in ("<@697075731842203728>", "<@!697075731842203728>"):
            with self.subTest(mention=mention):
                user_id, is_owner = await discord_bot.resolve_target_user(
                    bot, interaction, mention
                )

                self.assertEqual(user_id, 97)
                self.assertFalse(is_owner)

    async def test_rejects_two_target_types(self) -> None:
        bot = type("Bot", (), {"repository": _Repository()})()
        interaction = type("Interaction", (), {"user": _User(100)})()

        with self.assertRaises(discord_bot.ValidationError):
            await discord_bot.resolve_target_user(
                bot, interaction, "sample-player", _User(200)
            )


class PublicLookupCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_and_recent_support_discord_user_and_send_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = discord_bot.BotSettings(
                root / "game.db",
                root / "mapping.db",
                root / "b30.py",
                root,
                root / "bot.log",
            )
            bot = discord_bot.build_bot(settings)
            bot.repository = _PublicRepository()
            try:
                for command_name in ("profile", "recent"):
                    interaction = _Interaction(done=False)
                    command = bot.tree.get_command(command_name)

                    await command.callback(interaction, None, _User(200))

                    self.assertEqual(
                        interaction.response.deferred,
                        [{"thinking": True}],
                    )
                    self.assertEqual(len(interaction.followup.sent), 1)
                    self.assertNotIn("ephemeral", interaction.followup.sent[0])
            finally:
                await bot.close()


class CharacterAssetTests(unittest.TestCase):
    def test_saya_uses_matching_character_asset_id(self) -> None:
        original = b30_generator.CHAR_PATH
        with tempfile.TemporaryDirectory() as directory:
            b30_generator.CHAR_PATH = directory
            expected = Path(directory, "97_icon.png")
            expected.touch()
            try:
                actual = b30_generator.find_character_asset(97, want_icon=True)
            finally:
                b30_generator.CHAR_PATH = original

        self.assertEqual(actual, str(expected))

    def test_b30_renders_unicode_assets_and_font_fallback(self) -> None:
        scores = [{
            "song_id": "fixture", "name": f"Bài hát thử {index}", "diff": index % 5,
            "score": 9_950_000 - index * 100, "ct": "FR", "base": 10.5, "ptt": 12.1,
            "p": 950, "sp": 900, "f": 3, "l": 1, "days": index,
        } for index in range(30)]
        data = {"scores": scores, "max_ptt": 13.1, "r10_avg": 12.0,
                "character_id": 97, "is_uncapped": False, "rank": 2}
        font = next((path for path in ["C:/Windows/Fonts/arial.ttf", *b30_generator.SYSTEM_FONT_REG]
                     if Path(path).is_file()), None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = b30_generator.Image
            image.new("RGB", (100, 100), (80, 120, 180)).save(root / "fixture.png")
            image.new("RGBA", (64, 64), (220, 120, 80, 255)).save(root / "97_icon.png")
            image.new("RGBA", (180, 360), (140, 80, 180, 200)).save(root / "97.png")
            image.new("RGBA", (56, 56), (120, 160, 200, 255)).save(root / "rating_7.png")
            for configured_font in ([font, None] if font else [None]):
                with self.subTest(font="truetype" if configured_font else "fallback"):
                    settings = dict(OUT_DIR=directory, JACKETS_PATH=directory, CHAR_PATH=directory,
                        IMG_PATH=directory, FONT_REG=configured_font or str(root / "missing.ttf"),
                        FONT_BOLD=configured_font or str(root / "missing-bold.ttf"),
                        FONT_TITLE=str(root / "missing-title.otf"), SYSTEM_FONT_REG=[], SYSTEM_FONT_BOLD=[],
                        PARTNER_OVERRIDE_PATH=None, ICON_OVERRIDE_PATH=None)
                    rendered_strokes = []
                    draw_text = b30_generator.ImageDraw.ImageDraw.text
                    def record_text(draw, *args, **kwargs):
                        result = draw_text(draw, *args, **kwargs)
                        if kwargs.get("stroke_width"):
                            rendered_strokes.append(kwargs["stroke_width"])
                        return result
                    with patch.multiple(b30_generator, **settings), \
                         patch.object(b30_generator, "fetch_scores", return_value=data), \
                         patch.object(b30_generator, "download_fonts") as download, \
                         patch.object(b30_generator.ImageDraw.ImageDraw, "text", new=record_text):
                        output = b30_generator.generate_b30("123456789", "Người Chơi Ánh")
                    download.assert_called_once_with()
                    self.assertIn(2, rendered_strokes)
                    with image.open(output) as result:
                        result.load()
                        self.assertEqual((result.format, result.mode, result.size), ("JPEG", "RGB", (1024, 1536)))
                        self.assertTrue(any(low != high for low, high in result.getextrema()))


class RankingTests(unittest.TestCase):
    def test_ranking_is_stable_and_uses_five_players_per_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_db = root / "game.db"
            mapping_db = root / "mapping.db"
            connection = sqlite3.connect(game_db)
            try:
                connection.execute(
                    "CREATE TABLE user ("
                    "user_id INTEGER PRIMARY KEY, name TEXT, rating_ptt INTEGER, "
                    "is_hide_rating INTEGER DEFAULT 0)"
                )
                connection.executemany(
                    "INSERT INTO user VALUES (?,?,?,?)",
                    [
                        (1, "Alpha", 1200, 0),
                        (2, "Bravo", 1300, 0),
                        (3, "Charlie", 1300, 0),
                        (4, "Hidden", 1500, 1),
                        (5, "Unrated", -1, 0),
                        (6, "Delta", 1000, 0),
                        (7, "Echo", 900, 0),
                    ],
                )
                connection.commit()
            finally:
                connection.close()

            repository = discord_bot.BotRepository(game_db, mapping_db)
            first = repository.get_ranking_page(1)
            second = repository.get_ranking_page(2)

        self.assertEqual(first.total_players, 7)
        self.assertEqual(first.page_count, 2)
        self.assertEqual(len(first.entries), 5)
        self.assertEqual(
            [entry.username for entry in first.entries],
            ["Bravo", "Charlie", "Alpha", "Delta", "Echo"],
        )
        self.assertEqual([entry.rank for entry in first.entries], [1, 2, 3, 4, 5])
        self.assertEqual([entry.username for entry in second.entries], ["Hidden", "Unrated"])
        self.assertEqual([entry.ptt for entry in second.entries], ["Hidden", "Hidden"])

    def test_ranking_embed_contains_only_public_display_fields(self) -> None:
        page = discord_bot.RankingPage(
            entries=(
                discord_bot_core.RankingEntry(1, "PlayerOne", "12.34"),
            ),
            page=1,
            page_count=1,
            total_players=1,
        )

        embed = discord_bot.ranking_embed(page)

        self.assertIn("PlayerOne", embed.description)
        self.assertIn("12.34", embed.description)
        self.assertIn("5 per page", embed.footer.text)


class RankingViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_pagination_buttons_match_page_boundaries(self) -> None:
        bot = type("Bot", (), {})()
        first = discord_bot.RankingPage((), 1, 2, 6)
        last = discord_bot.RankingPage((), 2, 2, 6)

        first_view = discord_bot.RankingView(bot, 100, first)
        last_view = discord_bot.RankingView(bot, 100, last)
        first_buttons = {
            child.custom_id: child.disabled for child in first_view.children
        }
        last_buttons = {
            child.custom_id: child.disabled for child in last_view.children
        }

        self.assertTrue(first_buttons["lygus-ranking-previous"])
        self.assertFalse(first_buttons["lygus-ranking-next"])
        self.assertFalse(last_buttons["lygus-ranking-previous"])
        self.assertTrue(last_buttons["lygus-ranking-next"])


class MultiDiscordLinkTests(unittest.TestCase):
    def _setup_dbs(self, directory: str):
        root = Path(directory)
        game_db = root / "game.db"
        map_db = root / "mapping.db"
        with sqlite3.connect(game_db) as conn:
            conn.execute(
                """
                CREATE TABLE user (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    user_code TEXT NOT NULL,
                    rating_ptt INTEGER DEFAULT 1200,
                    character_id INTEGER DEFAULT 0,
                    join_date TEXT DEFAULT '2026-01-01',
                    is_profile_public INTEGER DEFAULT 1
                )
                """
            )
            conn.execute("CREATE TABLE login (user_id INTEGER, token TEXT)")
            pw_hash = discord_bot_core.hash_password("secretpass1")
            conn.execute(
                "INSERT INTO user (user_id, name, password, user_code) VALUES (1, 'Alice', ?, '123456789')",
                (pw_hash,),
            )
            conn.execute("INSERT INTO login (user_id, token) VALUES (1, 'tok1')")
            conn.commit()
        return game_db, map_db

    def test_migrate_legacy_unique_user_id_and_multilink_security(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_db, map_db = self._setup_dbs(directory)
            with sqlite3.connect(map_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE user_mapping (
                        discord_id TEXT NOT NULL,
                        user_id INTEGER NOT NULL UNIQUE,
                        username TEXT NOT NULL,
                        user_code TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (discord_id, user_id),
                        UNIQUE (discord_id, username)
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO user_mapping (discord_id, user_id, username, user_code) VALUES ('1001', 1, 'Alice', '123456789')"
                )
                conn.commit()

            repo = discord_bot_core.BotRepository(game_db, map_db)
            repo.migrate_mapping_schema()
            repo.migrate_mapping_schema()  # idempotent

            with sqlite3.connect(map_db) as conn:
                self.assertFalse(repo._has_single_user_id_unique(conn))
                idxs = {r[1] for r in conn.execute("PRAGMA index_list(user_mapping)").fetchall()}
                self.assertIn("idx_user_mapping_user_id", idxs)

            # Existing owner is backfilled as primary
            self.assertTrue(repo.list_accounts("1001")[0].is_primary)

            # Brute-force lockout after 5 wrong attempts
            for _ in range(discord_bot_core.LINK_MAX_FAILURES):
                with self.assertRaises(discord_bot_core.AuthenticationFailed):
                    repo.link_account("1002", "Alice", "wrongpass1", now_ts=1000)
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.link_account("1002", "Alice", "secretpass1", now_ts=1100)
            # After lockout window passes, link succeeds as secondary
            acc2 = repo.link_account("1002", "Alice", "secretpass1", now_ts=1000 + 1000)
            self.assertFalse(acc2.is_primary)

            # Secondary cannot rename, reset password, or revoke others
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.rename_account("1002", 1, "AliceHack")
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.reset_password("1002", 1, "newpass123")
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.revoke_other_discords("1002", 1)

            # Link 3rd Discord account, reject 4th
            acc3 = repo.link_account("1003", "Alice", "secretpass1")
            self.assertFalse(acc3.is_primary)
            self.assertEqual(repo.count_linked_discords(1), 3)
            with self.assertRaises(discord_bot_core.AccountConflict):
                repo.link_account("1004", "Alice", "secretpass1")

            # Primary renames -> synced to all rows
            repo.rename_account("1001", 1, "AliceNew")
            for did in ("1001", "1002", "1003"):
                self.assertEqual(repo.list_accounts(did)[0].username, "AliceNew")

            # Unlink primary -> oldest secondary promoted to primary
            repo.unlink_account("1001", 1)
            self.assertEqual(repo.count_linked_discords(1), 2)
            promoted = [did for did in ("1002", "1003") if repo.list_accounts(did)[0].is_primary]
            self.assertEqual(len(promoted), 1)
            primary_did = promoted[0]

            # Promoted primary can revoke other Discords and reset password
            removed = repo.revoke_other_discords(primary_did, 1)
            self.assertEqual(removed, 1)
            self.assertEqual(repo.count_linked_discords(1), 1)


class GameFeaturesTests(unittest.TestCase):
    def _create_game_fixture(self, directory: str):
        root = Path(directory)
        game_db = root / "game.db"
        map_db = root / "map.db"
        pw = discord_bot_core.hash_password("secretpass1")
        with sqlite3.connect(game_db) as conn:
            conn.executescript(
                f"""
                CREATE TABLE user (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    password TEXT,
                    join_date TEXT,
                    user_code TEXT,
                    rating_ptt INTEGER,
                    character_id INTEGER,
                    is_skill_sealed INTEGER DEFAULT 0,
                    is_char_uncapped INTEGER DEFAULT 0,
                    is_char_uncapped_override INTEGER DEFAULT 0,
                    is_hide_rating INTEGER DEFAULT 0,
                    song_id TEXT,
                    difficulty INTEGER,
                    score INTEGER,
                    shiny_perfect_count INTEGER,
                    perfect_count INTEGER,
                    near_count INTEGER,
                    miss_count INTEGER,
                    clear_type INTEGER,
                    rating REAL,
                    time_played INTEGER,
                    is_profile_public INTEGER DEFAULT 1
                );
                CREATE TABLE user_char (user_id INTEGER, character_id INTEGER, level INTEGER);
                CREATE TABLE chart (
                    song_id TEXT PRIMARY KEY,
                    name TEXT,
                    rating_pst INTEGER DEFAULT -1,
                    rating_prs INTEGER DEFAULT -1,
                    rating_ftr INTEGER DEFAULT -1,
                    rating_byn INTEGER DEFAULT -1,
                    rating_etr INTEGER DEFAULT -1
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
                    time_played INTEGER,
                    best_clear_type INTEGER,
                    clear_type INTEGER,
                    rating REAL,
                    PRIMARY KEY (user_id, song_id, difficulty)
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
                    clear_type INTEGER,
                    rating REAL,
                    PRIMARY KEY (user_id, r_index)
                );
                INSERT INTO user (user_id, name, password, join_date, user_code, rating_ptt, character_id, song_id, difficulty, score, time_played, is_profile_public)
                VALUES
                    (1, 'Alice', '{pw}', '2026-01-01', '111111111', 1245, 0, 'arcanaeden', 3, 9936371, 1795770000, 1),
                    (2, 'Bob', '{pw}', '2026-01-02', '222222222', 1180, 1, 'grievouslady', 2, 9850000, 1795760000, 1);
                INSERT INTO user_char VALUES (1, 0, 20);
                INSERT INTO chart VALUES
                    ('arcanaeden', 'Arcana Eden', 55, 87, 105, 116, -1),
                    ('cataclysmcry', 'Cataclysm Cry', 65, 88, 106, 118, -10),
                    ('grievouslady', 'Grievous Lady', 65, 93, 111, -1, -1);
                INSERT INTO best_score VALUES
                    (1, 'arcanaeden', 3, 9936371, 1800, 2000, 12, 3, 1795770000, 2, 2, 13.281855),
                    (1, 'grievouslady', 2, 9966880, 1300, 1400, 5, 0, 1795760000, 2, 2, 12.9344),
                    (2, 'arcanaeden', 3, 9850000, 1500, 1900, 40, 20, 1795750000, 1, 1, 12.85),
                    (2, 'grievouslady', 2, 9850000, 1200, 1350, 30, 15, 1795755000, 1, 1, 12.35);
                INSERT INTO recent30 VALUES
                    (1, 0, 1795770000, 'arcanaeden', 3, 9936371, 1800, 2000, 12, 3, 2, 13.281855),
                    (1, 1, 1795760000, 'grievouslady', 2, 9910000, 1200, 1380, 20, 5, 1, 12.65);
                """
            )
            conn.commit()
        return discord_bot_core.BotRepository(game_db, map_db)

    def test_rating_math_matches_live_formula(self) -> None:
        r = discord_bot_core.calculate_play_rating(11.6, 9_936_371)
        self.assertAlmostEqual(r, 13.281855, places=6)
        self.assertEqual(discord_bot_core.calculate_play_rating(11.6, 10_000_000), 13.6)
        needed = discord_bot_core.score_for_target_rating(11.6, 13.281855)
        self.assertEqual(needed, 9_936_371)
        self.assertIsNone(discord_bot_core.score_for_target_rating(11.6, 13.7))

    def test_chart_queries_whatif_progress_random_and_card_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._create_game_fixture(directory)
            repo.migrate_mapping_schema()

            # Invalid constant -10 excluded
            chart, diff_id, cc = repo.resolve_chart("cataclysm")
            self.assertEqual(chart.song_id, "cataclysmcry")
            self.assertEqual(diff_id, 3)
            self.assertAlmostEqual(cc, 11.8)
            self.assertNotIn(4, chart.constants)
            with self.assertRaises(discord_bot_core.ValidationError):
                repo.resolve_chart("cataclysmcry", 4)

            # Recent cards & card PNG rendering
            cards = repo.get_recent_score_cards(1, limit=10)
            self.assertEqual(len(cards), 2)
            self.assertEqual(cards[0].song_title, "Arcana Eden")
            self.assertEqual(cards[0].chart_rank, 1)
            self.assertEqual(cards[1].pb_delta, 9910000 - 9966880)

            png = score_card_renderer.render_score_card(cards[0])
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(io.BytesIO(png)) as im:
                self.assertEqual(im.size, (600, 867))

            # Leaderboard, Top, Whatif, Progress, Compare, Random
            lb = repo.get_chart_leaderboard("arcanaeden", 3, viewer_user_id=2)
            self.assertEqual(lb.entries[0].username, "Alice")
            self.assertIsNotNone(lb.viewer_entry)
            self.assertEqual(lb.viewer_entry.rank, 2)

            top = repo.get_top_scores(1, min_cc=11.5)
            self.assertEqual(top.total_entries, 1)
            self.assertEqual(top.entries[0].song_id, "arcanaeden")

            whatif_sum = repo.get_whatif_summary(1)
            self.assertGreater(whatif_sum.b30_avg, 0.8)
            sim = repo.simulate_whatif_chart(1, "cataclysmcry", 3, target_score=9_900_000)
            self.assertAlmostEqual(sim.simulated_rating, 13.3, places=4)
            self.assertGreater(sim.simulated_b30_delta, 0.0)

            prog = repo.get_progress_summary(1)
            self.assertEqual(prog.total_played, 2)
            self.assertEqual(prog.total_ex_plus, 2)
            self.assertEqual(prog.total_fr, 2)

            comp = repo.compare_scores("arcanaeden", 3, 1, 2)
            self.assertGreater(comp.left_score.score, comp.right_score.score)

            rchart, rdiff, rcc = repo.get_random_chart(min_cc=11.0, max_cc=12.0)
            self.assertGreaterEqual(rcc, 11.0)
            self.assertLessEqual(rcc, 12.0)

            jpg = b30n_generator.render_b30n(repo.game_db_path, 1)
            self.assertTrue(jpg.startswith(b"\xff\xd8\xff"))
            with Image.open(io.BytesIO(jpg)) as b30_im:
                self.assertEqual(b30_im.width, 2000)

            jpg2 = b30n_generator.render_b30n2(repo.game_db_path, 1)
            self.assertTrue(jpg2.startswith(b"\xff\xd8\xff"))
            with Image.open(io.BytesIO(jpg2)) as b30n2_im:
                self.assertEqual(b30n2_im.size, (2560, 1600))


class DefaultAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_account_migration_switch_unlink_and_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_db = root / "game.db"
            map_db = root / "mapping.db"
            pw = discord_bot_core.hash_password("FixturePass99!")
            with sqlite3.connect(game_db) as conn:
                conn.executescript(
                    f"""
                    CREATE TABLE user (
                        user_id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE,
                        password TEXT,
                        join_date TEXT,
                        user_code TEXT UNIQUE,
                        rating_ptt INTEGER,
                        character_id INTEGER,
                        is_profile_public INTEGER DEFAULT 1
                    );
                    INSERT INTO user VALUES
                        (10, 'FirstAcc', '{pw}', '2026-01-01', '101010101', 1200, 0, 1),
                        (20, 'SecondAcc', '{pw}', '2026-01-02', '202020202', 1100, 1, 1);
                    """
                )
                conn.commit()
            # Pre-is_default legacy schema backfill check
            with sqlite3.connect(map_db) as conn:
                conn.executescript(
                    """
                    CREATE TABLE user_mapping (
                        discord_id TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        user_code TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_primary INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (discord_id, user_id),
                        UNIQUE (discord_id, username)
                    );
                    INSERT INTO user_mapping (discord_id, user_id, username, user_code, created_at, is_primary)
                    VALUES ('555', 10, 'FirstAcc', '101010101', '2026-01-01 00:00:00', 1);
                    """
                )
                conn.commit()

            repo = discord_bot_core.BotRepository(game_db, map_db)
            repo.migrate_mapping_schema()
            accounts = repo.list_accounts(555)
            self.assertEqual(len(accounts), 1)
            self.assertTrue(accounts[0].is_default)

            # Linking a second account preserves FirstAcc as default
            second = repo.link_account(555, "SecondAcc", "FixturePass99!")
            self.assertFalse(second.is_default)
            ordered = repo.list_accounts(555)
            self.assertEqual([a.user_id for a in ordered], [10, 20])
            self.assertTrue(ordered[0].is_default)

            # Switch default to SecondAcc by name
            switched = repo.set_default_account_by_name(555, "secondacc")
            self.assertTrue(switched.is_default)
            ordered = repo.list_accounts(555)
            self.assertEqual([a.user_id for a in ordered], [20, 10])
            self.assertTrue(ordered[0].is_default)
            self.assertFalse(ordered[1].is_default)

            # Another Discord user cannot switch a foreign account
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.set_default_account(999, 20)

            # resolve_target_user picks SecondAcc (active default) when no args given
            from types import SimpleNamespace
            fake_bot = SimpleNamespace(repository=repo)
            fake_interaction = SimpleNamespace(user=SimpleNamespace(id=555))
            resolved_uid, is_owner = await discord_bot.resolve_target_user(
                fake_bot, fake_interaction, None, None
            )
            self.assertEqual(resolved_uid, 20)
            self.assertTrue(is_owner)

            # Unlinking the default promotes remaining account
            repo.unlink_account(555, 20)
            remaining = repo.list_accounts(555)
            self.assertEqual([a.user_id for a in remaining], [10])
            self.assertTrue(remaining[0].is_default)


class CommunityApiKeyTests(unittest.TestCase):
    def test_community_key_lifecycle_isolation_and_ban(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_db = root / "game.db"
            map_db = root / "mapping.db"
            with sqlite3.connect(game_db) as conn:
                conn.executescript(
                    "CREATE TABLE user (user_id INTEGER PRIMARY KEY, name TEXT UNIQUE, user_code TEXT UNIQUE);"
                    "INSERT INTO user VALUES (1, 'DevUser', '123456789');"
                )
                conn.commit()
            repo = discord_bot_core.BotRepository(game_db, map_db)
            repo.migrate_mapping_schema()

            # Unlinked user cannot mint a developer key
            with self.assertRaises(discord_bot_core.AccountNotFound):
                repo.issue_community_api_key(777, "app")

            repo.register_mapping(777, 1, "DevUser", "123456789")
            token1, replaced = repo.issue_community_api_key(777, "bot-v1")
            self.assertTrue(token1.startswith("akdev_"))
            self.assertFalse(replaced)
            info = repo.get_community_api_key_info(777)
            self.assertIsNotNone(info)
            self.assertEqual(info["label"], "bot-v1")

            # Admin key rotation preserves community keys; admin revoke only drops admin key
            repo.rotate_external_api_key(999)
            self.assertIsNotNone(repo.get_community_api_key_info(777))
            self.assertTrue(repo.revoke_external_api_key())
            self.assertIsNotNone(repo.get_community_api_key_info(777))

            # Banning revokes key and blocks reissue; unbanning restores
            self.assertTrue(repo.ban_community_api_user(777, 999, "abuse"))
            self.assertIsNone(repo.get_community_api_key_info(777))
            with self.assertRaises(discord_bot_core.PermissionDenied):
                repo.issue_community_api_key(777, "bot-v2")
            self.assertTrue(repo.unban_community_api_user(777))
            token2, _ = repo.issue_community_api_key(777, "bot-v2")
            self.assertNotEqual(token1, token2)
            self.assertTrue(repo.revoke_community_api_key(777))
            self.assertIsNone(repo.get_community_api_key_info(777))


if __name__ == "__main__":
    unittest.main()
