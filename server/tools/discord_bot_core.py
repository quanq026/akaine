from __future__ import annotations

import hashlib
import hmac
import math
import random
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_SERVER_ROOT = Path(__file__).resolve().parents[1]
if (_SERVER_ROOT / "core" / "account_provisioning.py").is_file():
    import sys as _sys

    if str(_SERVER_ROOT) not in _sys.path:
        _sys.path.insert(0, str(_SERVER_ROOT))
    from core.account_provisioning import (
        BotCoreError,
        MAX_PASSWORD_LENGTH,
        MIN_PASSWORD_LENGTH,
        USERNAME_PATTERN,
        ValidationError,
        provision_account,
        validate_password,
        validate_username,
    )

    _HAS_SHARED_PROVISIONING = True
else:
    _HAS_SHARED_PROVISIONING = False
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9]{3,16}$")
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 32
    provision_account = None  # type: ignore[assignment]

MAX_DISCORD_LINKS_PER_ACCOUNT = 3
LINK_MAX_FAILURES = 5
LINK_LOCKOUT_SECONDS = 900
CHART_CACHE_TTL_SECONDS = 300

DIFFICULTY_NAMES = {
    0: "PST",
    1: "PRS",
    2: "FTR",
    3: "BYD",
    4: "ETR",
}

DIFFICULTY_FULL_NAMES = {
    0: "Past",
    1: "Present",
    2: "Future",
    3: "Beyond",
    4: "Eternal",
}

CLEAR_TYPE_NAMES = {
    0: "TRACK LOST",
    1: "NORMAL CLEAR",
    2: "FULL RECALL",
    3: "PURE MEMORY",
    4: "EASY CLEAR",
    5: "HARD CLEAR",
}

CLEAR_TYPE_SHORT = {
    0: "TL",
    1: "NC",
    2: "FR",
    3: "PM",
    4: "EC",
    5: "HC",
}

LEVEL_BUCKET_ORDER = (
    "≤7+",
    "8",
    "8+",
    "9",
    "9+",
    "10",
    "10+",
    "11",
    "11+",
    "12",
)


if not _HAS_SHARED_PROVISIONING:

    class BotCoreError(Exception):
        pass

    class ValidationError(BotCoreError):
        pass


class AuthenticationFailed(BotCoreError):
    pass


class AccountConflict(BotCoreError):
    pass


class PermissionDenied(BotCoreError):
    pass


class AccountNotFound(BotCoreError):
    pass


@dataclass(frozen=True)
class Account:
    discord_id: str
    user_id: int
    username: str
    user_code: str
    created_at: Optional[str] = None
    is_primary: bool = True
    is_default: bool = False


@dataclass(frozen=True)
class Profile:
    user_id: int
    username: str
    user_code: str
    ptt: str
    character_id: Optional[int]
    character_level: Optional[int]
    joined_at: Optional[str]
    best_score_count: int
    recent_play_count: int
    is_public: bool
    server_rank: Optional[int] = None
    b30_avg: float = 0.0
    r10_avg: float = 0.0
    pm_count: int = 0
    fr_count: int = 0
    ex_plus_count: int = 0
    is_char_uncapped: bool = False
    last_song_id: Optional[str] = None
    last_song_title: Optional[str] = None
    last_difficulty: Optional[int] = None
    last_score: Optional[int] = None


@dataclass(frozen=True)
class RecentScore:
    song_id: str
    difficulty: str
    score: int
    clear_type: str
    rating: float
    time_played: int
    pure_count: int
    shiny_pure_count: int
    near_count: int
    miss_count: int
    difficulty_id: int = 2
    song_title: str = ""
    constant: Optional[float] = None
    clear_type_id: int = 0
    pb_score: Optional[int] = None
    pb_delta: Optional[int] = None
    b30_rank: Optional[int] = None
    chart_rank: Optional[int] = None
    chart_total_players: int = 0


@dataclass(frozen=True)
class RankingEntry:
    rank: int
    username: str
    ptt: str


@dataclass(frozen=True)
class RankingPage:
    entries: tuple[RankingEntry, ...]
    page: int
    page_count: int
    total_players: int


@dataclass(frozen=True)
class ChartInfo:
    song_id: str
    title: str
    constants: dict[int, float]
    play_count: int = 0
    top_score: Optional[int] = None
    top_player: Optional[str] = None
    top_difficulty: Optional[int] = None


@dataclass(frozen=True)
class ScoreCardData:
    username: str
    user_ptt: str
    song_id: str
    song_title: str
    difficulty_id: int
    difficulty: str
    constant: Optional[float]
    score: int
    grade: str
    clear_type_id: int
    clear_type: str
    clear_short: str
    pure_count: int
    shiny_pure_count: int
    near_count: int
    miss_count: int
    rating: float
    time_played: int
    is_recent: bool
    recent_index: int
    recent_total: int
    pb_score: Optional[int]
    pb_delta: Optional[int]
    b30_rank: Optional[int]
    chart_rank: Optional[int]
    chart_total_players: int
    user_code: str = ""
    character_id: Optional[int] = None
    is_char_uncapped: bool = False
    raw_ptt: int = -1


@dataclass(frozen=True)
class ChartLeaderboardEntry:
    rank: int
    user_id: int
    username: str
    score: int
    grade: str
    clear_short: str
    pure_count: int
    shiny_pure_count: int
    near_count: int
    miss_count: int
    rating: float
    time_played: int


@dataclass(frozen=True)
class ChartLeaderboardPage:
    chart: ChartInfo
    difficulty_id: int
    constant: Optional[float]
    entries: tuple[ChartLeaderboardEntry, ...]
    page: int
    page_count: int
    total_entries: int
    viewer_entry: Optional[ChartLeaderboardEntry]


@dataclass(frozen=True)
class TopScoreEntry:
    rank: int
    b30_rank: Optional[int]
    song_id: str
    song_title: str
    difficulty_id: int
    difficulty: str
    constant: Optional[float]
    score: int
    grade: str
    clear_short: str
    rating: float
    time_played: int


@dataclass(frozen=True)
class TopScoresPage:
    username: str
    entries: tuple[TopScoreEntry, ...]
    page: int
    page_count: int
    total_entries: int
    b30_avg: float


@dataclass(frozen=True)
class WhatIfRecommendation:
    song_id: str
    song_title: str
    difficulty_id: int
    difficulty: str
    constant: float
    current_score: Optional[int]
    target_score: int
    projected_rating: float
    b30_gain: float


@dataclass(frozen=True)
class WhatIfSummary:
    username: str
    ptt: str
    b30_avg: float
    r10_avg: float
    b30_ceiling: float
    b30_floor: float
    b30_count: int
    recommendations: tuple[WhatIfRecommendation, ...]


@dataclass(frozen=True)
class WhatIfChartResult:
    username: str
    chart: ChartInfo
    difficulty_id: int
    constant: float
    b30_avg: float
    b30_floor: float
    current_pb: Optional[int]
    current_rating: float
    score_to_enter_b30: Optional[int]
    milestones: tuple[tuple[str, Optional[int]], ...]
    simulated_score: Optional[int]
    simulated_rating: Optional[float]
    simulated_new_b30: Optional[float]
    simulated_b30_delta: Optional[float]


@dataclass(frozen=True)
class ProgressBucket:
    label: str
    total_charts: int
    played: int
    cleared: int
    ex_count: int
    ex_plus_count: int
    fr_count: int
    pm_count: int


@dataclass(frozen=True)
class ProgressSummary:
    username: str
    difficulty_filter: Optional[int]
    buckets: tuple[ProgressBucket, ...]
    total_played: int
    total_pm: int
    total_fr: int
    total_ex_plus: int


@dataclass(frozen=True)
class CompareResult:
    chart: ChartInfo
    difficulty_id: int
    constant: Optional[float]
    left_username: str
    left_score: Optional[ScoreCardData]
    right_username: Optional[str]
    right_score: Optional[ScoreCardData]


if not _HAS_SHARED_PROVISIONING:

    def validate_username(username: str) -> str:
        value = username.strip()
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValidationError("Username must be 3-16 ASCII letters or digits.")
        return value


    def validate_password(password: str) -> str:
        if password != password.strip():
            raise ValidationError("Password cannot start or end with whitespace.")
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise ValidationError("Password must be 8-32 characters.")
        return password


def hash_password(password: str) -> str:
    return hashlib.sha256(validate_password(password).encode("utf-8")).hexdigest()


def verify_password(password: str, expected_hash: str) -> bool:
    try:
        candidate = hash_password(password)
    except ValidationError:
        return False
    return hmac.compare_digest(candidate, expected_hash or "")


def format_ptt(rating_ptt: Optional[int]) -> str:
    if rating_ptt is None or int(rating_ptt) < 0:
        return "Hidden"
    return f"{int(rating_ptt) / 100:.2f}"


def difficulty_name(difficulty: int) -> str:
    value = int(difficulty)
    return DIFFICULTY_NAMES.get(value, f"D{value}")


def clear_type_name(clear_type: int) -> str:
    value = int(clear_type)
    return CLEAR_TYPE_NAMES.get(value, f"CLEAR {value}")


def clear_type_short(clear_type: int) -> str:
    value = int(clear_type)
    return CLEAR_TYPE_SHORT.get(value, f"C{value}")


def score_grade(score: int) -> str:
    value = int(score)
    if value >= 9_900_000:
        return "EX+"
    if value >= 9_800_000:
        return "EX"
    if value >= 9_500_000:
        return "AA"
    if value >= 9_200_000:
        return "A"
    if value >= 8_900_000:
        return "B"
    if value >= 8_600_000:
        return "C"
    return "D"


