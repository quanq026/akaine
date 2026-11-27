from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
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
    ChartInfo,
    ChartLeaderboardPage,
    CompareResult,
    DIFFICULTY_NAMES,
    MAX_DISCORD_LINKS_PER_ACCOUNT,
    PermissionDenied,
    Profile,
    ProgressSummary,
    RankingPage,
    RecentScore,
    ScoreCardData,
    TopScoresPage,
    ValidationError,
    WhatIfChartResult,
    WhatIfSummary,
    difficulty_name,
    format_score_arcaea,
    format_score_commas,
    validate_password,
    validate_username,
)
from score_card_renderer import (
    find_jacket_path,
    find_partner_icon_path,
    render_score_card,
)
from b30n_generator import render_b30n, render_b30n2
from discord_bot_guards import InteractionRateLimiter, b30_slot


LOGGER = logging.getLogger("lygus_bot")
BRAND_COLOR = discord.Color.from_rgb(204, 67, 116)
SUCCESS_COLOR = discord.Color.from_rgb(73, 185, 124)
ERROR_COLOR = discord.Color.from_rgb(218, 68, 83)
INFO_COLOR = discord.Color.from_rgb(108, 134, 232)
ACCOUNT_SETUP_NOTE = (
    "**7.3.1 setup:** In Akaine, use **Cloud Sync -> Download** to receive current unlock and content data."
)
RANKING_PAGE_SIZE = 5
SCORE_LIST_PAGE_SIZE = 10
DISCORD_MENTION_PATTERN = re.compile(r"^<@!?(\d{15,20})>$")

DIFF_CHOICES = [
    app_commands.Choice(name="PST (Past)", value=0),
    app_commands.Choice(name="PRS (Present)", value=1),
    app_commands.Choice(name="FTR (Future)", value=2),
    app_commands.Choice(name="BYD (Beyond)", value=3),
    app_commands.Choice(name="ETR (Eternal)", value=4),
]

_DEFAULT_LIMITER = InteractionRateLimiter()


@dataclass(frozen=True)
class BotSettings:
    game_db_path: Path
    mapping_db_path: Path
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


def _diff_value(difficulty: Optional[app_commands.Choice[int]]) -> Optional[int]:
    if difficulty is None:
        return None
    return int(difficulty.value) if isinstance(difficulty, app_commands.Choice) else int(difficulty)


def _format_cc(constant: Optional[float]) -> str:
    return f"{constant:.1f}" if constant is not None else "?"


def _score_card_file(card: ScoreCardData, png_bytes: bytes) -> discord.File:
    return discord.File(io.BytesIO(png_bytes), filename=f"score_{card.song_id}_{card.difficulty_id}.png")


def _relative_ts_tag(ts_seconds: int) -> str:
    return f"<t:{ts_seconds}:R>" if ts_seconds > 0 else "—"


def profile_embed(profile: Profile, title: str = "Akaine Profile") -> discord.Embed:
    embed, _ = build_profile_payload(profile, title=title)
    return embed


def build_profile_payload(
    profile: Profile, title: str = "Akaine Profile"
) -> tuple[discord.Embed, Optional[discord.File]]:
    embed = discord.Embed(title=title, color=BRAND_COLOR)
    rank_text = f" · Rank `#{profile.server_rank}`" if profile.server_rank else ""
    embed.description = f"**{discord.utils.escape_markdown(profile.username)}** · `{profile.user_code}`{rank_text}"
    embed.add_field(name="Potential", value=f"**{profile.ptt}**", inline=True)
    embed.add_field(
        name="B30 / R10",
        value=f"`{profile.b30_avg:.2f}` / `{profile.r10_avg:.2f}`",
        inline=True,
    )
    character = f"#{profile.character_id}" if profile.character_id is not None else "—"
    if profile.character_level is not None:
        character += f" · Lv.{profile.character_level}"
    embed.add_field(name="Partner", value=character, inline=True)
    embed.add_field(
        name="Milestones",
        value=f"PM `{profile.pm_count}` · FR `{profile.fr_count}` · EX+ `{profile.ex_plus_count}`",
        inline=True,
    )
    embed.add_field(name="Best scores", value=str(profile.best_score_count), inline=True)
    embed.add_field(name="Recent plays", value=str(profile.recent_play_count), inline=True)
    if profile.last_song_title and profile.last_score is not None:
        diff_lbl = difficulty_name(profile.last_difficulty) if profile.last_difficulty is not None else "?"
        embed.add_field(
            name="Latest play",
            value=f"**{profile.last_song_title}** [{diff_lbl}] — `{format_score_arcaea(profile.last_score)}`",
            inline=False,
        )
    embed.set_footer(text="Demiurge · Akaine")

    attachment: Optional[discord.File] = None
    icon_path = find_partner_icon_path(profile.character_id, profile.is_char_uncapped)
    if icon_path is not None:
        attachment = discord.File(icon_path, filename="partner.png")
        embed.set_thumbnail(url="attachment://partner.png")
    return embed, attachment


def recent_embed(username: str, scores: list[RecentScore]) -> discord.Embed:
    embed = discord.Embed(title=f"Recent plays · {username}", color=BRAND_COLOR)
    if not scores:
        embed.description = "No recent plays yet."
        return embed
    for index, score in enumerate(scores, 1):
        title = score.song_title or score.song_id
        cc = f" {score.constant:.1f}" if score.constant else ""
        value = (
            f"`{score.difficulty}{cc}` · **{format_score_arcaea(score.score)}** · {score.clear_type}\n"
            f"Play PTT `{score.rating:.2f}` · P {score.pure_count:,} "
            f"(+{score.shiny_pure_count:,}) / F {score.near_count:,} / L {score.miss_count:,}"
        )
        embed.add_field(name=f"{index}. {title}", value=value, inline=False)
    embed.set_footer(text="Newest first")
    return embed


def ranking_embed(ranking: RankingPage) -> discord.Embed:
    embed = discord.Embed(title="Akaine Ranking", color=BRAND_COLOR)
    if not ranking.entries:
        embed.description = "No players yet."
    else:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        embed.description = "\n".join(
            f"{medals.get(entry.rank, f'`#{entry.rank}`')} "
            f"**{discord.utils.escape_markdown(entry.username)}** · "
            f"Potential `{entry.ptt}`"
            for entry in ranking.entries
        )
    embed.set_footer(
        text=(
            f"Page {ranking.page}/{ranking.page_count} · "
            f"{ranking.total_players} players · {RANKING_PAGE_SIZE} per page"
        )
    )
    return embed


def chart_lb_embed(lb: ChartLeaderboardPage) -> discord.Embed:
    cc_text = _format_cc(lb.constant)
    embed = discord.Embed(
        title=f"Leaderboard · {lb.chart.title} [{difficulty_name(lb.difficulty_id)} {cc_text}]",
        color=BRAND_COLOR,
    )
    if not lb.entries:
        embed.description = "No recorded scores on this chart yet."
    else:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for e in lb.entries:
            prefix = medals.get(e.rank, f"`#{e.rank}`")
            lines.append(
                f"{prefix} **{discord.utils.escape_markdown(e.username)}** — "
                f"`{format_score_arcaea(e.score)}` ({e.grade} · {e.clear_short}) · "
                f"PTT `{e.rating:.2f}` · {_relative_ts_tag(e.time_played)}"
            )
        embed.description = "\n".join(lines)
    footer = f"Page {lb.page}/{lb.page_count} · {lb.total_entries} player(s)"
    if lb.viewer_entry is not None:
        footer += (
            f" · Your rank: #{lb.viewer_entry.rank} "
            f"({format_score_arcaea(lb.viewer_entry.score)})"
        )
    embed.set_footer(text=footer)
    return embed


