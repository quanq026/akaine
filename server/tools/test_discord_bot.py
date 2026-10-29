"""Regression tests for Discord interaction response helpers."""

import asyncio
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