def format_score_commas(score: int) -> str:
    return f"{int(score):,}"


def format_score_arcaea(score: int) -> str:
    sc = str(max(0, int(score))).zfill(8)
    return f"{sc[:-6]}'{sc[-6:-3]}'{sc[-3:]}"


def calculate_play_rating(constant: float, score: int) -> float:
    if constant <= 0:
        return 0.0
    s = int(score)
    if s >= 10_000_000:
        return float(constant) + 2.0
    if s >= 9_800_000:
        return float(constant) + 1.0 + (s - 9_800_000) / 200_000.0
    return max(0.0, float(constant) + (s - 9_500_000) / 300_000.0)


def score_for_target_rating(constant: float, target_rating: float) -> Optional[int]:
    if constant <= 0:
        return None
    if target_rating <= 0:
        return 0
    if target_rating > constant + 2.0 + 1e-9:
        return None
    if target_rating >= constant + 2.0 - 1e-9:
        return 10_000_000
    if target_rating >= constant + 1.0:
        needed = 9_800_000.0 + (target_rating - constant - 1.0) * 200_000.0
        return min(10_000_000, max(9_800_000, int(math.ceil(needed - 1e-9))))
    needed = 9_500_000.0 + (target_rating - constant) * 300_000.0
    return min(9_799_999, max(0, int(math.ceil(needed - 1e-9))))


def level_bucket(constant: float) -> str:
    tenths = int(round(float(constant) * 10))
    if tenths <= 79:
        return "≤7+"
    if tenths <= 86:
        return "8"
    if tenths <= 89:
        return "8+"
    if tenths <= 96:
        return "9"
    if tenths <= 99:
        return "9+"
    if tenths <= 106:
        return "10"
    if tenths <= 109:
        return "10+"
    if tenths <= 116:
        return "11"
    if tenths <= 119:
        return "11+"
    return "12"


def normalize_timestamp_seconds(ts: Optional[int]) -> int:
    if not ts:
        return 0
    value = int(ts)
    if value > 10_000_000_000:
        return value // 1000
    return value