def top_scores_embed(
    top: TopScoresPage, diff_filter: Optional[int], min_cc: Optional[float]
) -> discord.Embed:
    filters = []
    if diff_filter is not None:
        filters.append(difficulty_name(diff_filter))
    if min_cc is not None:
        filters.append(f"CC≥{min_cc:.1f}")
    filter_lbl = f" ({', '.join(filters)})" if filters else ""
    embed = discord.Embed(
        title=f"Best Scores · {top.username}{filter_lbl}",
        description=f"B30 Avg: **`{top.b30_avg:.4f}`**",
        color=BRAND_COLOR,
    )
    if not top.entries:
        embed.description = f"B30 Avg: **`{top.b30_avg:.4f}`**\nNo scores match this filter."
    else:
        lines = []
        for e in top.entries:
            cc_lbl = _format_cc(e.constant)
            b30_tag = f" `[B30 #{e.b30_rank}]`" if e.b30_rank else ""
            lines.append(
                f"`#{e.rank}` **{discord.utils.escape_markdown(e.song_title)}** "
                f"[{e.difficulty} {cc_lbl}]{b30_tag}\n"
                f"╰ `{format_score_arcaea(e.score)}` · {e.grade} · {e.clear_short} · PTT **`{e.rating:.3f}`**"
            )
        embed.description = f"B30 Avg: **`{top.b30_avg:.4f}`**\n\n" + "\n".join(lines)
    embed.set_footer(text=f"Page {top.page}/{top.page_count} · {top.total_entries} score(s)")
    return embed


def _compare_line(name: str, card: Optional[ScoreCardData]) -> str:
    if card is None:
        return f"**{discord.utils.escape_markdown(name)}**: No recorded PB"
    rank_str = f" · `#{card.chart_rank} LB`" if card.chart_rank else ""
    return (
        f"**{discord.utils.escape_markdown(name)}**{rank_str}\n"
        f"`{format_score_arcaea(card.score)}` · **{card.grade}** · `{card.clear_short}` · "
        f"PTT `{card.rating:.3f}`\n"
        f"PURE `{card.pure_count:,}` (+{card.shiny_pure_count:,}) · "
        f"FAR `{card.near_count:,}` · LOST `{card.miss_count:,}`"
    )


def compare_embed(
    result: CompareResult, reference_card: Optional[ScoreCardData] = None
) -> discord.Embed:
    cc_lbl = _format_cc(result.constant)
    embed = discord.Embed(
        title=f"Compare · {result.chart.title} [{difficulty_name(result.difficulty_id)} {cc_lbl}]",
        color=INFO_COLOR,
    )
    if reference_card is not None:
        left_card = result.left_score
        right_card = reference_card
        left_name = result.left_username
        right_name = f"{reference_card.username} (Displayed)"
    else:
        left_card = result.left_score
        right_card = result.right_score
        left_name = result.left_username
        right_name = result.right_username

    if right_name is None:
        embed.description = _compare_line(left_name, left_card)
    else:
        parts = [_compare_line(left_name, left_card), _compare_line(right_name, right_card)]
        if left_card is not None and right_card is not None:
            diff = left_card.score - right_card.score
            if diff > 0:
                summary = f"**{discord.utils.escape_markdown(left_name)}** leads by **+{diff:,}**"
            elif diff < 0:
                summary = f"**{discord.utils.escape_markdown(right_name)}** leads by **+{-diff:,}**"
            else:
                summary = "Exact score tie!"
            parts.append(summary)
        embed.description = "\n\n".join(parts)
    embed.set_footer(text="Demiurge · Chart Comparison")
    return embed


def whatif_summary_embed(summary: WhatIfSummary) -> discord.Embed:
    embed = discord.Embed(
        title=f"What-If & Farm Guide · {summary.username}",
        color=INFO_COLOR,
    )
    embed.description = (
        f"Profile PTT: **`{summary.ptt}`** · B30 Avg: **`{summary.b30_avg:.4f}`** ({summary.b30_count}/30)\n"
        f"B30 Ceiling `#1`: `{summary.b30_ceiling:.4f}` · Floor `#30`: `{summary.b30_floor:.4f}` · R10 Avg: `{summary.r10_avg:.4f}`\n"
        "Tip: `+0.01 B30` requires `+0.30` play rating above your floor (or current B30 entry)."
    )
    if not summary.recommendations:
        embed.add_field(
            name="Recommended charts",
            value="No obvious improvement targets found yet. Play more charts or specify `/whatif song:<name>`.",
            inline=False,
        )
    else:
        lines = []
        for idx, rec in enumerate(summary.recommendations, 1):
            cur = format_score_arcaea(rec.current_score) if rec.current_score is not None else "Unplayed"
            lines.append(
                f"{idx}. **{discord.utils.escape_markdown(rec.song_title)}** [{rec.difficulty} {rec.constant:.1f}]\n"
                f"   `{cur}` -> **`{format_score_arcaea(rec.target_score)}`** "
                f"(PTT `{rec.projected_rating:.2f}`, B30 **+{rec.b30_gain:.4f}**)"
            )
        embed.add_field(name="Top 5 PTT farm targets", value="\n".join(lines), inline=False)
    return embed


def whatif_chart_embed(res: WhatIfChartResult) -> discord.Embed:
    embed = discord.Embed(
        title=f"What-If · {res.chart.title} [{difficulty_name(res.difficulty_id)} {res.constant:.1f}]",
        color=INFO_COLOR,
    )
    pb_txt = (
        f"`{format_score_arcaea(res.current_pb)}` (`{res.current_rating:.4f}`)"
        if res.current_pb is not None
        else "Unplayed"
    )
    lines = [
        f"Player: **{discord.utils.escape_markdown(res.username)}** · B30 Avg: `{res.b30_avg:.4f}` · Floor: `{res.b30_floor:.4f}`",
        f"Current PB: {pb_txt} · Max possible PTT: `{res.constant + 2.0:.2f}` (PM)",
        "Enter B30 score: "
        + (f"`{format_score_arcaea(res.score_to_enter_b30)}`" if res.score_to_enter_b30 is not None else "Not reachable"),
    ]
    milestone_lines = []
    for label, needed in res.milestones:
        milestone_lines.append(
            f"• **{label} B30**: "
            + (f"`{format_score_arcaea(needed)}`" if needed is not None else "Exceeds PM (`10'000'000`)")
        )
    embed.description = "\n".join(lines)
    embed.add_field(name="Score targets on this chart", value="\n".join(milestone_lines), inline=False)
    if res.simulated_score is not None and res.simulated_rating is not None and res.simulated_new_b30 is not None:
        delta = res.simulated_b30_delta or 0.0
        embed.add_field(
            name=f"Simulation at {format_score_arcaea(res.simulated_score)}",
            value=(
                f"Play PTT: **`{res.simulated_rating:.4f}`**\n"
                f"New B30 Avg: **`{res.simulated_new_b30:.4f}`** (`{delta:+.4f}`)"
            ),
            inline=False,
        )
    return embed


def progress_embed(prog: ProgressSummary) -> discord.Embed:
    diff_lbl = f" · {difficulty_name(prog.difficulty_filter)}" if prog.difficulty_filter is not None else " · All Difficulties"
    embed = discord.Embed(
        title=f"Clear Progress · {prog.username}{diff_lbl}",
        color=BRAND_COLOR,
    )
    if not prog.buckets:
        embed.description = "No chart data available."
        return embed
    rows = ["Tier | Played/Tot | Clr | EX+ |  FR |  PM", "-----+------------+-----+-----+-----+----"]
    for b in prog.buckets:
        play_col = f"{b.played}/{b.total_charts}"
        rows.append(
            f"{b.label:<4} | {play_col:>10} | {b.cleared:>3} | {b.ex_plus_count:>3} | {b.fr_count:>3} | {b.pm_count:>3}"
        )
    embed.description = "```text\n" + "\n".join(rows) + "\n```"
    embed.set_footer(
        text=f"Total: {prog.total_played} played · {prog.total_ex_plus} EX+ · {prog.total_fr} FR · {prog.total_pm} PM"
    )
    return embed


def build_song_payload(info: ChartInfo) -> tuple[discord.Embed, Optional[discord.File]]:
    embed = discord.Embed(title=info.title, color=BRAND_COLOR)
    const_lines = [
        f"**{difficulty_name(d)}**: `{cc:.1f}`"
        for d, cc in sorted(info.constants.items())
    ]
    embed.description = (
        f"Song ID: `{info.song_id}`\n\n"
        + (" · ".join(const_lines) if const_lines else "No chart constants recorded.")
    )
    embed.add_field(name="Server plays", value=str(info.play_count), inline=True)
    if info.top_score is not None and info.top_player:
        top_diff = difficulty_name(info.top_difficulty) if info.top_difficulty is not None else "?"
        embed.add_field(
            name=f"#1 [{top_diff}]",
            value=f"**{discord.utils.escape_markdown(info.top_player)}** · `{format_score_arcaea(info.top_score)}`",
            inline=True,
        )
    jfile: Optional[discord.File] = None
    jpath = find_jacket_path(info.song_id)
    if jpath is not None:
        ext = jpath.suffix or ".jpg"
        jfile = discord.File(jpath, filename=f"jacket{ext}")
        embed.set_thumbnail(url=f"attachment://jacket{ext}")
    return embed, jfile


