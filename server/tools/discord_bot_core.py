from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9]{3,16}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 32

DIFFICULTY_NAMES = {
    0: "PST",
    1: "PRS",
    2: "FTR",
    3: "BYD",
    4: "ETR",
}

CLEAR_TYPE_NAMES = {
    0: "TRACK LOST",
    1: "NORMAL CLEAR",
    2: "FULL RECALL",
    3: "PURE MEMORY",
    4: "EASY CLEAR",
    5: "HARD CLEAR",
}


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
    created_at: str | None = None


@dataclass(frozen=True)
class Profile:
    user_id: int
    username: str
    user_code: str
    ptt: str
    character_id: int | None
    character_level: int | None
    joined_at: str | None
    best_score_count: int
    recent_play_count: int
    is_public: bool


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


def format_ptt(rating_ptt: int | None) -> str:
    if rating_ptt is None or int(rating_ptt) < 0:
        return "Hidden"
    return f"{int(rating_ptt) / 100:.2f}"


def difficulty_name(difficulty: int) -> str:
    value = int(difficulty)
    return DIFFICULTY_NAMES.get(value, f"D{value}")


def clear_type_name(clear_type: int) -> str:
    value = int(clear_type)
    return CLEAR_TYPE_NAMES.get(value, f"CLEAR {value}")