class BotRepository:
    def __init__(self, game_db_path: str | Path, mapping_db_path: str | Path) -> None:
        self.game_db_path = Path(game_db_path)
        self.mapping_db_path = Path(mapping_db_path)
        self._chart_cache: dict[str, ChartInfo] = {}
        self._chart_cache_at: float = 0.0

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    @staticmethod
    def _existing_tables(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    def migrate_mapping_schema(self) -> None:
        connection = self._connect(self.mapping_db_path)
        try:
            self._create_external_api_key_table(connection)
            self._create_link_failures_table(connection)
            connection.commit()
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_mapping'"
            ).fetchone()
            if not table_exists:
                self._create_mapping_table(connection)
                connection.commit()
                return

            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(user_mapping)")
            }
            if "password" in columns or self._has_single_user_id_unique(connection):
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DROP TABLE IF EXISTS user_mapping_v2")
                self._create_mapping_table(connection, table_name="user_mapping_v2")
                primary_expr = "COALESCE(is_primary, 0)" if "is_primary" in columns else "0"
                default_expr = "COALESCE(is_default, 0)" if "is_default" in columns else "0"
                connection.execute(
                    f"""
                    INSERT OR IGNORE INTO user_mapping_v2 (
                        discord_id, user_id, username, user_code, created_at, is_primary, is_default
                    )
                    SELECT
                        CAST(discord_id AS TEXT), CAST(user_id AS INTEGER),
                        username, user_code, created_at, {primary_expr}, {default_expr}
                    FROM user_mapping
                    WHERE discord_id IS NOT NULL
                      AND user_id IS NOT NULL
                      AND username IS NOT NULL
                      AND user_code IS NOT NULL
                    ORDER BY created_at, rowid
                    """
                )
                connection.execute("DROP TABLE user_mapping")
                connection.execute("ALTER TABLE user_mapping_v2 RENAME TO user_mapping")
                self._create_mapping_indexes(connection)
                self._backfill_primary_flags(connection)
                self._backfill_default_flags(connection)
                connection.commit()
                return

            connection.execute("BEGIN IMMEDIATE")
            if "is_primary" not in columns:
                connection.execute(
                    "ALTER TABLE user_mapping ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0"
                )
            if "is_default" not in columns:
                connection.execute(
                    "ALTER TABLE user_mapping ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
                )
            self._create_mapping_indexes(connection)
            self._backfill_primary_flags(connection)
            self._backfill_default_flags(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _create_mapping_table(
        connection: sqlite3.Connection,
        table_name: str = "user_mapping",
    ) -> None:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                discord_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                user_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_primary INTEGER NOT NULL DEFAULT 0,
                is_default INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (discord_id, user_id),
                UNIQUE (discord_id, username)
            )
            """
        )

    @staticmethod
    def _backfill_primary_flags(connection: sqlite3.Connection) -> None:
        user_rows = connection.execute(
            """
            SELECT user_id, SUM(COALESCE(is_primary, 0)) AS primary_count
            FROM user_mapping
            GROUP BY user_id
            HAVING primary_count < 1
            """
        ).fetchall()
        for row in user_rows:
            uid = int(row["user_id"])
            oldest = connection.execute(
                """
                SELECT rowid
                FROM user_mapping
                WHERE user_id = ?
                ORDER BY created_at ASC, rowid ASC
                LIMIT 1
                """,
                (uid,),
            ).fetchone()
            if oldest is not None:
                connection.execute(
                    "UPDATE user_mapping SET is_primary = 1 WHERE rowid = ?",
                    (int(oldest["rowid"]),),
                )

    @staticmethod
    def _backfill_default_flags(connection: sqlite3.Connection) -> None:
        discord_rows = connection.execute(
            """
            SELECT discord_id, SUM(COALESCE(is_default, 0)) AS default_count
            FROM user_mapping
            GROUP BY discord_id
            HAVING default_count <> 1
            """
        ).fetchall()
        for row in discord_rows:
            did = str(row["discord_id"])
            count = int(row["default_count"])
            if count == 0:
                chosen = connection.execute(
                    """
                    SELECT rowid
                    FROM user_mapping
                    WHERE discord_id = ?
                    ORDER BY is_primary DESC, created_at DESC, user_id DESC
                    LIMIT 1
                    """,
                    (did,),
                ).fetchone()
                if chosen is not None:
                    connection.execute(
                        "UPDATE user_mapping SET is_default = 1 WHERE rowid = ?",
                        (int(chosen["rowid"]),),
                    )
            else:
                chosen = connection.execute(
                    """
                    SELECT rowid
                    FROM user_mapping
                    WHERE discord_id = ? AND COALESCE(is_default, 0) = 1
                    ORDER BY is_primary DESC, created_at DESC, user_id DESC
                    LIMIT 1
                    """,
                    (did,),
                ).fetchone()
                if chosen is not None:
                    connection.execute(
                        "UPDATE user_mapping SET is_default = CASE WHEN rowid = ? THEN 1 ELSE 0 END WHERE discord_id = ?",
                        (int(chosen["rowid"]), did),
                    )

    @staticmethod
    def _has_single_user_id_unique(connection: sqlite3.Connection) -> bool:
        for row in connection.execute("PRAGMA index_list(user_mapping)").fetchall():
            if row[2] != 1:
                continue
            safe_name = str(row[1]).replace('"', '""')
            cols = connection.execute(f'PRAGMA index_info("{safe_name}")').fetchall()
            if [col[2] for col in cols] == ["user_id"]:
                return True
        return False

    @staticmethod
    def _create_mapping_indexes(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_mapping_discord_id "
            "ON user_mapping(discord_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_mapping_user_id "
            "ON user_mapping(user_id)"
        )

    @staticmethod
    def _create_external_api_key_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS external_api_key (
                key_hash TEXT PRIMARY KEY,
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    @staticmethod
    def _create_link_failures_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS link_failures (
                scope_key TEXT NOT NULL,
                failed_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_link_failures_scope "
            "ON link_failures(scope_key, failed_at)"
        )

    def count_linked_discords(self, user_id: int) -> int:
        connection = self._connect(self.mapping_db_path)
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM user_mapping WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            return int(row[0]) if row is not None else 0
        finally:
            connection.close()

    def list_linked_discord_ids(
        self, user_id: int, exclude_discord_id: Optional[str | int] = None
    ) -> list[str]:
        connection = self._connect(self.mapping_db_path)
        try:
            if exclude_discord_id is not None:
                rows = connection.execute(
                    "SELECT discord_id FROM user_mapping WHERE user_id = ? AND discord_id <> ?",
                    (int(user_id), str(exclude_discord_id)),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT discord_id FROM user_mapping WHERE user_id = ?",
                    (int(user_id),),
                ).fetchall()
            return [str(row["discord_id"]) for row in rows]
        finally:
            connection.close()

    def rotate_external_api_key(self, created_by: str | int) -> str:
        token = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        connection = self._connect(self.mapping_db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._create_external_api_key_table(connection)
            connection.execute("DELETE FROM external_api_key")
            connection.execute(
                "INSERT INTO external_api_key (key_hash,created_by) VALUES (?,?)",
                (key_hash, str(created_by)),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return token

    def revoke_external_api_key(self) -> bool:
        connection = self._connect(self.mapping_db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._create_external_api_key_table(connection)
            changed = connection.execute("DELETE FROM external_api_key").rowcount > 0
            connection.commit()
            return changed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> Account:
        keys = row.keys()
        is_primary = bool(row["is_primary"]) if "is_primary" in keys else True
        is_default = bool(row["is_default"]) if "is_default" in keys else False
        return Account(
            discord_id=str(row["discord_id"]),
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            user_code=str(row["user_code"]),
            created_at=row["created_at"],
            is_primary=is_primary,
            is_default=is_default,
        )

    def list_accounts(self, discord_id: str | int) -> list[Account]:
        connection = self._connect(self.mapping_db_path)
        try:
            rows = connection.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default
                FROM user_mapping
                WHERE discord_id = ?
                ORDER BY is_default DESC, is_primary DESC, created_at DESC, user_id DESC
                """,
                (str(discord_id),),
            ).fetchall()
            return [self._account_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_owned_account(self, discord_id: str | int, user_id: int) -> Account:
        connection = self._connect(self.mapping_db_path)
        try:
            row = connection.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default
                FROM user_mapping
                WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise PermissionDenied("This Discord user does not own that account.")
        return self._account_from_row(row)

    def find_user_id(self, username: str) -> int:
        value = validate_username(username)
        connection = self._connect(self.game_db_path)
        try:
            row = connection.execute(
                "SELECT user_id FROM user WHERE name = ?",
                (value,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise AccountNotFound("Account does not exist.")
        return int(row["user_id"])

    def create_account(self, discord_id: str | int, username: str, password: str) -> Account:
        if provision_account is None:
            from create_user_cli import provision_account as _provision_fn
        else:
            _provision_fn = provision_account

        username = validate_username(username)
        password = validate_password(password)
        connection = self._connect(self.game_db_path)
        try:
            connection.execute("ATTACH DATABASE ? AS botdb", (str(self.mapping_db_path),))
            for database in ("main", "botdb"):
                mode = connection.execute(f"PRAGMA {database}.journal_mode").fetchone()[0]
                if mode not in ("delete", "truncate", "persist"):
                    raise RuntimeError("Atomic account creation requires rollback-journal databases.")
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM user WHERE name = ?", (username,)).fetchone():
                raise AccountConflict("Username already exists.")
            payload = _provision_fn(connection.cursor(), username, password)
            existing_for_discord = int(
                connection.execute(
                    "SELECT COUNT(*) FROM botdb.user_mapping WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()[0]
            )
            is_default = 1 if existing_for_discord == 0 else 0
            connection.execute(
                "INSERT INTO botdb.user_mapping (discord_id, user_id, username, user_code, is_primary, is_default) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (str(discord_id), payload["user_id"], payload["username"], payload["user_code"], is_default),
            )
            account_row = connection.execute(
                "SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default "
                "FROM botdb.user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), payload["user_id"]),
            ).fetchone()
            account = self._account_from_row(account_row)
            connection.commit()
            return account
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise AccountConflict("Account creation or linking conflicted; no account was created.") from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def register_mapping(
        self,
        discord_id: str | int,
        user_id: int,
        username: str,
        user_code: str,
    ) -> Account:
        value = validate_username(username)
        game = self._connect(self.game_db_path)
        try:
            row = game.execute(
                "SELECT user_id, name, user_code FROM user WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        finally:
            game.close()
        if row is None:
            raise AccountNotFound("Created account does not exist in the game database.")
        if row["name"] != value or str(row["user_code"]) != str(user_code):
            raise AccountConflict("Created account details do not match the game database.")

        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            existing_count = int(
                mapping.execute(
                    "SELECT COUNT(*) FROM user_mapping WHERE user_id = ?",
                    (int(user_id),),
                ).fetchone()[0]
            )
            existing_for_discord = int(
                mapping.execute(
                    "SELECT COUNT(*) FROM user_mapping WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()[0]
            )
            is_primary = 1 if existing_count == 0 else 0
            is_default = 1 if existing_for_discord == 0 else 0
            mapping.execute(
                """
                INSERT INTO user_mapping (
                    discord_id, user_id, username, user_code, is_primary, is_default
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(discord_id), int(user_id), value, str(user_code), is_primary, is_default),
            )
            account_row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default
                FROM user_mapping WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            mapping.commit()
        except sqlite3.IntegrityError as error:
            mapping.rollback()
            raise AccountConflict("This account is already linked.") from error
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()
        return self._account_from_row(account_row)

    def unlink_account(self, discord_id: str | int, user_id: int) -> Account:
        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default
                FROM user_mapping WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            if row is None:
                raise PermissionDenied("This Discord user does not own that account.")
            was_primary = bool(row["is_primary"])
            was_default = bool(row["is_default"])
            mapping.execute(
                "DELETE FROM user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            )
            if was_primary:
                next_owner = mapping.execute(
                    """
                    SELECT rowid
                    FROM user_mapping
                    WHERE user_id = ?
                    ORDER BY created_at ASC, rowid ASC
                    LIMIT 1
                    """,
                    (int(user_id),),
                ).fetchone()
                if next_owner is not None:
                    mapping.execute(
                        "UPDATE user_mapping SET is_primary = 1 WHERE rowid = ?",
                        (int(next_owner["rowid"]),),
                    )
            if was_default:
                next_default = mapping.execute(
                    """
                    SELECT rowid
                    FROM user_mapping
                    WHERE discord_id = ?
                    ORDER BY is_primary DESC, created_at DESC, user_id DESC
                    LIMIT 1
                    """,
                    (str(discord_id),),
                ).fetchone()
                if next_default is not None:
                    mapping.execute(
                        "UPDATE user_mapping SET is_default = 1 WHERE rowid = ?",
                        (int(next_default["rowid"]),),
                    )
            mapping.commit()
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()
        return self._account_from_row(row)

    def set_default_account(self, discord_id: str | int, user_id: int) -> Account:
        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            exists = mapping.execute(
                "SELECT 1 FROM user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            ).fetchone()
            if exists is None:
                raise PermissionDenied("This Discord user does not own that account.")
            mapping.execute(
                "UPDATE user_mapping SET is_default = CASE WHEN user_id = ? THEN 1 ELSE 0 END WHERE discord_id = ?",
                (int(user_id), str(discord_id)),
            )
            account_row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary, is_default
                FROM user_mapping WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            mapping.commit()
            return self._account_from_row(account_row)
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()

    def set_default_account_by_name(self, discord_id: str | int, account_query: str) -> Account:
        query = account_query.strip()
        if not query:
            raise ValidationError("Provide an account username, user code, or user ID.")
        accounts = self.list_accounts(discord_id)
        if not accounts:
            raise AccountNotFound("Use `/create` or `/link` first.")
        matched: Optional[Account] = None
        q_lower = query.lower()
        for acc in accounts:
            if str(acc.user_id) == query or acc.user_code == query or acc.username.lower() == q_lower:
                matched = acc
                break
        if matched is None:
            raise AccountNotFound("That account is not linked to your Discord user.")
        return self.set_default_account(discord_id, matched.user_id)

    @staticmethod
    def _link_failure_scopes(discord_id: str | int, username: str) -> tuple[str, str]:
        did = str(discord_id)
        return (f"discord:{did}", f"target:{did}:{username.lower()}")

    def _check_link_lockout(self, discord_id: str | int, username: str, now_ts: int) -> None:
        cutoff = now_ts - LINK_LOCKOUT_SECONDS
        scopes = self._link_failure_scopes(discord_id, username)
        mapping = self._connect(self.mapping_db_path)
        try:
            self._create_link_failures_table(mapping)
            mapping.execute("DELETE FROM link_failures WHERE failed_at < ?", (cutoff,))
            for scope in scopes:
                row = mapping.execute(
                    """
                    SELECT COUNT(*) AS cnt, MIN(failed_at) AS oldest
                    FROM link_failures
                    WHERE scope_key = ? AND failed_at >= ?
                    """,
                    (scope, cutoff),
                ).fetchone()
                if row is not None and int(row["cnt"]) >= LINK_MAX_FAILURES:
                    oldest = int(row["oldest"] or now_ts)
                    wait_secs = max(60, oldest + LINK_LOCKOUT_SECONDS - now_ts)
                    wait_mins = (wait_secs + 59) // 60
                    mapping.commit()
                    raise PermissionDenied(
                        f"Too many failed `/link` attempts. Try again in {wait_mins} minute(s)."
                    )
            mapping.commit()
        finally:
            mapping.close()

    def _record_link_failure(self, discord_id: str | int, username: str, now_ts: int) -> None:
        scopes = self._link_failure_scopes(discord_id, username)
        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            self._create_link_failures_table(mapping)
            for scope in scopes:
                mapping.execute(
                    "INSERT INTO link_failures (scope_key, failed_at) VALUES (?, ?)",
                    (scope, now_ts),
                )
            mapping.commit()
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()

    def _clear_link_failures(self, mapping: sqlite3.Connection, discord_id: str | int, username: str) -> None:
        self._create_link_failures_table(mapping)
        for scope in self._link_failure_scopes(discord_id, username):
            mapping.execute("DELETE FROM link_failures WHERE scope_key = ?", (scope,))

    def link_account(
        self,
        discord_id: str | int,
        username: str,
        password: str,
        *,
        now_ts: Optional[int] = None,
    ) -> Account:
        validated_username = validate_username(username)
        validate_password(password)
        ts = int(time.time()) if now_ts is None else int(now_ts)

        self._check_link_lockout(discord_id, validated_username, ts)

        game = self._connect(self.game_db_path)
        try:
            row = game.execute(
                "SELECT user_id, name, password, user_code FROM user WHERE name = ?",
                (validated_username,),
            ).fetchone()
        finally:
            game.close()

        if row is None or not verify_password(password, row["password"]):
            self._record_link_failure(discord_id, validated_username, ts)
            raise AuthenticationFailed("Username or password is incorrect.")

        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            already_self = mapping.execute(
                "SELECT 1 FROM user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(row["user_id"])),
            ).fetchone()
            if already_self is not None:
                raise AccountConflict("This account is already linked to your Discord user.")
            linked_count = int(
                mapping.execute(
                    "SELECT COUNT(*) FROM user_mapping WHERE user_id = ?",
                    (int(row["user_id"]),),
                ).fetchone()[0]
            )
            if linked_count >= MAX_DISCORD_LINKS_PER_ACCOUNT:
                raise AccountConflict(
                    f"This account already has the maximum of {MAX_DISCORD_LINKS_PER_ACCOUNT} linked Discord accounts."
                )
            is_primary = 1 if linked_count == 0 else 0
            mapping.execute(
                """
                INSERT INTO user_mapping (
                    discord_id, user_id, username, user_code, is_primary
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(discord_id), int(row["user_id"]), row["name"], row["user_code"], is_primary),
            )
            self._clear_link_failures(mapping, discord_id, validated_username)
            account_row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary
                FROM user_mapping WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(row["user_id"])),
            ).fetchone()
            mapping.commit()
        except sqlite3.IntegrityError as error:
            mapping.rollback()
            raise AccountConflict("This account is already linked.") from error
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()

        return self._account_from_row(account_row)

    def rename_account(
        self,
        discord_id: str | int,
        user_id: int,
        new_username: str,
    ) -> Account:
        username = validate_username(new_username)
        connection = self._connect(self.game_db_path)
        try:
            connection.execute("ATTACH DATABASE ? AS botdb", (str(self.mapping_db_path),))
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at, is_primary
                FROM botdb.user_mapping
                WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            if owner is None:
                raise PermissionDenied("This Discord user does not own that account.")
            if not bool(owner["is_primary"]):
                raise PermissionDenied("Only the primary linked Discord account can perform this action.")

            conflict = connection.execute(
                "SELECT user_id FROM user WHERE name = ? AND user_id <> ?",
                (username, int(user_id)),
            ).fetchone()
            if conflict is not None:
                raise AccountConflict("Username already exists.")

            changed = connection.execute(
                "UPDATE user SET name = ? WHERE user_id = ?",
                (username, int(user_id)),
            ).rowcount
            if changed != 1:
                raise AccountNotFound("Account no longer exists.")
            connection.execute(
                "UPDATE botdb.user_mapping SET username = ? WHERE user_id = ?",
                (username, int(user_id)),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        accounts = [item for item in self.list_accounts(discord_id) if item.user_id == int(user_id)]
        if not accounts:
            raise AccountNotFound("Updated account mapping is missing.")
        return accounts[0]

    def reset_password(
        self,
        discord_id: str | int,
        user_id: int,
        new_password: str,
    ) -> int:
        password_hash = hash_password(new_password)
        connection = self._connect(self.game_db_path)
        try:
            connection.execute("ATTACH DATABASE ? AS botdb", (str(self.mapping_db_path),))
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT is_primary FROM botdb.user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            ).fetchone()
            if owner is None:
                raise PermissionDenied("This Discord user does not own that account.")
            if not bool(owner["is_primary"]):
                raise PermissionDenied("Only the primary linked Discord account can perform this action.")
            changed = connection.execute(
                "UPDATE user SET password = ? WHERE user_id = ?",
                (password_hash, int(user_id)),
            ).rowcount
            if changed != 1:
                raise AccountNotFound("Account no longer exists.")
            connection.execute("DELETE FROM login WHERE user_id = ?", (int(user_id),))
            unlinked_others = int(
                connection.execute(
                    "DELETE FROM botdb.user_mapping WHERE user_id = ? AND discord_id <> ?",
                    (int(user_id), str(discord_id)),
                ).rowcount
            )
            connection.commit()
            return unlinked_others
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def revoke_other_discords(self, discord_id: str | int, user_id: int) -> int:
        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            owner = mapping.execute(
                "SELECT is_primary FROM user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            ).fetchone()
            if owner is None:
                raise PermissionDenied("This Discord user does not own that account.")
            if not bool(owner["is_primary"]):
                raise PermissionDenied("Only the primary linked Discord account can perform this action.")
            removed = int(
                mapping.execute(
                    "DELETE FROM user_mapping WHERE user_id = ? AND discord_id <> ?",
                    (int(user_id), str(discord_id)),
                ).rowcount
            )
            mapping.commit()
            return removed
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()

    def _load_charts_unlocked(self, force: bool = False) -> dict[str, ChartInfo]:
        now = time.monotonic()
        if not force and self._chart_cache and (now - self._chart_cache_at) < CHART_CACHE_TTL_SECONDS:
            return self._chart_cache

        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            if "chart" not in tables:
                self._chart_cache = {}
                self._chart_cache_at = now
                return self._chart_cache

            rows = connection.execute(
                """
                SELECT song_id, name, rating_pst, rating_prs, rating_ftr, rating_byn, rating_etr
                FROM chart
                """
            ).fetchall()
        finally:
            connection.close()

        loaded: dict[str, ChartInfo] = {}
        cols = ("rating_pst", "rating_prs", "rating_ftr", "rating_byn", "rating_etr")
        for row in rows:
            constants: dict[int, float] = {}
            for diff_id, col in enumerate(cols):
                raw = row[col]
                if raw is not None and int(raw) > 0:
                    constants[diff_id] = round(int(raw) / 10.0, 1)
            sid = str(row["song_id"])
            title = str(row["name"] or sid)
            loaded[sid] = ChartInfo(song_id=sid, title=title, constants=constants)
        self._chart_cache = loaded
        self._chart_cache_at = now
        return loaded

    def search_charts(self, query: str, limit: int = 25) -> list[ChartInfo]:
        charts = self._load_charts_unlocked()
        q = query.strip().lower()
        if not q:
            items = sorted(
                charts.values(),
                key=lambda c: (-(max(c.constants.values()) if c.constants else 0.0), c.title.lower()),
            )
            return items[:limit]

        scored: list[tuple[int, str, ChartInfo]] = []
        for chart in charts.values():
            title_l = chart.title.lower()
            sid_l = chart.song_id.lower()
            if q == sid_l or q == title_l:
                rank = 0
            elif title_l.startswith(q) or sid_l.startswith(q):
                rank = 1
            elif q in title_l:
                rank = 2
            elif q in sid_l:
                rank = 3
            else:
                continue
            scored.append((rank, title_l, chart))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in scored[:limit]]

    def resolve_chart(
        self, query: str, difficulty: Optional[int] = None
    ) -> tuple[ChartInfo, int, Optional[float]]:
        q = query.strip()
        if not q:
            raise ValidationError("Provide a song name or ID.")
        charts = self._load_charts_unlocked()
        chart = charts.get(q) or charts.get(q.lower())
        if chart is None:
            matches = self.search_charts(q, limit=5)
            if not matches:
                raise AccountNotFound(f"No chart matching `{q}` was found.")
            chart = matches[0]

        if difficulty is not None:
            diff_id = int(difficulty)
            if diff_id not in DIFFICULTY_NAMES:
                raise ValidationError("Invalid difficulty.")
            if chart.constants and diff_id not in chart.constants:
                available = ", ".join(
                    f"{difficulty_name(d)} {cc:.1f}" for d, cc in sorted(chart.constants.items())
                )
                raise ValidationError(
                    f"`{chart.title}` does not have a `{difficulty_name(diff_id)}` chart. Available: {available}"
                )
            return chart, diff_id, chart.constants.get(diff_id)

        if chart.constants:
            best_diff = max(chart.constants.keys())
            return chart, best_diff, chart.constants.get(best_diff)
        return chart, 2, None

    def get_chart_info(self, query: str) -> ChartInfo:
        chart, _, _ = self.resolve_chart(query, None)
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            if "best_score" not in tables:
                return chart
            play_row = connection.execute(
                "SELECT COUNT(*) FROM best_score WHERE song_id = ?",
                (chart.song_id,),
            ).fetchone()
            play_count = int(play_row[0]) if play_row else 0
            top_row = None
            if chart.constants:
                pref_diff = max(chart.constants.keys())
                top_row = connection.execute(
                    """
                    SELECT b.score, b.difficulty, u.name
                    FROM best_score b
                    JOIN user u ON u.user_id = b.user_id
                    WHERE b.song_id = ? AND b.difficulty = ?
                    ORDER BY b.score DESC, b.time_played ASC
                    LIMIT 1
                    """,
                    (chart.song_id, pref_diff),
                ).fetchone()
            if top_row is None:
                top_row = connection.execute(
                    """
                    SELECT b.score, b.difficulty, u.name
                    FROM best_score b
                    JOIN user u ON u.user_id = b.user_id
                    WHERE b.song_id = ?
                    ORDER BY b.difficulty DESC, b.score DESC
                    LIMIT 1
                    """,
                    (chart.song_id,),
                ).fetchone()
        finally:
            connection.close()

        return ChartInfo(
            song_id=chart.song_id,
            title=chart.title,
            constants=chart.constants,
            play_count=play_count,
            top_score=int(top_row["score"]) if top_row else None,
            top_player=str(top_row["name"]) if top_row else None,
            top_difficulty=int(top_row["difficulty"]) if top_row else None,
        )

    def get_profile(self, user_id: int) -> Profile:
        charts = self._load_charts_unlocked()
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_cols = {row[1] for row in connection.execute("PRAGMA table_info(user)").fetchall()}
            has_user_char = "user_char" in tables
            has_best = "best_score" in tables
            has_recent = "recent30" in tables
            char_join = (
                "LEFT JOIN user_char uc ON uc.user_id = u.user_id AND uc.character_id = u.character_id"
                if has_user_char
                else ""
            )
            char_level_col = "uc.level AS character_level" if has_user_char else "NULL AS character_level"
            best_cnt_col = (
                "(SELECT COUNT(*) FROM best_score b WHERE b.user_id = u.user_id) AS best_score_count"
                if has_best
                else "0 AS best_score_count"
            )
            recent_cnt_col = (
                "(SELECT COUNT(*) FROM recent30 r WHERE r.user_id = u.user_id) AS recent_play_count"
                if has_recent
                else "0 AS recent_play_count"
            )
            hide_col = "COALESCE(u.is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            uncap_ov_col = "COALESCE(u.is_char_uncapped_override, 0)" if "is_char_uncapped_override" in user_cols else "0"
            uncap_col = "COALESCE(u.is_char_uncapped, 0)" if "is_char_uncapped" in user_cols else "0"
            last_sid_col = "u.song_id" if "song_id" in user_cols else "NULL"
            last_diff_col = "u.difficulty" if "difficulty" in user_cols else "NULL"
            last_score_col = "u.score" if "score" in user_cols else "NULL"
            row = connection.execute(
                f"""
                SELECT
                    u.user_id, u.name, u.user_code, u.rating_ptt,
                    u.character_id, u.join_date, u.is_profile_public,
                    {hide_col} AS is_hide_rating,
                    {uncap_ov_col} AS is_char_uncapped_override,
                    {uncap_col} AS is_char_uncapped,
                    {last_sid_col} AS last_song_id,
                    {last_diff_col} AS last_difficulty,
                    {last_score_col} AS last_score,
                    {char_level_col},
                    {best_cnt_col},
                    {recent_cnt_col}
                FROM user u
                {char_join}
                WHERE u.user_id = ?
                """,
                (int(user_id),),
            ).fetchone()
            if row is None:
                raise AccountNotFound("Account no longer exists.")

            rating_ptt = -1 if int(row["is_hide_rating"]) == 1 else row["rating_ptt"]
            rank_hide_expr = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            rank_row = connection.execute(
                f"""
                SELECT COUNT(*) FROM user
                WHERE (CASE WHEN {rank_hide_expr} = 1 THEN -1 ELSE COALESCE(rating_ptt, -1) END)
                    > (CASE WHEN ? < 0 OR ? IS NULL THEN -1 ELSE ? END)
                """,
                (rating_ptt, rating_ptt, rating_ptt),
            ).fetchone()
            server_rank = (int(rank_row[0]) + 1) if (rating_ptt is not None and int(rating_ptt) >= 0) else None

            b30_avg = 0.0
            r10_avg = 0.0
            pm_count = 0
            fr_count = 0
            ex_plus_count = 0
            if has_best:
                b30_rows = connection.execute(
                    "SELECT rating FROM best_score WHERE user_id = ? AND rating > 0 ORDER BY rating DESC LIMIT 30",
                    (int(user_id),),
                ).fetchall()
                if b30_rows:
                    b30_avg = sum(float(r["rating"]) for r in b30_rows) / 30.0
                agg = connection.execute(
                    """
                    SELECT
                        SUM(CASE WHEN COALESCE(best_clear_type, clear_type) = 3 THEN 1 ELSE 0 END) AS pm_cnt,
                        SUM(CASE WHEN COALESCE(best_clear_type, clear_type) = 2 THEN 1 ELSE 0 END) AS fr_cnt,
                        SUM(CASE WHEN score >= 9900000 THEN 1 ELSE 0 END) AS ex_plus_cnt
                    FROM best_score
                    WHERE user_id = ?
                    """,
                    (int(user_id),),
                ).fetchone()
                if agg is not None:
                    pm_count = int(agg["pm_cnt"] or 0)
                    fr_count = int(agg["fr_cnt"] or 0)
                    ex_plus_count = int(agg["ex_plus_cnt"] or 0)
            if has_recent:
                r10_rows = connection.execute(
                    "SELECT rating FROM recent30 WHERE user_id = ? AND rating > 0 ORDER BY rating DESC LIMIT 10",
                    (int(user_id),),
                ).fetchall()
                if r10_rows:
                    r10_avg = sum(float(r["rating"]) for r in r10_rows) / len(r10_rows)
        finally:
            connection.close()

        last_sid = str(row["last_song_id"]) if row["last_song_id"] else None
        last_title = charts[last_sid].title if last_sid and last_sid in charts else last_sid
        is_uncapped = bool(row["is_char_uncapped_override"]) or bool(row["is_char_uncapped"])
        return Profile(
            user_id=int(row["user_id"]),
            username=str(row["name"]),
            user_code=str(row["user_code"]),
            ptt=format_ptt(rating_ptt),
            character_id=row["character_id"],
            character_level=row["character_level"],
            joined_at=row["join_date"],
            best_score_count=int(row["best_score_count"]),
            recent_play_count=int(row["recent_play_count"]),
            is_public=bool(row["is_profile_public"]),
            server_rank=server_rank,
            b30_avg=b30_avg,
            r10_avg=r10_avg,
            pm_count=pm_count,
            fr_count=fr_count,
            ex_plus_count=ex_plus_count,
            is_char_uncapped=is_uncapped,
            last_song_id=last_sid,
            last_song_title=last_title,
            last_difficulty=int(row["last_difficulty"]) if row["last_difficulty"] is not None else None,
            last_score=int(row["last_score"]) if row["last_score"] is not None else None,
        )

    def _enrich_score_card(
        self,
        connection: sqlite3.Connection,
        tables: set[str],
        charts: dict[str, ChartInfo],
        *,
        user_id: int,
        username: str,
        user_ptt: str,
        user_code: str = "",
        character_id: Optional[int] = None,
        is_char_uncapped: bool = False,
        raw_ptt: int = -1,
        song_id: str,
        difficulty_id: int,
        score: int,
        clear_type_id: int,
        rating: float,
        time_played: int,
        pure_count: int,
        shiny_pure_count: int,
        near_count: int,
        miss_count: int,
        is_recent: bool,
        recent_index: int = 1,
        recent_total: int = 1,
        b30_map: Optional[dict[tuple[str, int], int]] = None,
    ) -> ScoreCardData:
        chart = charts.get(song_id)
        title = chart.title if chart else song_id
        constant = chart.constants.get(difficulty_id) if chart else None

        pb_score: Optional[int] = None
        pb_delta: Optional[int] = None
        chart_rank: Optional[int] = None
        chart_total_players = 0

        if "best_score" in tables:
            pb_row = connection.execute(
                "SELECT score FROM best_score WHERE user_id = ? AND song_id = ? AND difficulty = ?",
                (int(user_id), song_id, int(difficulty_id)),
            ).fetchone()
            if pb_row is not None:
                pb_score = int(pb_row["score"])
                pb_delta = int(score) - pb_score
            lb_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_players,
                    SUM(CASE WHEN score > ? THEN 1 ELSE 0 END) AS higher_count
                FROM best_score
                WHERE song_id = ? AND difficulty = ?
                """,
                (pb_score if pb_score is not None else int(score), song_id, int(difficulty_id)),
            ).fetchone()
            if lb_row is not None and int(lb_row["total_players"]) > 0:
                chart_total_players = int(lb_row["total_players"])
                if pb_score is not None or not is_recent:
                    chart_rank = int(lb_row["higher_count"] or 0) + 1

        b30_rank = b30_map.get((song_id, difficulty_id)) if b30_map else None

        return ScoreCardData(
            username=username,
            user_ptt=user_ptt,
            song_id=song_id,
            song_title=title,
            difficulty_id=int(difficulty_id),
            difficulty=difficulty_name(difficulty_id),
            constant=constant,
            score=int(score),
            grade=score_grade(score),
            clear_type_id=int(clear_type_id),
            clear_type=clear_type_name(clear_type_id),
            clear_short=clear_type_short(clear_type_id),
            pure_count=int(pure_count),
            shiny_pure_count=int(shiny_pure_count),
            near_count=int(near_count),
            miss_count=int(miss_count),
            rating=float(rating),
            time_played=normalize_timestamp_seconds(time_played),
            is_recent=is_recent,
            recent_index=recent_index,
            recent_total=recent_total,
            pb_score=pb_score,
            pb_delta=pb_delta,
            b30_rank=b30_rank,
            chart_rank=chart_rank,
            chart_total_players=chart_total_players,
            user_code=user_code,
            character_id=character_id,
            is_char_uncapped=is_char_uncapped,
            raw_ptt=raw_ptt,
        )

    @staticmethod
    def _load_b30_rank_map(
        connection: sqlite3.Connection, tables: set[str], user_id: int
    ) -> dict[tuple[str, int], int]:
        if "best_score" not in tables:
            return {}
        rows = connection.execute(
            """
            SELECT song_id, difficulty
            FROM best_score
            WHERE user_id = ? AND rating > 0
            ORDER BY rating DESC
            LIMIT 30
            """,
            (int(user_id),),
        ).fetchall()
        return {
            (str(row["song_id"]), int(row["difficulty"])): idx
            for idx, row in enumerate(rows, 1)
        }

    def get_recent_score_cards(self, user_id: int, limit: int = 30) -> list[ScoreCardData]:
        bounded_limit = max(1, min(int(limit), 30))
        charts = self._load_charts_unlocked()
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_cols = {row[1] for row in connection.execute("PRAGMA table_info(user)").fetchall()}
            hide_col = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            ucode_col = "user_code" if "user_code" in user_cols else "''"
            char_col = "character_id" if "character_id" in user_cols else "NULL"
            uncap_ov_col = "COALESCE(is_char_uncapped_override, 0)" if "is_char_uncapped_override" in user_cols else "0"
            uncap_col = "COALESCE(is_char_uncapped, 0)" if "is_char_uncapped" in user_cols else "0"
            extra_cols = []
            for col, default in (
                ("song_id", "NULL"),
                ("difficulty", "NULL"),
                ("score", "0"),
                ("shiny_perfect_count", "0"),
                ("perfect_count", "0"),
                ("near_count", "0"),
                ("miss_count", "0"),
                ("clear_type", "0"),
                ("rating", "0.0"),
                ("time_played", "0"),
            ):
                extra_cols.append(f"{col}" if col in user_cols else f"{default} AS {col}")
            user_row = connection.execute(
                f"SELECT name, rating_ptt, {hide_col} AS is_hide_rating, {ucode_col} AS user_code, "
                f"{char_col} AS character_id, {uncap_ov_col} AS is_char_uncapped_override, "
                f"{uncap_col} AS is_char_uncapped, {', '.join(extra_cols)} "
                "FROM user WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])
            raw_ptt = -1 if int(user_row["is_hide_rating"]) == 1 or user_row["rating_ptt"] is None else int(user_row["rating_ptt"])
            user_ptt = format_ptt(raw_ptt)
            user_code = str(user_row["user_code"] or "")
            character_id = int(user_row["character_id"]) if user_row["character_id"] is not None else None
            is_uncapped = bool(user_row["is_char_uncapped_override"]) or bool(user_row["is_char_uncapped"])
            b30_map = self._load_b30_rank_map(connection, tables, user_id)

            rows = []
            if "recent30" in tables:
                rows = connection.execute(
                    """
                    SELECT
                        song_id, difficulty, score, clear_type, rating, time_played,
                        perfect_count, shiny_perfect_count, near_count, miss_count
                    FROM recent30
                    WHERE user_id = ?
                    ORDER BY time_played DESC, r_index DESC
                    LIMIT ?
                    """,
                    (int(user_id), bounded_limit),
                ).fetchall()

            if not rows and user_row["song_id"]:
                rows = [
                    {
                        "song_id": user_row["song_id"],
                        "difficulty": user_row["difficulty"] if user_row["difficulty"] is not None else 2,
                        "score": user_row["score"] or 0,
                        "clear_type": user_row["clear_type"] or 0,
                        "rating": user_row["rating"] or 0.0,
                        "time_played": user_row["time_played"] or 0,
                        "perfect_count": user_row["perfect_count"] or 0,
                        "shiny_perfect_count": user_row["shiny_perfect_count"] or 0,
                        "near_count": user_row["near_count"] or 0,
                        "miss_count": user_row["miss_count"] or 0,
                    }
                ]

            total = len(rows)
            cards: list[ScoreCardData] = []
            for idx, row in enumerate(rows, 1):
                cards.append(
                    self._enrich_score_card(
                        connection,
                        tables,
                        charts,
                        user_id=user_id,
                        username=username,
                        user_ptt=user_ptt,
                        user_code=user_code,
                        character_id=character_id,
                        is_char_uncapped=is_uncapped,
                        raw_ptt=raw_ptt,
                        song_id=str(row["song_id"]),
                        difficulty_id=int(row["difficulty"]),
                        score=int(row["score"] or 0),
                        clear_type_id=int(row["clear_type"] or 0),
                        rating=float(row["rating"] or 0.0),
                        time_played=int(row["time_played"] or 0),
                        pure_count=int(row["perfect_count"] or 0),
                        shiny_pure_count=int(row["shiny_perfect_count"] or 0),
                        near_count=int(row["near_count"] or 0),
                        miss_count=int(row["miss_count"] or 0),
                        is_recent=True,
                        recent_index=idx,
                        recent_total=total,
                        b30_map=b30_map,
                    )
                )
            return cards
        finally:
            connection.close()

    def get_recent_scores(self, user_id: int, limit: int = 5) -> list[RecentScore]:
        cards = self.get_recent_score_cards(user_id, limit=min(int(limit), 30))
        return [
            RecentScore(
                song_id=c.song_id,
                difficulty=c.difficulty,
                score=c.score,
                clear_type=c.clear_type,
                rating=c.rating,
                time_played=c.time_played,
                pure_count=c.pure_count,
                shiny_pure_count=c.shiny_pure_count,
                near_count=c.near_count,
                miss_count=c.miss_count,
                difficulty_id=c.difficulty_id,
                song_title=c.song_title,
                constant=c.constant,
                clear_type_id=c.clear_type_id,
                pb_score=c.pb_score,
                pb_delta=c.pb_delta,
                b30_rank=c.b30_rank,
                chart_rank=c.chart_rank,
                chart_total_players=c.chart_total_players,
            )
            for c in cards
        ]

    def get_user_chart_score(
        self, user_id: int, query: str, difficulty: Optional[int] = None
    ) -> ScoreCardData:
        chart, diff_id, _ = self.resolve_chart(query, difficulty)
        charts = self._load_charts_unlocked()
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_cols = {row[1] for row in connection.execute("PRAGMA table_info(user)").fetchall()}
            hide_col = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            ucode_col = "user_code" if "user_code" in user_cols else "''"
            char_col = "character_id" if "character_id" in user_cols else "NULL"
            uncap_ov_col = "COALESCE(is_char_uncapped_override, 0)" if "is_char_uncapped_override" in user_cols else "0"
            uncap_col = "COALESCE(is_char_uncapped, 0)" if "is_char_uncapped" in user_cols else "0"
            user_row = connection.execute(
                f"SELECT name, rating_ptt, {hide_col} AS is_hide_rating, {ucode_col} AS user_code, "
                f"{char_col} AS character_id, {uncap_ov_col} AS is_char_uncapped_override, "
                f"{uncap_col} AS is_char_uncapped FROM user WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])
            raw_ptt = -1 if int(user_row["is_hide_rating"]) == 1 or user_row["rating_ptt"] is None else int(user_row["rating_ptt"])
            user_ptt = format_ptt(raw_ptt)
            user_code = str(user_row["user_code"] or "")
            character_id = int(user_row["character_id"]) if user_row["character_id"] is not None else None
            is_uncapped = bool(user_row["is_char_uncapped_override"]) or bool(user_row["is_char_uncapped"])

            if "best_score" not in tables:
                raise AccountNotFound(
                    f"`{username}` has no recorded score on `{chart.title}` [{difficulty_name(diff_id)}]."
                )

            row = connection.execute(
                """
                SELECT
                    song_id, difficulty, score, COALESCE(best_clear_type, clear_type) AS clear_type,
                    rating, time_played, perfect_count, shiny_perfect_count, near_count, miss_count
                FROM best_score
                WHERE user_id = ? AND song_id = ? AND difficulty = ?
                """,
                (int(user_id), chart.song_id, int(diff_id)),
            ).fetchone()

            if row is None and difficulty is None:
                alt = connection.execute(
                    """
                    SELECT
                        song_id, difficulty, score, COALESCE(best_clear_type, clear_type) AS clear_type,
                        rating, time_played, perfect_count, shiny_perfect_count, near_count, miss_count
                    FROM best_score
                    WHERE user_id = ? AND song_id = ?
                    ORDER BY difficulty DESC
                    LIMIT 1
                    """,
                    (int(user_id), chart.song_id),
                ).fetchone()
                if alt is not None:
                    row = alt
                    diff_id = int(alt["difficulty"])

            if row is None:
                raise AccountNotFound(
                    f"`{username}` has no recorded score on `{chart.title}` [{difficulty_name(diff_id)}]."
                )

            b30_map = self._load_b30_rank_map(connection, tables, user_id)
            return self._enrich_score_card(
                connection,
                tables,
                charts,
                user_id=user_id,
                username=username,
                user_ptt=user_ptt,
                user_code=user_code,
                character_id=character_id,
                is_char_uncapped=is_uncapped,
                raw_ptt=raw_ptt,
                song_id=chart.song_id,
                difficulty_id=diff_id,
                score=int(row["score"] or 0),
                clear_type_id=int(row["clear_type"] or 0),
                rating=float(row["rating"] or 0.0),
                time_played=int(row["time_played"] or 0),
                pure_count=int(row["perfect_count"] or 0),
                shiny_pure_count=int(row["shiny_perfect_count"] or 0),
                near_count=int(row["near_count"] or 0),
                miss_count=int(row["miss_count"] or 0),
                is_recent=False,
                recent_index=1,
                recent_total=1,
                b30_map=b30_map,
            )
        finally:
            connection.close()

    def get_chart_leaderboard(
        self,
        query: str,
        difficulty: Optional[int] = None,
        *,
        page: int = 1,
        page_size: int = 10,
        viewer_user_id: Optional[int] = None,
    ) -> ChartLeaderboardPage:
        chart, diff_id, constant = self.resolve_chart(query, difficulty)
        bounded_size = max(1, min(int(page_size), 20))
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            if "best_score" not in tables:
                return ChartLeaderboardPage(
                    chart=chart,
                    difficulty_id=diff_id,
                    constant=constant,
                    entries=(),
                    page=1,
                    page_count=1,
                    total_entries=0,
                    viewer_entry=None,
                )

            total_entries = int(
                connection.execute(
                    "SELECT COUNT(*) FROM best_score WHERE song_id = ? AND difficulty = ?",
                    (chart.song_id, int(diff_id)),
                ).fetchone()[0]
            )
            page_count = max(1, (total_entries + bounded_size - 1) // bounded_size)
            current_page = max(1, min(int(page), page_count))
            offset = (current_page - 1) * bounded_size

            rows = connection.execute(
                """
                SELECT
                    b.user_id, u.name, b.score, COALESCE(b.best_clear_type, b.clear_type) AS ct,
                    b.perfect_count, b.shiny_perfect_count, b.near_count, b.miss_count,
                    b.rating, b.time_played
                FROM best_score b
                JOIN user u ON u.user_id = b.user_id
                WHERE b.song_id = ? AND b.difficulty = ?
                ORDER BY b.score DESC, b.shiny_perfect_count DESC, b.time_played ASC
                LIMIT ? OFFSET ?
                """,
                (chart.song_id, int(diff_id), bounded_size, offset),
            ).fetchall()

            entries = tuple(
                ChartLeaderboardEntry(
                    rank=offset + idx,
                    user_id=int(r["user_id"]),
                    username=str(r["name"]),
                    score=int(r["score"] or 0),
                    grade=score_grade(r["score"] or 0),
                    clear_short=clear_type_short(r["ct"] or 0),
                    pure_count=int(r["perfect_count"] or 0),
                    shiny_pure_count=int(r["shiny_perfect_count"] or 0),
                    near_count=int(r["near_count"] or 0),
                    miss_count=int(r["miss_count"] or 0),
                    rating=float(r["rating"] or 0.0),
                    time_played=normalize_timestamp_seconds(r["time_played"]),
                )
                for idx, r in enumerate(rows, 1)
            )

            viewer_entry: Optional[ChartLeaderboardEntry] = None
            if viewer_user_id is not None:
                vrow = connection.execute(
                    """
                    SELECT
                        b.user_id, u.name, b.score, COALESCE(b.best_clear_type, b.clear_type) AS ct,
                        b.perfect_count, b.shiny_perfect_count, b.near_count, b.miss_count,
                        b.rating, b.time_played
                    FROM best_score b
                    JOIN user u ON u.user_id = b.user_id
                    WHERE b.song_id = ? AND b.difficulty = ? AND b.user_id = ?
                    """,
                    (chart.song_id, int(diff_id), int(viewer_user_id)),
                ).fetchone()
                if vrow is not None:
                    higher = int(
                        connection.execute(
                            """
                            SELECT COUNT(*) FROM best_score
                            WHERE song_id = ? AND difficulty = ?
                              AND (score > ? OR (score = ? AND shiny_perfect_count > ?))
                            """,
                            (
                                chart.song_id,
                                int(diff_id),
                                int(vrow["score"] or 0),
                                int(vrow["score"] or 0),
                                int(vrow["shiny_perfect_count"] or 0),
                            ),
                        ).fetchone()[0]
                    )
                    viewer_entry = ChartLeaderboardEntry(
                        rank=higher + 1,
                        user_id=int(vrow["user_id"]),
                        username=str(vrow["name"]),
                        score=int(vrow["score"] or 0),
                        grade=score_grade(vrow["score"] or 0),
                        clear_short=clear_type_short(vrow["ct"] or 0),
                        pure_count=int(vrow["perfect_count"] or 0),
                        shiny_pure_count=int(vrow["shiny_perfect_count"] or 0),
                        near_count=int(vrow["near_count"] or 0),
                        miss_count=int(vrow["miss_count"] or 0),
                        rating=float(vrow["rating"] or 0.0),
                        time_played=normalize_timestamp_seconds(vrow["time_played"]),
                    )
        finally:
            connection.close()

        return ChartLeaderboardPage(
            chart=chart,
            difficulty_id=diff_id,
            constant=constant,
            entries=entries,
            page=current_page,
            page_count=page_count,
            total_entries=total_entries,
            viewer_entry=viewer_entry,
        )

    def get_top_scores(
        self,
        user_id: int,
        *,
        difficulty: Optional[int] = None,
        min_cc: Optional[float] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> TopScoresPage:
        charts = self._load_charts_unlocked()
        bounded_size = max(1, min(int(page_size), 15))
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_row = connection.execute(
                "SELECT name FROM user WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])
            if "best_score" not in tables:
                return TopScoresPage(
                    username=username, entries=(), page=1, page_count=1, total_entries=0, b30_avg=0.0
                )

            b30_map = self._load_b30_rank_map(connection, tables, user_id)
            rows = connection.execute(
                """
                SELECT
                    song_id, difficulty, score, COALESCE(best_clear_type, clear_type) AS ct,
                    rating, time_played
                FROM best_score
                WHERE user_id = ? AND rating > 0
                ORDER BY rating DESC, score DESC
                """,
                (int(user_id),),
            ).fetchall()
        finally:
            connection.close()

        b30_ratings = [float(r["rating"]) for r in rows[:30]]
        b30_avg = sum(b30_ratings) / 30.0 if b30_ratings else 0.0

        filtered: list[TopScoreEntry] = []
        for r in rows:
            sid = str(r["song_id"])
            diff_id = int(r["difficulty"])
            if difficulty is not None and diff_id != int(difficulty):
                continue
            chart = charts.get(sid)
            const = chart.constants.get(diff_id) if chart else None
            if min_cc is not None and (const is None or const + 1e-9 < float(min_cc)):
                continue
            filtered.append(
                TopScoreEntry(
                    rank=len(filtered) + 1,
                    b30_rank=b30_map.get((sid, diff_id)),
                    song_id=sid,
                    song_title=chart.title if chart else sid,
                    difficulty_id=diff_id,
                    difficulty=difficulty_name(diff_id),
                    constant=const,
                    score=int(r["score"] or 0),
                    grade=score_grade(r["score"] or 0),
                    clear_short=clear_type_short(r["ct"] or 0),
                    rating=float(r["rating"] or 0.0),
                    time_played=normalize_timestamp_seconds(r["time_played"]),
                )
            )

        total_entries = len(filtered)
        page_count = max(1, (total_entries + bounded_size - 1) // bounded_size)
        current_page = max(1, min(int(page), page_count))
        offset = (current_page - 1) * bounded_size
        return TopScoresPage(
            username=username,
            entries=tuple(filtered[offset : offset + bounded_size]),
            page=current_page,
            page_count=page_count,
            total_entries=total_entries,
            b30_avg=b30_avg,
        )

    def get_whatif_summary(self, user_id: int) -> WhatIfSummary:
        charts = self._load_charts_unlocked()
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_cols = {row[1] for row in connection.execute("PRAGMA table_info(user)").fetchall()}
            hide_col = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            user_row = connection.execute(
                f"SELECT name, rating_ptt, {hide_col} AS is_hide_rating FROM user WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])
            ptt = format_ptt(-1 if int(user_row["is_hide_rating"]) == 1 else user_row["rating_ptt"])

            best_rows = (
                connection.execute(
                    "SELECT song_id, difficulty, score, rating FROM best_score WHERE user_id = ? AND rating > 0 ORDER BY rating DESC",
                    (int(user_id),),
                ).fetchall()
                if "best_score" in tables
                else []
            )
            r10_rows = (
                connection.execute(
                    "SELECT rating FROM recent30 WHERE user_id = ? AND rating > 0 ORDER BY rating DESC LIMIT 10",
                    (int(user_id),),
                ).fetchall()
                if "recent30" in tables
                else []
            )
        finally:
            connection.close()

        top30 = best_rows[:30]
        b30_sum = sum(float(r["rating"]) for r in top30)
        b30_avg = b30_sum / 30.0 if top30 else 0.0
        b30_ceiling = float(top30[0]["rating"]) if top30 else 0.0
        b30_floor = float(top30[-1]["rating"]) if len(top30) >= 30 else 0.0
        r10_avg = sum(float(r["rating"]) for r in r10_rows) / len(r10_rows) if r10_rows else 0.0

        pb_by_chart: dict[tuple[str, int], tuple[int, float]] = {
            (str(r["song_id"]), int(r["difficulty"])): (int(r["score"]), float(r["rating"]))
            for r in best_rows
        }
        in_top30: dict[tuple[str, int], float] = {
            (str(r["song_id"]), int(r["difficulty"])): float(r["rating"])
            for r in top30
        }

        candidates: list[tuple[float, WhatIfRecommendation]] = []
        ref_level = max(7.0, b30_floor if len(top30) >= 30 else (b30_ceiling - 0.5 if top30 else 8.5))
        for chart in charts.values():
            for diff_id, const in chart.constants.items():
                if const + 1.5 < b30_floor:
                    continue
                if const > ref_level + 1.6 and (chart.song_id, diff_id) not in pb_by_chart:
                    continue
                cur = pb_by_chart.get((chart.song_id, diff_id))
                cur_score = cur[0] if cur else None
                if cur_score is not None and cur_score >= 9_960_000:
                    continue
                if cur_score is None or cur_score < 9_800_000:
                    target_score = 9_850_000 if const >= ref_level - 0.2 else 9_920_000
                elif cur_score < 9_900_000:
                    target_score = 9_920_000
                else:
                    target_score = min(9_980_000, max(cur_score + 30_000, 9_960_000))
                proj_r = calculate_play_rating(const, target_score)
                baseline = in_top30.get((chart.song_id, diff_id), b30_floor)
                gain_rating = proj_r - baseline
                if gain_rating <= 0.02:
                    continue
                b30_gain = gain_rating / 30.0
                closeness = abs(const - ref_level)
                priority = b30_gain * 100.0 - closeness * 0.4 + (0.6 if cur_score else 0.0)
                candidates.append(
                    (
                        priority,
                        WhatIfRecommendation(
                            song_id=chart.song_id,
                            song_title=chart.title,
                            difficulty_id=diff_id,
                            difficulty=difficulty_name(diff_id),
                            constant=const,
                            current_score=cur_score,
                            target_score=target_score,
                            projected_rating=proj_r,
                            b30_gain=b30_gain,
                        ),
                    )
                )

        candidates.sort(key=lambda item: item[0], reverse=True)
        recs = tuple(item[1] for item in candidates[:5])
        return WhatIfSummary(
            username=username,
            ptt=ptt,
            b30_avg=b30_avg,
            r10_avg=r10_avg,
            b30_ceiling=b30_ceiling,
            b30_floor=b30_floor,
            b30_count=len(top30),
            recommendations=recs,
        )

    def simulate_whatif_chart(
        self,
        user_id: int,
        query: str,
        difficulty: Optional[int] = None,
        target_score: Optional[int] = None,
    ) -> WhatIfChartResult:
        chart, diff_id, constant = self.resolve_chart(query, difficulty)
        if constant is None or constant <= 0:
            raise ValidationError(f"`{chart.title}` [{difficulty_name(diff_id)}] has no valid chart constant.")
        if target_score is not None and not (0 <= int(target_score) <= 10_005_000):
            raise ValidationError("Target score must be between 0 and 10,005,000.")

        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_row = connection.execute(
                "SELECT name FROM user WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])

            top30 = (
                connection.execute(
                    "SELECT song_id, difficulty, score, rating FROM best_score WHERE user_id = ? AND rating > 0 ORDER BY rating DESC LIMIT 30",
                    (int(user_id),),
                ).fetchall()
                if "best_score" in tables
                else []
            )
            pb_row = (
                connection.execute(
                    "SELECT score, rating FROM best_score WHERE user_id = ? AND song_id = ? AND difficulty = ?",
                    (int(user_id), chart.song_id, int(diff_id)),
                ).fetchone()
                if "best_score" in tables
                else None
            )
        finally:
            connection.close()

        b30_sum = sum(float(r["rating"]) for r in top30)
        b30_avg = b30_sum / 30.0 if top30 else 0.0
        b30_floor = float(top30[-1]["rating"]) if len(top30) >= 30 else 0.0

        current_pb = int(pb_row["score"]) if pb_row is not None else None
        current_rating = float(pb_row["rating"]) if pb_row is not None else 0.0
        in_top30_rating = next(
            (float(r["rating"]) for r in top30 if str(r["song_id"]) == chart.song_id and int(r["difficulty"]) == diff_id),
            None,
        )
        baseline = in_top30_rating if in_top30_rating is not None else b30_floor

        score_enter = score_for_target_rating(constant, b30_floor) if b30_floor > 0 else 9_000_000
        milestones = tuple(
            (label, score_for_target_rating(constant, baseline + delta * 30.0))
            for label, delta in (("+0.01", 0.01), ("+0.02", 0.02), ("+0.05", 0.05))
        )

        sim_rating: Optional[float] = None
        sim_new_b30: Optional[float] = None
        sim_delta: Optional[float] = None
        if target_score is not None:
            sim_rating = calculate_play_rating(constant, int(target_score))
            if sim_rating > baseline:
                sim_new_b30 = (b30_sum - baseline + sim_rating) / 30.0
            else:
                sim_new_b30 = b30_avg
            sim_delta = sim_new_b30 - b30_avg

        return WhatIfChartResult(
            username=username,
            chart=chart,
            difficulty_id=diff_id,
            constant=constant,
            b30_avg=b30_avg,
            b30_floor=b30_floor,
            current_pb=current_pb,
            current_rating=current_rating,
            score_to_enter_b30=score_enter,
            milestones=milestones,
            simulated_score=int(target_score) if target_score is not None else None,
            simulated_rating=sim_rating,
            simulated_new_b30=sim_new_b30,
            simulated_b30_delta=sim_delta,
        )

    def get_progress_summary(
        self, user_id: int, difficulty_filter: Optional[int] = None
    ) -> ProgressSummary:
        charts = self._load_charts_unlocked()
        connection = self._connect(self.game_db_path)
        try:
            tables = self._existing_tables(connection)
            user_row = connection.execute(
                "SELECT name FROM user WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            if user_row is None:
                raise AccountNotFound("Account no longer exists.")
            username = str(user_row["name"])
            rows = (
                connection.execute(
                    "SELECT song_id, difficulty, score, COALESCE(best_clear_type, clear_type) AS ct FROM best_score WHERE user_id = ?",
                    (int(user_id),),
                ).fetchall()
                if "best_score" in tables
                else []
            )
        finally:
            connection.close()

        counts: dict[str, dict[str, int]] = {
            b: {"total": 0, "played": 0, "cleared": 0, "ex": 0, "ex_plus": 0, "fr": 0, "pm": 0}
            for b in LEVEL_BUCKET_ORDER
        }
        for chart in charts.values():
            for diff_id, const in chart.constants.items():
                if difficulty_filter is not None and diff_id != int(difficulty_filter):
                    continue
                counts[level_bucket(const)]["total"] += 1

        total_played = 0
        total_pm = 0
        total_fr = 0
        total_ex_plus = 0
        for row in rows:
            sid = str(row["song_id"])
            diff_id = int(row["difficulty"])
            if difficulty_filter is not None and diff_id != int(difficulty_filter):
                continue
            chart = charts.get(sid)
            if not chart or diff_id not in chart.constants:
                continue
            bucket = level_bucket(chart.constants[diff_id])
            st = counts[bucket]
            sc = int(row["score"] or 0)
            ct = int(row["ct"] or 0)
            st["played"] += 1
            total_played += 1
            if ct != 0:
                st["cleared"] += 1
            if sc >= 9_800_000:
                st["ex"] += 1
            if sc >= 9_900_000:
                st["ex_plus"] += 1
                total_ex_plus += 1
            if ct == 2:
                st["fr"] += 1
                total_fr += 1
            elif ct == 3:
                st["pm"] += 1
                total_pm += 1

        buckets = tuple(
            ProgressBucket(
                label=b,
                total_charts=counts[b]["total"],
                played=counts[b]["played"],
                cleared=counts[b]["cleared"],
                ex_count=counts[b]["ex"],
                ex_plus_count=counts[b]["ex_plus"],
                fr_count=counts[b]["fr"],
                pm_count=counts[b]["pm"],
            )
            for b in LEVEL_BUCKET_ORDER
            if counts[b]["total"] > 0 or counts[b]["played"] > 0
        )
        return ProgressSummary(
            username=username,
            difficulty_filter=difficulty_filter,
            buckets=buckets,
            total_played=total_played,
            total_pm=total_pm,
            total_fr=total_fr,
            total_ex_plus=total_ex_plus,
        )

    def get_random_chart(
        self,
        *,
        min_cc: float = 8.0,
        max_cc: float = 11.5,
        difficulty: Optional[int] = None,
    ) -> tuple[ChartInfo, int, float]:
        lo = float(min_cc)
        hi = float(max_cc)
        if lo > hi:
            raise ValidationError("`min_cc` cannot be greater than `max_cc`.")
        charts = self._load_charts_unlocked()
        pool: list[tuple[ChartInfo, int, float]] = []
        for chart in charts.values():
            for diff_id, const in chart.constants.items():
                if difficulty is not None and diff_id != int(difficulty):
                    continue
                if lo - 1e-9 <= const <= hi + 1e-9:
                    pool.append((chart, diff_id, const))
        if not pool:
            raise AccountNotFound(f"No charts match constant {lo:.1f}–{hi:.1f}.")
        return random.choice(pool)

    def compare_scores(
        self,
        query: str,
        difficulty: Optional[int],
        left_user_id: int,
        right_user_id: Optional[int] = None,
    ) -> CompareResult:
        chart, diff_id, constant = self.resolve_chart(query, difficulty)

        def _try_get(uid: int) -> tuple[str, Optional[ScoreCardData]]:
            prof = self.get_profile(uid)
            try:
                card = self.get_user_chart_score(uid, chart.song_id, diff_id)
                return prof.username, card
            except AccountNotFound:
                return prof.username, None

        left_name, left_card = _try_get(left_user_id)
        right_name: Optional[str] = None
        right_card: Optional[ScoreCardData] = None
        if right_user_id is not None and right_user_id != left_user_id:
            right_name, right_card = _try_get(right_user_id)

        return CompareResult(
            chart=chart,
            difficulty_id=diff_id,
            constant=constant,
            left_username=left_name,
            left_score=left_card,
            right_username=right_name,
            right_score=right_card,
        )

    def get_ranking_page(self, page: int, page_size: int = 5) -> RankingPage:
        bounded_size = max(1, min(int(page_size), 25))
        connection = self._connect(self.game_db_path)
        try:
            user_cols = {row[1] for row in connection.execute("PRAGMA table_info(user)").fetchall()}
            hide_expr = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
            total_players = int(
                connection.execute("SELECT COUNT(*) FROM user").fetchone()[0]
            )
            page_count = max(1, (total_players + bounded_size - 1) // bounded_size)
            current_page = max(1, min(int(page), page_count))
            offset = (current_page - 1) * bounded_size
            rows = connection.execute(
                f"""
                SELECT
                    user_id, name,
                    CASE
                        WHEN {hide_expr} = 1 THEN -1
                        ELSE COALESCE(rating_ptt, -1)
                    END AS public_rating_ptt
                FROM user
                ORDER BY public_rating_ptt DESC, user_id ASC
                LIMIT ? OFFSET ?
                """,
                (bounded_size, offset),
            ).fetchall()
        finally:
            connection.close()

        entries = tuple(
            RankingEntry(
                rank=offset + index,
                username=str(row["name"]),
                ptt=format_ptt(row["public_rating_ptt"]),
            )
            for index, row in enumerate(rows, 1)
        )
        return RankingPage(
            entries=entries,
            page=current_page,
            page_count=page_count,
            total_players=total_players,
        )