def build_random_payload(
    chart: ChartInfo, diff_id: int, constant: float, caller_pb: Optional[ScoreCardData]
) -> tuple[discord.Embed, Optional[discord.File]]:
    embed = discord.Embed(
        title=f"Random Chart · {chart.title}",
        description=f"`{difficulty_name(diff_id)} {constant:.1f}` · ID: `{chart.song_id}`",
        color=BRAND_COLOR,
    )
    if caller_pb is not None:
        rank_txt = f" · `#{caller_pb.chart_rank} LB`" if caller_pb.chart_rank else ""
        embed.add_field(
            name=f"Your PB ({caller_pb.username})",
            value=f"`{format_score_arcaea(caller_pb.score)}` ({caller_pb.grade} · {caller_pb.clear_short}){rank_txt}",
            inline=False,
        )
    else:
        embed.add_field(name="Your PB", value="Unplayed on this chart.", inline=False)
    jfile: Optional[discord.File] = None
    jpath = find_jacket_path(chart.song_id)
    if jpath is not None:
        ext = jpath.suffix or ".jpg"
        jfile = discord.File(jpath, filename=f"jacket{ext}")
        embed.set_thumbnail(url=f"attachment://jacket{ext}")
    return embed, jfile


def help_embed_for_category(category: str) -> discord.Embed:
    if category == "scores":
        embed = discord.Embed(title="Demiurge · Play & Scores", color=BRAND_COLOR)
        embed.add_field(
            name="/rs · /recent",
            value="Rich recent score card (up to 30 plays) with Prev/Next, Compare, Chart LB, and B30 buttons.",
            inline=False,
        )
        embed.add_field(
            name="/score <song> [diff]",
            value="Render your (or another player's) Personal Best card for any official or fan chart.",
            inline=False,
        )
        embed.add_field(
            name="/compare [song] [diff] [player]",
            value="Compare scores on a chart. Leave `song` blank to auto-use the latest chart posted in chat.",
            inline=False,
        )
        embed.add_field(
            name="/b30 · /b30n · /b30n2 · /profile",
            value="Classic `/b30`, portrait `/b30n` (B30+Overflow), landscape 16:10 `/b30n2`, and profile summary.",
            inline=False,
        )
        return embed
    if category == "ptt":
        embed = discord.Embed(title="Demiurge · PTT & Progress", color=INFO_COLOR)
        embed.add_field(
            name="/whatif [song] [diff] [target_score]",
            value="Analyze B30 floor/ceiling + top 5 farm charts, or simulate exact score targets for `+0.01/+0.02/+0.05` B30.",
            inline=False,
        )
        embed.add_field(
            name="/top [diff] [min_cc]",
            value="Browse your Best scores with pagination and difficulty / constant filters.",
            inline=False,
        )
        embed.add_field(
            name="/progress [diff]",
            value="View clear / EX+ / FR / PM breakdown across level buckets (`≤7+` through `12`).",
            inline=False,
        )
        return embed
    if category == "charts":
        embed = discord.Embed(title="Demiurge · Charts & Leaderboards", color=BRAND_COLOR)
        embed.add_field(
            name="/lb <song> [diff]",
            value="Server-wide leaderboard for any official or fan chart, with difficulty switcher & your rank.",
            inline=False,
        )
        embed.add_field(
            name="/song <song>",
            value="Look up chart constants across PST/PRS/FTR/BYD/ETR, play count, and `#1` holder.",
            inline=False,
        )
        embed.add_field(
            name="/random [min_cc] [max_cc] [diff]",
            value="Pick a random chart in your target constant range with a Roll Again button.",
            inline=False,
        )
        embed.add_field(name="/ranking", value="Server Potential leaderboard.", inline=False)
        return embed
    if category == "account":
        embed = discord.Embed(title="Demiurge · Account & Security", color=SUCCESS_COLOR)
        embed.add_field(
            name="/account · /default · /create · /link",
            value=(
                "Create or manage up to 3 linked Discord accounts per Akaine account.\n"
                "• **Default account** sets which account quick commands (`/rs`, `/b30n`, `/profile`, ...) use (`⭐ Set Default` in `/account` or `/default <account>`).\n"
                "• **Primary link** controls Rename, Password reset, and Remove other Discords.\n"
                "• **Brute-force lockout** protects `/link` after 5 failed attempts.\n"
                "• **Security alerts** DM existing linked Discord owners whenever a new Discord links."
            ),
            inline=False,
        )
        embed.set_footer(text=ACCOUNT_SETUP_NOTE)
        return embed

    embed = discord.Embed(
        title="Demiurge · Akaine Companion",
        description="Choose a category below to view commands.",
        color=BRAND_COLOR,
    )
    embed.add_field(
        name="Play & Scores",
        value="`/rs` · `/recent` · `/score` · `/compare` · `/b30` · `/b30n` · `/b30n2` · `/profile`",
        inline=False,
    )
    embed.add_field(
        name="PTT & Progress",
        value="`/whatif` · `/top` · `/progress`",
        inline=False,
    )
    embed.add_field(
        name="Charts & Leaderboards",
        value="`/lb` · `/song` · `/random` · `/ranking`",
        inline=False,
    )
    embed.add_field(
        name="Account",
        value="`/account` · `/default` · `/create` · `/link`",
        inline=False,
    )
    embed.set_footer(text="Demiurge · Use the dropdown menu for detailed command usage.")
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
    file: Optional[discord.File] = None,
) -> None:
    kwargs: dict = {
        "content": content,
        "embed": embed,
        "ephemeral": True,
    }
    if view is not None:
        kwargs["view"] = view
    if file is not None:
        kwargs["file"] = file
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


def run_b30(settings: BotSettings, user_code: str, username: str) -> Path:
    if not b30_slot.acquire(blocking=False):
        raise ValidationError("B30 is busy. Please try again shortly.")
    try:
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
    finally:
        b30_slot.release()


async def _anti_raid(interaction: discord.Interaction, action: str = "interaction") -> bool:
    if getattr(interaction, "type", None) == discord.InteractionType.autocomplete:
        return True
    limiter = getattr(getattr(interaction, "client", None), "interaction_limiter", None) or _DEFAULT_LIMITER
    if limiter.admit(interaction.user.id, action):
        return True
    await send_ephemeral(interaction, content="Too many requests. Please wait before trying again.")
    return False


anti_raid = _anti_raid


class GuardedModal(discord.ui.Modal):
    rate_action = "interaction"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _anti_raid(interaction, self.rate_action)


class LygusBot(discord.Client):
    def __init__(self, settings: BotSettings) -> None:
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.repository = BotRepository(settings.game_db_path, settings.mapping_db_path)
        self.interaction_limiter = InteractionRateLimiter()
        self.tree = app_commands.CommandTree(self)
        self.tree.interaction_check = _anti_raid
        self.channel_last_chart: OrderedDict[int, tuple[str, int]] = OrderedDict()

    def remember_chart(self, channel_id: Optional[int], song_id: str, difficulty_id: int) -> None:
        if channel_id is None:
            return
        cid = int(channel_id)
        if cid in self.channel_last_chart:
            self.channel_last_chart.move_to_end(cid)
        self.channel_last_chart[cid] = (str(song_id), int(difficulty_id))
        while len(self.channel_last_chart) > 500:
            self.channel_last_chart.popitem(last=False)

    async def setup_hook(self) -> None:
        await asyncio.to_thread(self.repository.migrate_mapping_schema)
        self.tree.interaction_check = _anti_raid
        synced = await self.tree.sync()
        LOGGER.info("Synced %d global command(s).", len(synced))


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return await _anti_raid(interaction)
        await send_ephemeral(interaction, content="This panel belongs to another Discord user.")
        return False


