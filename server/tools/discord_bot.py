from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from discord_bot_core import (
    Account,
    AccountConflict,
    AccountNotFound,
    AuthenticationFailed,
    BotCoreError,
    BotRepository,
    PermissionDenied,
    Profile,
    RecentScore,
    ValidationError,
)


LOGGER = logging.getLogger("lygus_bot")
BRAND_COLOR = discord.Color.from_rgb(204, 67, 116)
SUCCESS_COLOR = discord.Color.from_rgb(73, 185, 124)
ERROR_COLOR = discord.Color.from_rgb(218, 68, 83)
ACCOUNT_SETUP_NOTE = "**7.0 setup:** In Akaine, use **Cloud Sync → Download** to receive current unlock and content data."


@dataclass(frozen=True)
class BotSettings:
    game_db_path: Path
    mapping_db_path: Path
    create_user_cli_path: Path
    b30_generator_path: Path
    server_cwd: Path
    log_path: Path

    @classmethod
    def from_environment(cls) -> "BotSettings":
        root = Path(os.environ.get("LYGUS_SERVER_ROOT", Path(__file__).resolve().parents[1]))
        return cls(
            game_db_path=Path(
                os.environ.get("LYGUS_GAME_DB", root / "database" / "arcaea_database.db")
            ),
            mapping_db_path=Path(
                os.environ.get("LYGUS_MAPPING_DB", root / "database" / "discord_bot.db")
            ),
            create_user_cli_path=Path(
                os.environ.get("LYGUS_CREATE_CLI", root / "tools" / "create_user_cli.py")
            ),
            b30_generator_path=Path(
                os.environ.get("LYGUS_B30_GENERATOR", root / "tools" / "b30_generator.py")
            ),
            server_cwd=root,
            log_path=Path(os.environ.get("LYGUS_LOG_PATH", root / "log" / "discord_bot.log")),
        )


def configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    stream = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    stream.setFormatter(formatter)
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.addHandler(stream)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def profile_embed(profile: Profile, title: str = "Akaine Profile") -> discord.Embed:
    embed = discord.Embed(title=title, color=BRAND_COLOR)
    embed.description = f"**{profile.username}**  ·  `{profile.user_code}`"
    embed.add_field(name="Potential", value=f"**{profile.ptt}**", inline=True)
    character = f"#{profile.character_id}"
    if profile.character_level is not None:
        character += f" · Lv.{profile.character_level}"
    embed.add_field(name="Partner", value=character, inline=True)
    embed.add_field(name="Best scores", value=str(profile.best_score_count), inline=True)
    embed.add_field(name="Recent plays", value=str(profile.recent_play_count), inline=True)
    embed.set_footer(text="Lygus · Akaine account service")
    return embed


def recent_embed(username: str, scores: list[RecentScore]) -> discord.Embed:
    embed = discord.Embed(title=f"Recent plays · {username}", color=BRAND_COLOR)
    if not scores:
        embed.description = "No recent plays yet."
        return embed

    for index, score in enumerate(scores, 1):
        value = (
            f"`{score.difficulty}` · **{score.score:,}** · {score.clear_type}\n"
            f"Play rating `{score.rating:.2f}` · P {score.pure_count:,} "
            f"(+{score.shiny_pure_count:,}) / N {score.near_count:,} / M {score.miss_count:,}"
        )
        embed.add_field(name=f"{index}. {score.song_id}", value=value, inline=False)
    embed.set_footer(text="Newest first · up to 5 results")
    return embed