class BotRepository:
    def __init__(self, game_db_path: str | Path, mapping_db_path: str | Path) -> None:
        self.game_db_path = Path(game_db_path)
        self.mapping_db_path = Path(mapping_db_path)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def migrate_mapping_schema(self) -> None:
        connection = self._connect(self.mapping_db_path)
        try:
            self._create_external_api_key_table(connection)
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
            if "password" not in columns:
                self._create_mapping_indexes(connection)
                connection.commit()
                return

            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE IF EXISTS user_mapping_v2")
            self._create_mapping_table(connection, table_name="user_mapping_v2")
            connection.execute(
                """
                INSERT OR IGNORE INTO user_mapping_v2 (
                    discord_id, user_id, username, user_code, created_at
                )
                SELECT
                    CAST(discord_id AS TEXT), CAST(user_id AS INTEGER),
                    username, user_code, created_at
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
                user_id INTEGER NOT NULL UNIQUE,
                username TEXT NOT NULL,
                user_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_id, user_id),
                UNIQUE (discord_id, username)
            )
            """
        )

    @staticmethod
    def _create_mapping_indexes(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_mapping_discord_id "
            "ON user_mapping(discord_id)"
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
        return Account(
            discord_id=str(row["discord_id"]),
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            user_code=str(row["user_code"]),
            created_at=row["created_at"],
        )

    def list_accounts(self, discord_id: str | int) -> list[Account]:
        connection = self._connect(self.mapping_db_path)
        try:
            rows = connection.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at
                FROM user_mapping
                WHERE discord_id = ?
                ORDER BY created_at DESC, user_id DESC
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
                SELECT discord_id, user_id, username, user_code, created_at
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
            mapping.execute(
                """
                INSERT INTO user_mapping (
                    discord_id, user_id, username, user_code
                ) VALUES (?, ?, ?, ?)
                """,
                (str(discord_id), int(user_id), value, str(user_code)),
            )
            account_row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at
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
                SELECT discord_id, user_id, username, user_code, created_at
                FROM user_mapping WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            if row is None:
                raise PermissionDenied("This Discord user does not own that account.")
            mapping.execute(
                "DELETE FROM user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            )
            mapping.commit()
        except Exception:
            mapping.rollback()
            raise
        finally:
            mapping.close()
        return self._account_from_row(row)

    def link_account(
        self,
        discord_id: str | int,
        username: str,
        password: str,
    ) -> Account:
        validated_username = validate_username(username)
        validate_password(password)

        game = self._connect(self.game_db_path)
        try:
            row = game.execute(
                "SELECT user_id, name, password, user_code FROM user WHERE name = ?",
                (validated_username,),
            ).fetchone()
        finally:
            game.close()

        if row is None or not verify_password(password, row["password"]):
            raise AuthenticationFailed("Username or password is incorrect.")

        mapping = self._connect(self.mapping_db_path)
        try:
            mapping.execute("BEGIN IMMEDIATE")
            mapping.execute(
                """
                INSERT INTO user_mapping (
                    discord_id, user_id, username, user_code
                ) VALUES (?, ?, ?, ?)
                """,
                (str(discord_id), int(row["user_id"]), row["name"], row["user_code"]),
            )
            account_row = mapping.execute(
                """
                SELECT discord_id, user_id, username, user_code, created_at
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
                SELECT discord_id, user_id, username, user_code, created_at
                FROM botdb.user_mapping
                WHERE discord_id = ? AND user_id = ?
                """,
                (str(discord_id), int(user_id)),
            ).fetchone()
            if owner is None:
                raise PermissionDenied("This Discord user does not own that account.")

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
    ) -> None:
        password_hash = hash_password(new_password)
        connection = self._connect(self.game_db_path)
        try:
            connection.execute("ATTACH DATABASE ? AS botdb", (str(self.mapping_db_path),))
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT 1 FROM botdb.user_mapping WHERE discord_id = ? AND user_id = ?",
                (str(discord_id), int(user_id)),
            ).fetchone()
            if owner is None:
                raise PermissionDenied("This Discord user does not own that account.")
            changed = connection.execute(
                "UPDATE user SET password = ? WHERE user_id = ?",
                (password_hash, int(user_id)),
            ).rowcount
            if changed != 1:
                raise AccountNotFound("Account no longer exists.")
            connection.execute("DELETE FROM login WHERE user_id = ?", (int(user_id),))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_profile(self, user_id: int) -> Profile:
        connection = self._connect(self.game_db_path)
        try:
            row = connection.execute(
                """
                SELECT
                    u.user_id, u.name, u.user_code, u.rating_ptt,
                    u.character_id, u.join_date, u.is_profile_public,
                    uc.level AS character_level,
                    (SELECT COUNT(*) FROM best_score b WHERE b.user_id = u.user_id)
                        AS best_score_count,
                    (SELECT COUNT(*) FROM recent30 r WHERE r.user_id = u.user_id)
                        AS recent_play_count
                FROM user u
                LEFT JOIN user_char uc
                    ON uc.user_id = u.user_id AND uc.character_id = u.character_id
                WHERE u.user_id = ?
                """,
                (int(user_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            raise AccountNotFound("Account no longer exists.")
        return Profile(
            user_id=int(row["user_id"]),
            username=str(row["name"]),
            user_code=str(row["user_code"]),
            ptt=format_ptt(row["rating_ptt"]),
            character_id=row["character_id"],
            character_level=row["character_level"],
            joined_at=row["join_date"],
            best_score_count=int(row["best_score_count"]),
            recent_play_count=int(row["recent_play_count"]),
            is_public=bool(row["is_profile_public"]),
        )

    def get_recent_scores(self, user_id: int, limit: int = 5) -> list[RecentScore]:
        bounded_limit = max(1, min(int(limit), 10))
        connection = self._connect(self.game_db_path)
        try:
            rows = connection.execute(
                """
                SELECT
                    song_id, difficulty, score, clear_type, rating, time_played,
                    perfect_count, shiny_perfect_count, near_count, miss_count
                FROM recent30
                WHERE user_id = ?
                ORDER BY time_played DESC
                LIMIT ?
                """,
                (int(user_id), bounded_limit),
            ).fetchall()
        finally:
            connection.close()

        return [
            RecentScore(
                song_id=str(row["song_id"]),
                difficulty=difficulty_name(row["difficulty"]),
                score=int(row["score"]),
                clear_type=clear_type_name(row["clear_type"]),
                rating=float(row["rating"]),
                time_played=int(row["time_played"]),
                pure_count=int(row["perfect_count"]),
                shiny_pure_count=int(row["shiny_perfect_count"]),
                near_count=int(row["near_count"]),
                miss_count=int(row["miss_count"]),
            )
            for row in rows
        ]