class GuardedView(discord.ui.View):
    def __init__(self, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _anti_raid(interaction)


async def _resolve_viewer_user_id(bot: LygusBot, discord_id: int) -> Optional[int]:
    accounts = await asyncio.to_thread(bot.repository.list_accounts, discord_id)
    return accounts[0].user_id if accounts else None


async def _send_chart_lb(
    bot: LygusBot,
    interaction: discord.Interaction,
    song_id: str,
    diff_id: Optional[int],
    *,
    ephemeral: bool = False,
) -> None:
    viewer_id = await _resolve_viewer_user_id(bot, interaction.user.id)
    lb = await asyncio.to_thread(
        bot.repository.get_chart_leaderboard,
        song_id,
        diff_id,
        page=1,
        page_size=SCORE_LIST_PAGE_SIZE,
        viewer_user_id=viewer_id,
    )
    bot.remember_chart(interaction.channel_id, lb.chart.song_id, lb.difficulty_id)
    view = ChartLeaderboardView(bot, interaction.user.id, lb, viewer_id)
    await interaction.followup.send(embed=chart_lb_embed(lb), view=view, ephemeral=ephemeral)


async def _send_compare_against_card(
    bot: LygusBot, interaction: discord.Interaction, card: ScoreCardData
) -> None:
    caller_accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
    if not caller_accounts:
        raise AccountNotFound("Use `/create` or `/link` first.")
    caller_uid = caller_accounts[0].user_id
    res = await asyncio.to_thread(
        bot.repository.compare_scores, card.song_id, card.difficulty_id, caller_uid, None
    )
    bot.remember_chart(interaction.channel_id, res.chart.song_id, res.difficulty_id)
    ref = None if caller_uid_matches(caller_accounts[0].username, card.username) else card
    await interaction.followup.send(embed=compare_embed(res, reference_card=ref))


def caller_uid_matches(caller_username: str, card_username: str) -> bool:
    return caller_username.lower() == card_username.lower()


async def _send_caller_score_card(
    bot: LygusBot,
    interaction: discord.Interaction,
    song_id: str,
    diff_id: int,
) -> None:
    caller_accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
    if not caller_accounts:
        raise AccountNotFound("Use `/create` or `/link` first.")
    card = await asyncio.to_thread(
        bot.repository.get_user_chart_score, caller_accounts[0].user_id, song_id, diff_id
    )
    png = await asyncio.to_thread(render_score_card, card)
    bot.remember_chart(interaction.channel_id, card.song_id, card.difficulty_id)
    view = ScoreCardView(bot, interaction.user.id, card, caller_accounts[0].user_id)
    await interaction.followup.send(file=_score_card_file(card, png), view=view)


class RecentScoreView(GuardedView):
    def __init__(
        self,
        bot: LygusBot,
        owner_id: int,
        target_user_id: int,
        cards: list[ScoreCardData],
        index: int = 0,
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.target_user_id = target_user_id
        self.cards = cards
        self.index = max(0, min(index, len(cards) - 1))
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "demiurge-rs-prev":
                    child.disabled = self.index <= 0
                elif child.custom_id == "demiurge-rs-next":
                    child.disabled = self.index >= len(cards) - 1

    @property
    def current_card(self) -> ScoreCardData:
        return self.cards[self.index]

    async def _turn_page(self, interaction: discord.Interaction, new_index: int) -> None:
        if interaction.user.id != self.owner_id:
            await send_ephemeral(interaction, content="Use `/rs` to browse your own recent plays.")
            return
        await interaction.response.defer()
        self.index = max(0, min(new_index, len(self.cards) - 1))
        card = self.current_card
        png = await asyncio.to_thread(render_score_card, card)
        self.bot.remember_chart(interaction.channel_id, card.song_id, card.difficulty_id)
        replacement = RecentScoreView(
            self.bot, self.owner_id, self.target_user_id, self.cards, self.index
        )
        await interaction.edit_original_response(
            attachments=[_score_card_file(card, png)], view=replacement
        )

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.secondary, custom_id="demiurge-rs-prev")
    async def prev_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._turn_page(interaction, self.index - 1)

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.secondary, custom_id="demiurge-rs-next")
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._turn_page(interaction, self.index + 1)

    @discord.ui.button(label="Compare", emoji="⚔", style=discord.ButtonStyle.primary)
    async def compare_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_compare_against_card(self.bot, interaction, self.current_card)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Chart LB", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def lb_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_chart_lb(
                self.bot, interaction, self.current_card.song_id, self.current_card.difficulty_id
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="B30", emoji="📊", style=discord.ButtonStyle.secondary)
    async def b30_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            profile = await asyncio.to_thread(self.bot.repository.get_profile, self.target_user_id)
            output = await asyncio.to_thread(
                run_b30, self.bot.settings, profile.user_code, profile.username
            )
            await interaction.followup.send(file=discord.File(output))
        except Exception as error:
            await handle_interaction_error(interaction, error)


