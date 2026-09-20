"""Regression tests for Discord interaction response helpers."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import discord_bot  # noqa: E402
import b30_generator  # noqa: E402


class _Response:
    def __init__(self, done: bool) -> None:
        self._done = done
        self.sent: list[dict] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, **kwargs) -> None:
        if "view" in kwargs and kwargs["view"] is None:
            raise AssertionError("Discord rejects an explicit view=None")
        self.sent.append(kwargs)


class _Followup:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs) -> None:
        if "view" in kwargs and kwargs["view"] is None:
            raise AssertionError("Discord rejects an explicit view=None")
        self.sent.append(kwargs)


class _Interaction:
    def __init__(self, done: bool) -> None:
        self.response = _Response(done)
        self.followup = _Followup()


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
        if discord_id == 200:
            return [type("Account", (), {"user_id": 97})()]
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

    async def test_rejects_two_target_types(self) -> None:
        bot = type("Bot", (), {"repository": _Repository()})()
        interaction = type("Interaction", (), {"user": _User(100)})()

        with self.assertRaises(discord_bot.ValidationError):
            await discord_bot.resolve_target_user(
                bot, interaction, "sample-player", _User(200)
            )


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