def error_embed(message: str, correlation_id: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(title="Request failed", description=message, color=ERROR_COLOR)
    if correlation_id:
        embed.set_footer(text=f"Reference: {correlation_id}")
    return embed


async def send_ephemeral(
    interaction: discord.Interaction,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
) -> None:
    kwargs = {
        "content": content,
        "embed": embed,
        "ephemeral": True,
    }
    if view is not None:
        kwargs["view"] = view
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


def run_create_cli(settings: BotSettings, username: str, password: str) -> dict:
    process = subprocess.run(
        [sys.executable, str(settings.create_user_cli_path), username, password],
        cwd=settings.server_cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Account helper returned an invalid response.") from error
    if process.returncode != 0 or payload.get("status") != "success":
        raise RuntimeError(payload.get("message") or "Account creation failed.")
    return payload


def run_b30(settings: BotSettings, user_code: str, username: str) -> Path:
    process = subprocess.run(
        [sys.executable, str(settings.b30_generator_path), str(user_code), username],
        cwd=settings.server_cwd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError("B30 generator failed.")
    output = Path(process.stdout.strip())
    if not output.is_file():
        raise RuntimeError("The account does not have enough score data for B30.")
    return output


class LygusBot(discord.Client):
    def __init__(self, settings: BotSettings) -> None:
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.repository = BotRepository(settings.game_db_path, settings.mapping_db_path)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await asyncio.to_thread(self.repository.migrate_mapping_schema)
        synced = await self.tree.sync()
        LOGGER.info("Synced %d global command(s).", len(synced))


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await send_ephemeral(interaction, content="This panel belongs to another Discord user.")
        return False


class CreateAccountModal(discord.ui.Modal, title="Create Akaine account"):
    username = discord.ui.TextInput(
        label="Username",
        placeholder="3-16 letters or digits",
        min_length=3,
        max_length=16,
    )
    password = discord.ui.TextInput(
        label="Password",
        placeholder="8-32 characters",
        min_length=8,
        max_length=32,
    )

    def __init__(self, bot: LygusBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        username = str(self.username.value).strip()
        password = str(self.password.value)
        try:
            payload = await asyncio.to_thread(
                run_create_cli,
                self.bot.settings,
                username,
                password,
            )
            account = await asyncio.to_thread(
                self.bot.repository.register_mapping,
                interaction.user.id,
                int(payload["user_id"]),
                str(payload["username"]),
                str(payload["user_code"]),
            )
            embed = discord.Embed(
                title="Account created",
                description=f"These credentials are shown once. Store them somewhere private.\n\n{ACCOUNT_SETUP_NOTE}",
                color=SUCCESS_COLOR,
            )
            embed.add_field(name="Username", value=f"`{account.username}`", inline=True)
            embed.add_field(name="Password", value=f"||{password}||", inline=True)
            embed.add_field(name="User code", value=f"`{account.user_code}`", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class LinkAccountModal(discord.ui.Modal, title="Link existing account"):
    username = discord.ui.TextInput(label="Username", min_length=3, max_length=16)
    password = discord.ui.TextInput(label="Current password", min_length=8, max_length=32)

    def __init__(self, bot: LygusBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            account = await asyncio.to_thread(
                self.bot.repository.link_account,
                interaction.user.id,
                str(self.username.value),
                str(self.password.value),
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Account linked",
                    description=f"`{account.username}` is now available in `/account`.",
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)


class RenameAccountModal(discord.ui.Modal, title="Rename account"):
    username = discord.ui.TextInput(
        label="New username",
        placeholder="3-16 letters or digits",
        min_length=3,
        max_length=16,
    )

    def __init__(self, bot: LygusBot, user_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            account = await asyncio.to_thread(
                self.bot.repository.rename_account,
                interaction.user.id,
                self.user_id,
                str(self.username.value),
            )
            await interaction.followup.send(
                f"Username changed to `{account.username}`. Use Refresh on `/account`.",
                ephemeral=True,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)


class ResetPasswordModal(discord.ui.Modal, title="Reset password"):
    password = discord.ui.TextInput(label="New password", min_length=8, max_length=32)
    confirmation = discord.ui.TextInput(label="Confirm new password", min_length=8, max_length=32)

    def __init__(self, bot: LygusBot, user_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.password.value != self.confirmation.value:
            await send_ephemeral(interaction, content="The two passwords do not match.")
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await asyncio.to_thread(
                self.bot.repository.reset_password,
                interaction.user.id,
                self.user_id,
                str(self.password.value),
            )
            await interaction.followup.send(
                "Password updated. Existing game sessions were signed out.",
                ephemeral=True,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)


class UnlinkConfirmationView(OwnerView):
    def __init__(self, bot: LygusBot, owner_id: int, account: Account) -> None:
        super().__init__(owner_id, timeout=120)
        self.bot = bot
        self.account = account

    @discord.ui.button(label="Unlink", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await asyncio.to_thread(
                self.bot.repository.unlink_account,
                interaction.user.id,
                self.account.user_id,
            )
            await interaction.response.edit_message(
                content=f"`{self.account.username}` was unlinked. The game account was not deleted.",
                embed=None,
                view=None,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Unlink cancelled.", embed=None, view=None)


class AccountSelect(discord.ui.Select):
    def __init__(self, dashboard: "AccountDashboardView", accounts: list[Account]) -> None:
        self.dashboard = dashboard
        options = [
            discord.SelectOption(
                label=account.username,
                value=str(account.user_id),
                description=f"User code {account.user_code}",
                default=account.user_id == dashboard.selected_user_id,
            )
            for account in accounts[:25]
        ]
        super().__init__(placeholder="Choose an account", options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.dashboard.selected_user_id = int(self.values[0])
        await self.dashboard.refresh(interaction)


class AccountDashboardView(OwnerView):
    def __init__(
        self,
        bot: LygusBot,
        owner_id: int,
        accounts: list[Account],
        selected_user_id: Optional[int] = None,
    ) -> None:
        super().__init__(owner_id)
        self.bot = bot
        self.accounts = accounts
        self.selected_user_id = selected_user_id or (accounts[0].user_id if accounts else None)
        if len(accounts) > 1:
            self.add_item(AccountSelect(self, accounts))
        self._set_account_buttons(bool(accounts))

    def _set_account_buttons(self, enabled: bool) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id in {
                "lygus-profile",
                "lygus-recent",
                "lygus-b30",
                "lygus-rename",
                "lygus-password",
                "lygus-unlink",
            }:
                child.disabled = not enabled

    def selected_account(self) -> Account:
        for account in self.accounts:
            if account.user_id == self.selected_user_id:
                return account
        raise AccountNotFound("Select an account first.")

    async def render(self) -> discord.Embed:
        if not self.accounts:
            return discord.Embed(
                title="Lygus Account Hub",
                description="No linked Akaine account yet. Create one or link an existing account.",
                color=BRAND_COLOR,
            )
        account = self.selected_account()
        profile = await asyncio.to_thread(self.bot.repository.get_profile, account.user_id)
        embed = profile_embed(profile, title="Lygus Account Hub")
        embed.add_field(name="Linked accounts", value=str(len(self.accounts)), inline=True)
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.accounts = await asyncio.to_thread(
            self.bot.repository.list_accounts,
            interaction.user.id,
        )
        if self.selected_user_id not in {item.user_id for item in self.accounts}:
            self.selected_user_id = self.accounts[0].user_id if self.accounts else None
        replacement = AccountDashboardView(
            self.bot,
            interaction.user.id,
            self.accounts,
            self.selected_user_id,
        )
        await interaction.response.edit_message(embed=await replacement.render(), view=replacement)

    @discord.ui.button(
        label="Profile",
        emoji="👤",
        style=discord.ButtonStyle.primary,
        custom_id="lygus-profile",
        row=1,
    )
    async def profile(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        profile = await asyncio.to_thread(self.bot.repository.get_profile, account.user_id)
        await send_ephemeral(interaction, embed=profile_embed(profile))

    @discord.ui.button(
        label="Recent",
        emoji="🕒",
        style=discord.ButtonStyle.primary,
        custom_id="lygus-recent",
        row=1,
    )
    async def recent(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        scores = await asyncio.to_thread(self.bot.repository.get_recent_scores, account.user_id, 5)
        await send_ephemeral(interaction, embed=recent_embed(account.username, scores))

    @discord.ui.button(
        label="B30",
        style=discord.ButtonStyle.primary,
        custom_id="lygus-b30",
        row=1,
    )
    async def b30(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            output = await asyncio.to_thread(
                run_b30,
                self.bot.settings,
                account.user_code,
                account.username,
            )
            await interaction.followup.send(file=discord.File(output), ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(
        label="Rename",
        style=discord.ButtonStyle.secondary,
        custom_id="lygus-rename",
        row=2,
    )
    async def rename(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            RenameAccountModal(self.bot, self.selected_account().user_id)
        )

    @discord.ui.button(
        label="Password",
        style=discord.ButtonStyle.secondary,
        custom_id="lygus-password",
        row=2,
    )
    async def password(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            ResetPasswordModal(self.bot, self.selected_account().user_id)
        )

    @discord.ui.button(
        label="Unlink",
        style=discord.ButtonStyle.danger,
        custom_id="lygus-unlink",
        row=2,
    )
    async def unlink(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        await send_ephemeral(
            interaction,
            content=f"Unlink `{account.username}`? This does not delete the game account.",
            view=UnlinkConfirmationView(self.bot, interaction.user.id, account),
        )

    @discord.ui.button(label="Create", style=discord.ButtonStyle.success, row=3)
    async def create(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CreateAccountModal(self.bot))

    @discord.ui.button(label="Link existing", style=discord.ButtonStyle.success, row=3)
    async def link(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(LinkAccountModal(self.bot))

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=3)
    async def refresh_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.refresh(interaction)


async def handle_interaction_error(interaction: discord.Interaction, error: Exception) -> None:
    if isinstance(error, ValidationError):
        message = str(error)
    elif isinstance(error, AuthenticationFailed):
        message = "Username or password is incorrect."
    elif isinstance(error, PermissionDenied):
        message = "That account is not linked to your Discord user."
    elif isinstance(error, AccountConflict):
        message = str(error)
    elif isinstance(error, AccountNotFound):
        message = str(error)
    else:
        correlation_id = uuid.uuid4().hex[:8]
        LOGGER.exception("Unhandled interaction error [%s]", correlation_id)
        await send_ephemeral(
            interaction,
            embed=error_embed("An internal error occurred.", correlation_id),
        )
        return
    await send_ephemeral(interaction, embed=error_embed(message))


async def resolve_target_user(
    bot: LygusBot,
    interaction: discord.Interaction,
    username: Optional[str],
    discord_profile: Optional[discord.User] = None,
) -> tuple[int, bool]:
    if username and discord_profile:
        raise ValidationError("Choose either an Akaine username or a Discord user, not both.")
    if discord_profile:
        accounts = await asyncio.to_thread(bot.repository.list_accounts, discord_profile.id)
        if not accounts:
            raise AccountNotFound("That Discord user has no linked Akaine account.")
        return accounts[0].user_id, interaction.user.id == discord_profile.id
    if username:
        user_id = await asyncio.to_thread(bot.repository.find_user_id, username)
        try:
            await asyncio.to_thread(bot.repository.get_owned_account, interaction.user.id, user_id)
            return user_id, True
        except PermissionDenied:
            return user_id, False
    accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
    if not accounts:
        raise AccountNotFound("Use `/create` or `/link` first.")
    return accounts[0].user_id, True


def build_bot(settings: BotSettings) -> LygusBot:
    bot = LygusBot(settings)

    @bot.event
    async def on_ready() -> None:
        LOGGER.info("Logged in as %s (%s).", bot.user, bot.user.id if bot.user else "unknown")
        await bot.change_presence(
            activity=discord.Game(name="Akaine · /account"),
            status=discord.Status.online,
        )

    @bot.tree.command(name="account", description="Open your Akaine account dashboard")
    async def account_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
            view = AccountDashboardView(bot, interaction.user.id, accounts)
            await interaction.followup.send(embed=await view.render(), view=view, ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="create", description="Create a new Akaine account")
    async def create_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CreateAccountModal(bot))

    @bot.tree.command(name="link", description="Link an existing Akaine account")
    async def link_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(LinkAccountModal(bot))

    @bot.tree.command(name="profile", description="View an Akaine profile")
    @app_commands.describe(username="Optional Akaine username")
    async def profile_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(bot, interaction, username)
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            await interaction.followup.send(embed=profile_embed(profile), ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="recent", description="View the five latest plays")
    @app_commands.describe(username="Optional Akaine username")
    async def recent_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(bot, interaction, username)
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            scores = await asyncio.to_thread(bot.repository.get_recent_scores, user_id, 5)
            await interaction.followup.send(
                embed=recent_embed(profile.username, scores),
                ephemeral=True,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="b30", description="Generate your or another player's Best 30 image")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user; uses their most recently linked account",
    )
    async def b30_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, _ = await resolve_target_user(
                bot, interaction, username, discord_profile
            )
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            output = await asyncio.to_thread(
                run_b30,
                bot.settings,
                profile.user_code,
                profile.username,
            )
            await interaction.followup.send(file=discord.File(output))
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="help", description="Show Lygus Bot commands")
    async def help_command(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Lygus Bot",
            description="A small account and score companion for Akaine.",
            color=BRAND_COLOR,
        )
        embed.add_field(name="Account", value="`/account` · `/create` · `/link`", inline=False)
        embed.add_field(name="Scores", value="`/profile` · `/recent` · `/b30`", inline=False)
        embed.set_footer(text="Account changes are private and use Discord modals.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="api_key",
        description="Rotate the external read-only API key (administrator only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def api_key_command(interaction: discord.Interaction) -> None:
        token = await asyncio.to_thread(
            bot.repository.rotate_external_api_key, interaction.user.id
        )
        await interaction.response.send_message(
            "New read-only API key (shown once):\n"
            f"`{token}`\n"
            f"Base URL: `{os.environ.get('AKAINE_EXTERNAL_API', 'https://api.example.com/external/v1')}`\n"
            "Running this command again invalidates the previous key.",
            ephemeral=True,
        )

    @bot.tree.command(
        name="api_key_revoke",
        description="Revoke the external read-only API key (administrator only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def api_key_revoke_command(interaction: discord.Interaction) -> None:
        revoked = await asyncio.to_thread(bot.repository.revoke_external_api_key)
        await interaction.response.send_message(
            "Read-only API key revoked." if revoked else "No active API key.",
            ephemeral=True,
        )

    @bot.tree.command(name="sync", description="Synchronize slash commands (administrator only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        synced = await bot.tree.sync()
        await interaction.followup.send(f"Synchronized {len(synced)} command(s).", ephemeral=True)

    @sync_command.error
    async def sync_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await handle_interaction_error(interaction, error)

    @bot.tree.error
    async def tree_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        await handle_interaction_error(interaction, original)

    return bot


def main() -> int:
    settings = BotSettings.from_environment()
    configure_logging(settings.log_path)
    token = os.environ.get("LYGUS_BOT_TOKEN", "").strip()
    if not token:
        LOGGER.error("LYGUS_BOT_TOKEN is not configured.")
        return 2
    bot = build_bot(settings)
    bot.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