class ScoreCardView(GuardedView):
    def __init__(
        self, bot: LygusBot, owner_id: int, card: ScoreCardData, target_user_id: int
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.card = card
        self.target_user_id = target_user_id

    @discord.ui.button(label="Compare", emoji="⚔", style=discord.ButtonStyle.primary)
    async def compare_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_compare_against_card(self.bot, interaction, self.card)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Chart LB", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def lb_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_chart_lb(
                self.bot, interaction, self.card.song_id, self.card.difficulty_id
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Song Info", emoji="ℹ", style=discord.ButtonStyle.secondary)
    async def info_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            info = await asyncio.to_thread(self.bot.repository.get_chart_info, self.card.song_id)
            embed, jfile = build_song_payload(info)
            view = SongInfoView(self.bot, info, self.card.difficulty_id)
            if jfile is not None:
                await interaction.followup.send(embed=embed, file=jfile, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class ChartDiffSelect(discord.ui.Select):
    def __init__(self, lb_view: "ChartLeaderboardView") -> None:
        self.lb_view = lb_view
        options = [
            discord.SelectOption(
                label=f"{difficulty_name(diff_id)} {cc:.1f}",
                value=str(diff_id),
                default=(diff_id == lb_view.lb.difficulty_id),
            )
            for diff_id, cc in sorted(lb_view.lb.chart.constants.items())
        ]
        super().__init__(placeholder="Switch difficulty", options=options[:25], row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.lb_view.show_page(interaction, 1, diff_id=int(self.values[0]))


class ChartLeaderboardView(GuardedView):
    def __init__(
        self,
        bot: LygusBot,
        owner_id: int,
        lb: ChartLeaderboardPage,
        viewer_user_id: Optional[int],
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.lb = lb
        self.viewer_user_id = viewer_user_id
        if len(lb.chart.constants) > 1:
            self.add_item(ChartDiffSelect(self))
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "demiurge-lb-prev":
                    child.disabled = lb.page <= 1
                elif child.custom_id == "demiurge-lb-next":
                    child.disabled = lb.page >= lb.page_count

    async def show_page(
        self, interaction: discord.Interaction, page: int, *, diff_id: Optional[int] = None
    ) -> None:
        target_diff = self.lb.difficulty_id if diff_id is None else diff_id
        viewer_id = await _resolve_viewer_user_id(self.bot, interaction.user.id)
        updated = await asyncio.to_thread(
            self.bot.repository.get_chart_leaderboard,
            self.lb.chart.song_id,
            target_diff,
            page=page,
            page_size=SCORE_LIST_PAGE_SIZE,
            viewer_user_id=viewer_id,
        )
        self.bot.remember_chart(interaction.channel_id, updated.chart.song_id, updated.difficulty_id)
        replacement = ChartLeaderboardView(self.bot, self.owner_id, updated, viewer_id)
        await interaction.response.edit_message(embed=chart_lb_embed(updated), view=replacement)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="demiurge-lb-prev", row=1)
    async def prev_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.show_page(interaction, self.lb.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="demiurge-lb-next", row=1)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.show_page(interaction, self.lb.page + 1)


class TopScoresView(OwnerView):
    def __init__(
        self,
        bot: LygusBot,
        owner_id: int,
        target_user_id: int,
        top: TopScoresPage,
        diff_filter: Optional[int],
        min_cc: Optional[float],
    ) -> None:
        super().__init__(owner_id)
        self.bot = bot
        self.target_user_id = target_user_id
        self.top = top
        self.diff_filter = diff_filter
        self.min_cc = min_cc
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "demiurge-top-prev":
                    child.disabled = top.page <= 1
                elif child.custom_id == "demiurge-top-next":
                    child.disabled = top.page >= top.page_count

    async def show_page(self, interaction: discord.Interaction, page: int) -> None:
        updated = await asyncio.to_thread(
            self.bot.repository.get_top_scores,
            self.target_user_id,
            difficulty=self.diff_filter,
            min_cc=self.min_cc,
            page=page,
            page_size=SCORE_LIST_PAGE_SIZE,
        )
        replacement = TopScoresView(
            self.bot,
            self.owner_id,
            self.target_user_id,
            updated,
            self.diff_filter,
            self.min_cc,
        )
        await interaction.response.edit_message(
            embed=top_scores_embed(updated, self.diff_filter, self.min_cc), view=replacement
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="demiurge-top-prev")
    async def prev_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.show_page(interaction, self.top.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="demiurge-top-next")
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.show_page(interaction, self.top.page + 1)


class SongInfoView(GuardedView):
    def __init__(self, bot: LygusBot, info: ChartInfo, default_diff: int) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.info = info
        self.default_diff = default_diff

    @discord.ui.button(label="Chart LB", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def lb_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_chart_lb(self.bot, interaction, self.info.song_id, self.default_diff)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="My Score", emoji="⚔", style=discord.ButtonStyle.primary)
    async def my_score_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_caller_score_card(self.bot, interaction, self.info.song_id, self.default_diff)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class RandomChartView(GuardedView):
    def __init__(
        self,
        bot: LygusBot,
        owner_id: int,
        chart: ChartInfo,
        diff_id: int,
        min_cc: float,
        max_cc: float,
        diff_filter: Optional[int],
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.chart = chart
        self.diff_id = diff_id
        self.min_cc = min_cc
        self.max_cc = max_cc
        self.diff_filter = diff_filter

    @discord.ui.button(label="Roll Again", emoji="🎲", style=discord.ButtonStyle.primary)
    async def reroll_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await send_ephemeral(interaction, content="Run `/random` to roll your own chart.")
            return
        await interaction.response.defer()
        try:
            chart, diff_id, const = await asyncio.to_thread(
                self.bot.repository.get_random_chart,
                min_cc=self.min_cc,
                max_cc=self.max_cc,
                difficulty=self.diff_filter,
            )
            viewer_uid = await _resolve_viewer_user_id(self.bot, interaction.user.id)
            caller_pb: Optional[ScoreCardData] = None
            if viewer_uid is not None:
                try:
                    caller_pb = await asyncio.to_thread(
                        self.bot.repository.get_user_chart_score, viewer_uid, chart.song_id, diff_id
                    )
                except AccountNotFound:
                    caller_pb = None
            self.bot.remember_chart(interaction.channel_id, chart.song_id, diff_id)
            embed, jfile = build_random_payload(chart, diff_id, const, caller_pb)
            replacement = RandomChartView(
                self.bot, self.owner_id, chart, diff_id, self.min_cc, self.max_cc, self.diff_filter
            )
            kwargs: dict = {"embed": embed, "view": replacement}
            kwargs["attachments"] = [jfile] if jfile is not None else []
            await interaction.edit_original_response(**kwargs)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Chart LB", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def lb_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_chart_lb(self.bot, interaction, self.chart.song_id, self.diff_id)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="My Score", emoji="⚔", style=discord.ButtonStyle.secondary)
    async def my_score_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_caller_score_card(self.bot, interaction, self.chart.song_id, self.diff_id)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, current: str = "overview") -> None:
        options = [
            discord.SelectOption(label="Overview", value="overview", default=(current == "overview")),
            discord.SelectOption(label="Play & Scores", value="scores", default=(current == "scores")),
            discord.SelectOption(label="PTT & Progress", value="ptt", default=(current == "ptt")),
            discord.SelectOption(label="Charts & Leaderboards", value="charts", default=(current == "charts")),
            discord.SelectOption(label="Account & Security", value="account", default=(current == "account")),
        ]
        super().__init__(placeholder="Browse command categories", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        await interaction.response.edit_message(
            embed=help_embed_for_category(choice), view=HelpMenuView(interaction.user.id, choice)
        )


class HelpMenuView(OwnerView):
    def __init__(self, owner_id: int, current: str = "overview") -> None:
        super().__init__(owner_id)
        self.add_item(HelpCategorySelect(current))


class RankingView(OwnerView):
    def __init__(self, bot: LygusBot, owner_id: int, ranking: RankingPage) -> None:
        super().__init__(owner_id)
        self.bot = bot
        self.ranking = ranking
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "lygus-ranking-previous":
                child.disabled = ranking.page <= 1
            elif child.custom_id == "lygus-ranking-next":
                child.disabled = ranking.page >= ranking.page_count

    async def show_page(self, interaction: discord.Interaction, page: int) -> None:
        ranking = await asyncio.to_thread(
            self.bot.repository.get_ranking_page,
            page,
            RANKING_PAGE_SIZE,
        )
        replacement = RankingView(self.bot, interaction.user.id, ranking)
        await interaction.response.edit_message(
            embed=ranking_embed(ranking),
            view=replacement,
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary,
        custom_id="lygus-ranking-previous",
    )
    async def previous_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.show_page(interaction, self.ranking.page - 1)

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary,
        custom_id="lygus-ranking-next",
    )
    async def next_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.show_page(interaction, self.ranking.page + 1)


async def _notify_existing_discord_links(
    bot: LygusBot,
    account: Account,
    new_linker: discord.abc.User,
) -> None:
    try:
        other_ids = await asyncio.to_thread(
            bot.repository.list_linked_discord_ids, account.user_id, new_linker.id
        )
    except Exception:
        return
    if not other_ids:
        return

    alert_embed = discord.Embed(
        title="Security alert · New Discord linked",
        description=(
            f"Discord user **{discord.utils.escape_markdown(str(new_linker))}** (`{new_linker.id}`) "
            f"just linked to your Akaine account **`{account.username}`** (`{account.user_code}`)."
        ),
        color=ERROR_COLOR,
    )
    alert_embed.add_field(
        name="Was this not you?",
        value=(
            "Open `/account` on your **Primary** Discord link and click **Remove others** or **Password** reset "
            "immediately to kick all other Discord links and game sessions."
        ),
        inline=False,
    )
    for did in other_ids:
        try:
            user = bot.get_user(int(did)) or await bot.fetch_user(int(did))
            if user is not None:
                await user.send(embed=alert_embed)
        except Exception:
            LOGGER.info("Could not DM security alert to Discord ID %s.", did)


class CreateAccountModal(GuardedModal, title="Create Akaine account"):
    rate_action = "create"

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
            account = await asyncio.to_thread(
                self.bot.repository.create_account,
                interaction.user.id,
                username,
                password,
            )
            default_note = (
                "Active **⭐ Default** for quick commands."
                if account.is_default
                else "Use `/default` or `/account` to set as your default."
            )
            embed = discord.Embed(
                title="Account created",
                description=f"These credentials are shown once. Store them somewhere private.\n{default_note}\n\n{ACCOUNT_SETUP_NOTE}",
                color=SUCCESS_COLOR,
            )
            embed.add_field(name="Username", value=f"`{account.username}`", inline=True)
            embed.add_field(name="Password", value=f"||{password}||", inline=True)
            embed.add_field(name="User code", value=f"`{account.user_code}`", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class LinkAccountModal(GuardedModal, title="Link existing account"):
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
            role_note = "Primary" if account.is_primary else "Secondary (view & play commands)"
            default_note = (
                "Active **⭐ Default** for quick commands."
                if account.is_default
                else "Use `/default` or `/account` to set as your default."
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Account linked",
                    description=f"`{account.username}` is now available in `/account` as **{role_note}**.\n{default_note}",
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
            await _notify_existing_discord_links(self.bot, account, interaction.user)
        except Exception as error:
            await handle_interaction_error(interaction, error)


class RenameAccountModal(GuardedModal, title="Rename account"):
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


class ResetPasswordModal(GuardedModal, title="Reset password"):
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
            unlinked_others = await asyncio.to_thread(
                self.bot.repository.reset_password,
                interaction.user.id,
                self.user_id,
                str(self.password.value),
            )
            if unlinked_others > 0:
                message = (
                    "Password updated. Existing game sessions were signed out and "
                    f"{unlinked_others} other linked Discord account(s) were unlinked."
                )
            else:
                message = "Password updated. Existing game sessions were signed out."
            await interaction.followup.send(message, ephemeral=True)
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


class RevokeOthersConfirmationView(OwnerView):
    def __init__(self, bot: LygusBot, owner_id: int, account: Account) -> None:
        super().__init__(owner_id, timeout=120)
        self.bot = bot
        self.account = account

    @discord.ui.button(label="Remove other Discords", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            removed = await asyncio.to_thread(
                self.bot.repository.revoke_other_discords,
                interaction.user.id,
                self.account.user_id,
            )
            await interaction.response.edit_message(
                content=f"Removed {removed} other linked Discord account(s) from `{self.account.username}`.",
                embed=None,
                view=None,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


class AccountSelect(discord.ui.Select):
    def __init__(self, dashboard: "AccountDashboardView", accounts: list[Account]) -> None:
        self.dashboard = dashboard
        options = [
            discord.SelectOption(
                label=account.username,
                value=str(account.user_id),
                emoji="⭐" if account.is_default else None,
                description=(
                    f"{'Default · ' if account.is_default else ''}"
                    f"{'Primary' if account.is_primary else 'Secondary'} · {account.user_code}"
                )[:100],
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
        linked_counts: Optional[dict[int, int]] = None,
    ) -> None:
        super().__init__(owner_id)
        self.bot = bot
        self.accounts = accounts
        self.selected_user_id = selected_user_id or (accounts[0].user_id if accounts else None)
        self.linked_counts = linked_counts or {}
        if len(accounts) > 1:
            self.add_item(AccountSelect(self, accounts))
        self._set_account_buttons()

    def _set_account_buttons(self) -> None:
        has_accounts = bool(self.accounts)
        selected: Optional[Account] = None
        if has_accounts:
            for item in self.accounts:
                if item.user_id == self.selected_user_id:
                    selected = item
                    break
        is_primary = bool(selected and selected.is_primary)
        is_default = bool(selected and selected.is_default)
        other_links = self.linked_counts.get(selected.user_id, 1) > 1 if selected else False

        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id in {"lygus-profile", "lygus-recent", "lygus-b30", "lygus-b30n", "lygus-unlink"}:
                child.disabled = not has_accounts
            elif child.custom_id == "lygus-set-default":
                child.disabled = not has_accounts or is_default
                child.label = "Default ✓" if is_default else "Set Default"
            elif child.custom_id in {"lygus-rename", "lygus-password"}:
                child.disabled = not (has_accounts and is_primary)
            elif child.custom_id == "lygus-revoke-others":
                child.disabled = not (has_accounts and is_primary and other_links)

    def selected_account(self) -> Account:
        for account in self.accounts:
            if account.user_id == self.selected_user_id:
                return account
        raise AccountNotFound("Select an account first.")

    async def render(self) -> tuple[discord.Embed, Optional[discord.File]]:
        if not self.accounts:
            embed = discord.Embed(
                title="Demiurge Account Hub",
                description="No linked Akaine account yet. Create one or link an existing account.",
                color=BRAND_COLOR,
            )
            return embed, None
        account = self.selected_account()
        profile = await asyncio.to_thread(self.bot.repository.get_profile, account.user_id)
        linked_discords = self.linked_counts.get(account.user_id)
        if linked_discords is None:
            linked_discords = await asyncio.to_thread(
                self.bot.repository.count_linked_discords, account.user_id
            )
        embed, partner_file = build_profile_payload(profile, title="Demiurge Account Hub")
        embed.add_field(
            name="Link role",
            value="Primary (owner)" if account.is_primary else "Secondary (view only)",
            inline=True,
        )
        embed.add_field(
            name="Quick commands",
            value="⭐ Default" if account.is_default else "Not default",
            inline=True,
        )
        embed.add_field(
            name="Linked Discord",
            value=f"{linked_discords}/{MAX_DISCORD_LINKS_PER_ACCOUNT}",
            inline=True,
        )
        if len(self.accounts) > 1:
            overview_lines: list[str] = []
            for acc in self.accounts[:10]:
                marker = "⭐" if acc.is_default else "•"
                role = "Primary" if acc.is_primary else "Secondary"
                overview_lines.append(f"{marker} **{acc.username}** · {role} · `{acc.user_code}`")
            overview_text = "\n".join(overview_lines)
            if len(overview_text) > 1024:
                overview_text = overview_text[:1020].rsplit("\n", 1)[0]
            embed.add_field(
                name=f"Your accounts ({len(self.accounts)})",
                value=overview_text,
                inline=False,
            )
        return embed, partner_file

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.accounts = await asyncio.to_thread(
            self.bot.repository.list_accounts,
            interaction.user.id,
        )
        if self.selected_user_id not in {item.user_id for item in self.accounts}:
            self.selected_user_id = self.accounts[0].user_id if self.accounts else None
        counts = await _load_linked_counts(self.bot, self.accounts)
        replacement = AccountDashboardView(
            self.bot,
            interaction.user.id,
            self.accounts,
            self.selected_user_id,
            counts,
        )
        embed, partner_file = await replacement.render()
        kwargs: dict = {"embed": embed, "view": replacement}
        kwargs["attachments"] = [partner_file] if partner_file is not None else []
        await interaction.response.edit_message(**kwargs)

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
        embed, partner_file = build_profile_payload(profile)
        await send_ephemeral(interaction, embed=embed, file=partner_file)

    @discord.ui.button(
        label="Recent",
        emoji="🕒",
        style=discord.ButtonStyle.primary,
        custom_id="lygus-recent",
        row=1,
    )
    async def recent(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        cards = await asyncio.to_thread(self.bot.repository.get_recent_score_cards, account.user_id, 5)
        if not cards:
            await send_ephemeral(interaction, embed=recent_embed(account.username, []))
            return
        png = await asyncio.to_thread(render_score_card, cards[0])
        await send_ephemeral(interaction, file=_score_card_file(cards[0], png))

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
        label="B30N",
        style=discord.ButtonStyle.primary,
        custom_id="lygus-b30n",
        row=1,
    )
    async def b30n(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            jpg_bytes = await asyncio.to_thread(
                render_b30n,
                self.bot.settings.game_db_path,
                account.user_id,
            )
            await interaction.followup.send(
                file=discord.File(io.BytesIO(jpg_bytes), filename=f"b30n_{account.username}.jpg"),
                ephemeral=True,
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @discord.ui.button(
        label="Set Default",
        emoji="⭐",
        style=discord.ButtonStyle.success,
        custom_id="lygus-set-default",
        row=1,
    )
    async def set_default(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        await asyncio.to_thread(
            self.bot.repository.set_default_account,
            interaction.user.id,
            account.user_id,
        )
        await self.refresh(interaction)

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
        label="Remove others",
        style=discord.ButtonStyle.secondary,
        custom_id="lygus-revoke-others",
        row=2,
    )
    async def revoke_others(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        account = self.selected_account()
        await send_ephemeral(
            interaction,
            content=f"Remove all other linked Discord accounts from `{account.username}`?",
            view=RevokeOthersConfirmationView(self.bot, interaction.user.id, account),
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


async def _load_linked_counts(bot: LygusBot, accounts: list[Account]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for acc in accounts:
        counts[acc.user_id] = await asyncio.to_thread(
            bot.repository.count_linked_discords, acc.user_id
        )
    return counts


def project_admin(interaction: discord.Interaction) -> bool:
    return (
        str(interaction.user.id) == os.environ.get("LYGUS_ADMIN_USER_ID", "")
        and interaction.guild_id is not None
        and str(interaction.guild_id) == os.environ.get("LYGUS_ADMIN_GUILD_ID", "")
    )


async def handle_interaction_error(interaction: discord.Interaction, error: Exception) -> None:
    if isinstance(error, ValidationError):
        message = str(error)
    elif isinstance(error, AuthenticationFailed):
        message = "Username or password is incorrect."
    elif isinstance(error, PermissionDenied):
        message = str(error) or "You do not have permission for this action."
    elif isinstance(error, AccountConflict):
        message = str(error)
    elif isinstance(error, AccountNotFound):
        message = str(error)
    elif isinstance(error, app_commands.CheckFailure):
        message = "You do not have permission to use this command here."
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
        mention = DISCORD_MENTION_PATTERN.fullmatch(username.strip())
        if mention:
            discord_id = int(mention.group(1))
            accounts = await asyncio.to_thread(
                bot.repository.list_accounts,
                discord_id,
            )
            if not accounts:
                raise AccountNotFound("That Discord user has no linked Akaine account.")
            return accounts[0].user_id, interaction.user.id == discord_id
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


async def _handle_recent(
    bot: LygusBot,
    interaction: discord.Interaction,
    username: Optional[str],
    discord_profile: Optional[discord.User],
    index: int,
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        user_id, is_owner = await resolve_target_user(
            bot, interaction, username, discord_profile
        )
        profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
        if not profile.is_public and not is_owner:
            raise PermissionDenied("This profile is private.")
        if not hasattr(bot.repository, "get_recent_score_cards"):
            scores = await asyncio.to_thread(bot.repository.get_recent_scores, user_id, 5)
            await interaction.followup.send(embed=recent_embed(profile.username, scores))
            return
        cards = await asyncio.to_thread(bot.repository.get_recent_score_cards, user_id, 30)
        if not cards:
            await interaction.followup.send(embed=recent_embed(profile.username, []))
            return
        start_idx = max(0, min(index - 1, len(cards) - 1))
        card = cards[start_idx]
        png = await asyncio.to_thread(render_score_card, card)
        bot.remember_chart(interaction.channel_id, card.song_id, card.difficulty_id)
        view = RecentScoreView(bot, interaction.user.id, user_id, cards, start_idx)
        await interaction.followup.send(file=_score_card_file(card, png), view=view)
    except Exception as error:
        await handle_interaction_error(interaction, error)


def build_bot(settings: BotSettings) -> LygusBot:
    bot = LygusBot(settings)

    async def song_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        charts = await asyncio.to_thread(bot.repository.search_charts, current, 25)
        choices: list[app_commands.Choice[str]] = []
        for chart in charts[:25]:
            diffs = "/".join(
                f"{difficulty_name(d)} {cc:.1f}" for d, cc in sorted(chart.constants.items())
            )
            label = f"{chart.title} ({diffs})" if diffs else chart.title
            choices.append(app_commands.Choice(name=label[:100], value=chart.song_id[:100]))
        return choices

    async def linked_account_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
        needle = current.strip().lower()
        choices: list[app_commands.Choice[str]] = []
        for acc in accounts:
            if needle and needle not in acc.username.lower() and needle not in acc.user_code:
                continue
            prefix = "⭐ " if acc.is_default else ""
            role = "Primary" if acc.is_primary else "Secondary"
            label = f"{prefix}{acc.username} ({role} · {acc.user_code})"
            choices.append(app_commands.Choice(name=label[:100], value=acc.username[:100]))
        return choices[:25]

    @bot.event
    async def on_ready() -> None:
        LOGGER.info("Logged in as %s (%s).", bot.user, bot.user.id if bot.user else "unknown")
        await bot.change_presence(
            activity=discord.Game(name="Akaine · /rs · /help"),
            status=discord.Status.online,
        )

    @bot.tree.command(name="account", description="Open your Akaine account dashboard")
    async def account_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
            counts = await _load_linked_counts(bot, accounts)
            view = AccountDashboardView(bot, interaction.user.id, accounts, linked_counts=counts)
            embed, partner_file = await view.render()
            if partner_file is not None:
                await interaction.followup.send(
                    embed=embed, view=view, file=partner_file, ephemeral=True
                )
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(
        name="default",
        description="View or switch your default Akaine account for quick commands",
    )
    @app_commands.describe(account="Optional linked username, user code, or user ID")
    @app_commands.autocomplete(account=linked_account_autocomplete)
    async def default_command(
        interaction: discord.Interaction,
        account: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if account is None or not account.strip():
                accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
                if not accounts:
                    raise AccountNotFound("Use `/create` or `/link` first.")
                lines = []
                for acc in accounts[:15]:
                    marker = "⭐" if acc.is_default else "•"
                    role = "Primary" if acc.is_primary else "Secondary"
                    tag = " **(Default)**" if acc.is_default else ""
                    lines.append(f"{marker} **{acc.username}** · {role} · `{acc.user_code}`{tag}")
                embed = discord.Embed(
                    title="Default Akaine Account",
                    description="\n".join(lines),
                    color=BRAND_COLOR,
                )
                embed.set_footer(
                    text="Use /default <account> to switch quickly, or /account for full management."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            switched = await asyncio.to_thread(
                bot.repository.set_default_account_by_name,
                interaction.user.id,
                account,
            )
            embed = discord.Embed(
                title="Default account updated",
                description=(
                    f"⭐ **{switched.username}** (`{switched.user_code}`) is now your default account.\n"
                    "Quick commands (`/rs`, `/profile`, `/b30`, `/b30n`, `/b30n2`, `/score`, "
                    "`/top`, `/whatif`, `/progress`, `/compare`) now use it automatically."
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="create", description="Create a new Akaine account")
    async def create_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CreateAccountModal(bot))

    @bot.tree.command(name="link", description="Link an existing Akaine account")
    async def link_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(LinkAccountModal(bot))

    @bot.tree.command(name="profile", description="View an Akaine profile")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user; uses their primary linked account",
    )
    async def profile_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(
                bot, interaction, username, discord_profile
            )
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            embed, partner_file = build_profile_payload(profile)
            if partner_file is not None:
                await interaction.followup.send(embed=embed, file=partner_file)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="recent", description="Show your or another player's recent play cards")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user",
        index="Play number (1 = newest, up to 30)",
    )
    async def recent_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
        index: Optional[app_commands.Range[int, 1, 30]] = 1,
    ) -> None:
        await _handle_recent(bot, interaction, username, discord_profile, int(index or 1))

    @bot.tree.command(name="rs", description="Quick shortcut for recent play card (/recent)")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user",
        index="Play number (1 = newest, up to 30)",
    )
    async def rs_command(
        interaction: discord.Interaction,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
        index: Optional[app_commands.Range[int, 1, 30]] = 1,
    ) -> None:
        await _handle_recent(bot, interaction, username, discord_profile, int(index or 1))

    @bot.tree.command(name="score", description="Show a player's Personal Best score card on a chart")
    @app_commands.describe(
        song="Song title or ID",
        difficulty="Chart difficulty (defaults to highest)",
        username="Optional Akaine username",
        discord_profile="Optional Discord user",
    )
    @app_commands.autocomplete(song=song_autocomplete)
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def score_command(
        interaction: discord.Interaction,
        song: str,
        difficulty: Optional[app_commands.Choice[int]] = None,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(
                bot, interaction, username, discord_profile
            )
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            card = await asyncio.to_thread(
                bot.repository.get_user_chart_score, user_id, song, _diff_value(difficulty)
            )
            png = await asyncio.to_thread(render_score_card, card)
            bot.remember_chart(interaction.channel_id, card.song_id, card.difficulty_id)
            view = ScoreCardView(bot, interaction.user.id, card, user_id)
            await interaction.followup.send(file=_score_card_file(card, png), view=view)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="compare", description="Compare scores on a chart (defaults to last chart in chat)")
    @app_commands.describe(
        song="Song title or ID (leave empty to use the last chart shown in this channel)",
        difficulty="Chart difficulty",
        username="Optional opponent Akaine username",
        discord_profile="Optional opponent Discord user",
    )
    @app_commands.autocomplete(song=song_autocomplete)
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def compare_command(
        interaction: discord.Interaction,
        song: Optional[str] = None,
        difficulty: Optional[app_commands.Choice[int]] = None,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            caller_accounts = await asyncio.to_thread(bot.repository.list_accounts, interaction.user.id)
            if not caller_accounts:
                raise AccountNotFound("Use `/create` or `/link` first.")
            left_uid = caller_accounts[0].user_id

            diff_val = _diff_value(difficulty)
            query = song
            if not query:
                last = bot.channel_last_chart.get(int(interaction.channel_id or 0))
                if last is None:
                    raise ValidationError("No recent chart found in this channel. Specify `song`.")
                query = last[0]
                if diff_val is None:
                    diff_val = last[1]

            right_uid: Optional[int] = None
            if username or discord_profile:
                right_uid, right_is_owner = await resolve_target_user(
                    bot, interaction, username, discord_profile
                )
                if not right_is_owner:
                    rprof = await asyncio.to_thread(bot.repository.get_profile, right_uid)
                    if not rprof.is_public:
                        raise PermissionDenied("This profile is private.")

            result = await asyncio.to_thread(
                bot.repository.compare_scores, query, diff_val, left_uid, right_uid
            )
            bot.remember_chart(interaction.channel_id, result.chart.song_id, result.difficulty_id)
            await interaction.followup.send(embed=compare_embed(result))
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="lb", description="View server leaderboard for a chart")
    @app_commands.describe(song="Song title or ID", difficulty="Chart difficulty")
    @app_commands.autocomplete(song=song_autocomplete)
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def lb_command(
        interaction: discord.Interaction,
        song: str,
        difficulty: Optional[app_commands.Choice[int]] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await _send_chart_lb(bot, interaction, song, _diff_value(difficulty))
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="top", description="Browse Best scores with optional difficulty/constant filters")
    @app_commands.describe(
        difficulty="Filter by chart difficulty",
        min_cc="Minimum chart constant (e.g. 10.0)",
        username="Optional Akaine username",
        discord_profile="Optional Discord user",
    )
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def top_command(
        interaction: discord.Interaction,
        difficulty: Optional[app_commands.Choice[int]] = None,
        min_cc: Optional[app_commands.Range[float, 1.0, 15.0]] = None,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(
                bot, interaction, username, discord_profile
            )
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            diff_val = _diff_value(difficulty)
            cc_val = float(min_cc) if min_cc is not None else None
            top = await asyncio.to_thread(
                bot.repository.get_top_scores,
                user_id,
                difficulty=diff_val,
                min_cc=cc_val,
                page=1,
                page_size=SCORE_LIST_PAGE_SIZE,
            )
            view = TopScoresView(bot, interaction.user.id, user_id, top, diff_val, cc_val)
            await interaction.followup.send(
                embed=top_scores_embed(top, diff_val, cc_val), view=view
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="whatif", description="Simulate PTT targets on a chart or get B30 farm suggestions")
    @app_commands.describe(
        song="Optional song to simulate; omit for B30 overview + farm suggestions",
        difficulty="Chart difficulty",
        target_score="Optional hypothetical score (0–10,005,000)",
    )
    @app_commands.autocomplete(song=song_autocomplete)
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def whatif_command(
        interaction: discord.Interaction,
        song: Optional[str] = None,
        difficulty: Optional[app_commands.Choice[int]] = None,
        target_score: Optional[app_commands.Range[int, 0, 10005000]] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, _ = await resolve_target_user(bot, interaction, None, None)
            if not song:
                summary = await asyncio.to_thread(bot.repository.get_whatif_summary, user_id)
                await interaction.followup.send(embed=whatif_summary_embed(summary))
                return
            res = await asyncio.to_thread(
                bot.repository.simulate_whatif_chart,
                user_id,
                song,
                _diff_value(difficulty),
                int(target_score) if target_score is not None else None,
            )
            bot.remember_chart(interaction.channel_id, res.chart.song_id, res.difficulty_id)
            await interaction.followup.send(embed=whatif_chart_embed(res))
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="progress", description="View clear/EX+/FR/PM progress across chart levels")
    @app_commands.describe(
        difficulty="Optional difficulty filter",
        username="Optional Akaine username",
        discord_profile="Optional Discord user",
    )
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def progress_command(
        interaction: discord.Interaction,
        difficulty: Optional[app_commands.Choice[int]] = None,
        username: Optional[str] = None,
        discord_profile: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            user_id, is_owner = await resolve_target_user(
                bot, interaction, username, discord_profile
            )
            profile = await asyncio.to_thread(bot.repository.get_profile, user_id)
            if not profile.is_public and not is_owner:
                raise PermissionDenied("This profile is private.")
            prog = await asyncio.to_thread(
                bot.repository.get_progress_summary, user_id, _diff_value(difficulty)
            )
            await interaction.followup.send(embed=progress_embed(prog))
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="song", description="Look up chart constants and #1 score for a song")
    @app_commands.describe(song="Song title or ID")
    @app_commands.autocomplete(song=song_autocomplete)
    async def song_command(interaction: discord.Interaction, song: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            info = await asyncio.to_thread(bot.repository.get_chart_info, song)
            default_diff = max(info.constants.keys()) if info.constants else 2
            bot.remember_chart(interaction.channel_id, info.song_id, default_diff)
            embed, jfile = build_song_payload(info)
            view = SongInfoView(bot, info, default_diff)
            if jfile is not None:
                await interaction.followup.send(embed=embed, file=jfile, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="random", description="Roll a random chart by constant range")
    @app_commands.describe(
        min_cc="Minimum constant (default 8.0)",
        max_cc="Maximum constant (default 11.5)",
        difficulty="Optional difficulty filter",
    )
    @app_commands.choices(difficulty=DIFF_CHOICES)
    async def random_command(
        interaction: discord.Interaction,
        min_cc: Optional[app_commands.Range[float, 1.0, 15.0]] = 8.0,
        max_cc: Optional[app_commands.Range[float, 1.0, 15.0]] = 11.5,
        difficulty: Optional[app_commands.Choice[int]] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            lo = float(8.0 if min_cc is None else min_cc)
            hi = float(11.5 if max_cc is None else max_cc)
            diff_val = _diff_value(difficulty)
            chart, diff_id, const = await asyncio.to_thread(
                bot.repository.get_random_chart, min_cc=lo, max_cc=hi, difficulty=diff_val
            )
            viewer_uid = await _resolve_viewer_user_id(bot, interaction.user.id)
            caller_pb: Optional[ScoreCardData] = None
            if viewer_uid is not None:
                try:
                    caller_pb = await asyncio.to_thread(
                        bot.repository.get_user_chart_score, viewer_uid, chart.song_id, diff_id
                    )
                except AccountNotFound:
                    caller_pb = None
            bot.remember_chart(interaction.channel_id, chart.song_id, diff_id)
            embed, jfile = build_random_payload(chart, diff_id, const, caller_pb)
            view = RandomChartView(bot, interaction.user.id, chart, diff_id, lo, hi, diff_val)
            if jfile is not None:
                await interaction.followup.send(embed=embed, file=jfile, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="b30", description="Generate your or another player's Best 30 image")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user; uses their primary linked account",
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

    @bot.tree.command(name="b30n", description="Generate Chieri-style Best 30 + Overflow (#31–39) image")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user; uses their primary linked account",
    )
    async def b30n_command(
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
            jpg_bytes = await asyncio.to_thread(
                render_b30n,
                bot.settings.game_db_path,
                user_id,
            )
            await interaction.followup.send(
                file=discord.File(io.BytesIO(jpg_bytes), filename=f"b30n_{profile.username}.jpg")
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="b30n2", description="Generate 16:10 widescreen Best 30 image")
    @app_commands.describe(
        username="Optional Akaine username",
        discord_profile="Optional Discord user; uses their primary linked account",
    )
    async def b30n2_command(
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
            jpg_bytes = await asyncio.to_thread(
                render_b30n2,
                bot.settings.game_db_path,
                user_id,
            )
            await interaction.followup.send(
                file=discord.File(io.BytesIO(jpg_bytes), filename=f"b30n2_{profile.username}.jpg")
            )
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="ranking", description="View all players ranked by Potential")
    async def ranking_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            ranking = await asyncio.to_thread(
                bot.repository.get_ranking_page,
                1,
                RANKING_PAGE_SIZE,
            )
            view = RankingView(bot, interaction.user.id, ranking)
            await interaction.followup.send(embed=ranking_embed(ranking), view=view)
        except Exception as error:
            await handle_interaction_error(interaction, error)

    @bot.tree.command(name="help", description="Show Demiurge commands and guide")
    async def help_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=help_embed_for_category("overview"),
            view=HelpMenuView(interaction.user.id, "overview"),
            ephemeral=True,
        )

    @bot.tree.command(
        name="api_key",
        description="Rotate the external read-only API key (administrator only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.check(project_admin)
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
    @app_commands.check(project_admin)
    async def api_key_revoke_command(interaction: discord.Interaction) -> None:
        revoked = await asyncio.to_thread(bot.repository.revoke_external_api_key)
        await interaction.response.send_message(
            "Read-only API key revoked." if revoked else "No active API key.",
            ephemeral=True,
        )

    @bot.tree.command(name="sync", description="Synchronize slash commands (administrator only)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.check(project_admin)
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
