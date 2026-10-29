import argparse
import getpass
import hashlib
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

from discord_bot_core import validate_password, validate_username


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
from core.content_grants import grant_missing_content, missing_content_count

FALLBACK_DEFAULT_MEMORIES = 67
FALLBACK_BOOTSTRAP_MISSIONS = (
    "mission_1_1_tutorial",
    "mission_1_2_clearsong",
    "mission_1_3_settings",
    "mission_1_4_allsongsview",
    "mission_1_5_fragunlock",
    "mission_1_end",
    "mission_2_1_account",
    "mission_2_2_profile",
    "mission_2_3_partner",
    "mission_2_5_prologuestart",
)


def resolve_database_path(value=None):
    path = Path(value).expanduser() if value else SERVER_ROOT / "database" / "arcaea_database.db"
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError("database file was not found")
    return path


def configured_default_memories():
    try:
        root_text = str(SERVER_ROOT)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        from core.config_manager import Config

        return int(Config.DEFAULT_MEMORIES)
    except Exception:
        return FALLBACK_DEFAULT_MEMORIES


def bootstrap_mission_ids():
    try:
        root_text = str(SERVER_ROOT)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        from core.mission import MISSION_STATE_BOOTSTRAP_IDS

        return tuple(MISSION_STATE_BOOTSTRAP_IDS)
    except Exception:
        return FALLBACK_BOOTSTRAP_MISSIONS


def grant_current_entitlements(cur, user_id):
    """Use the same additive nonconsumable policy as API registration and repair."""
    return grant_missing_content(cur, user_id)


def verify_created_account(cur, user_id):
    """Fail the transaction instead of committing a partially provisioned account."""
    expected_characters = cur.execute("SELECT COUNT(*) FROM character").fetchone()[0]
    actual_characters = cur.execute(
        "SELECT COUNT(*) FROM user_char_full WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    missing_entitlements = missing_content_count(cur, user_id)
    if actual_characters != expected_characters or missing_entitlements:
        raise RuntimeError("account provisioning verification failed")
    return {
        "full_character_count": actual_characters,
        "missing_entitlement_count": missing_entitlements,
    }


def initialize_default_characters(cur, user_id):
    cur.execute(
        """
        INSERT INTO user_char
        (user_id, character_id, level, exp, is_uncapped, is_uncapped_override, skill_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, 0, 1, 0, 0, 0, 0),
    )
    cur.execute(
        """
        INSERT INTO user_char
        (user_id, character_id, level, exp, is_uncapped, is_uncapped_override, skill_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, 1, 1, 0, 0, 0, 0),
    )

    cur.execute("SELECT character_id, max_level, is_uncapped FROM character")
    full_count = 0
    for row in cur.fetchall():
        max_level = int(row["max_level"])
        exp = 25000 if max_level == 30 else 10000
        cur.execute(
            """
            INSERT OR REPLACE INTO user_char_full
            (user_id, character_id, level, exp, is_uncapped, is_uncapped_override, skill_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, row["character_id"], max_level, exp, row["is_uncapped"], 0, 0),
        )
        full_count += 1
    return full_count


def initialize_bootstrap_missions(cur, user_id):
    cur.execute("SELECT EXISTS(SELECT 1 FROM user_mission WHERE user_id = ?)", (user_id,))
    if cur.fetchone()[0]:
        return 0
    missions = tuple(bootstrap_mission_ids())
    cur.executemany(
        "INSERT OR IGNORE INTO user_mission (user_id, mission_id, status) VALUES (?, ?, 4)",
        [(user_id, mission_id) for mission_id in missions],
    )
    return len(missions)


def provision_account(cur, username, password, email=None, dry_run=False):
    """Provision inside the caller's transaction; never commits or closes it."""
    username = validate_username(username)
    password = validate_password(password)
    email = email.strip() if email else f"{username}@example.local"
    cur.execute("SELECT 1 FROM user WHERE name = ?", (username,))
    if cur.fetchone():
        raise ValueError("username already exists")

    cur.execute("SELECT MAX(user_id) FROM user")
    max_id = cur.fetchone()[0]
    user_id = int(max_id) + 1 if max_id is not None else 2000001

    cur.execute("SELECT user_code FROM user")
    existing_codes = {str(row["user_code"]) for row in cur.fetchall() if row["user_code"] is not None}
    while True:
        user_code = str(random.randint(100000000, 999999999))
        if user_code not in existing_codes:
            break

    now = str(int(time.time() * 1000))
    cur.execute(
        """
        INSERT INTO user
        (user_id, name, password, join_date, user_code, rating_ptt, character_id,
         is_skill_sealed, is_char_uncapped, is_char_uncapped_override, is_hide_rating,
         favorite_character, max_stamina_notification_enabled, current_map, ticket,
         prog_boost, email)
        VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, -1, 0, '', ?, 0, ?)
        """,
        (
            user_id,
            username,
            hashlib.sha256(password.encode("utf8")).hexdigest(),
            now,
            user_code,
            configured_default_memories(),
            email,
        ),
    )

    full_character_count = initialize_default_characters(cur, user_id)
    mission_count = initialize_bootstrap_missions(cur, user_id)
    entitlement_results = grant_current_entitlements(cur, user_id)
    verification = verify_created_account(cur, user_id)

    result = {
        "status": "success",
        "dry_run": dry_run,
        "user_id": user_id,
        "username": username,
        "user_code": user_code,
        "email": email,
        "initialization": {
            "full_character_count": full_character_count,
            "bootstrap_mission_count": mission_count,
        },
        "entitlement_reconcile": entitlement_results,
        "verification": verification,
    }
    return result


def create_account(database, username, password, email=None, dry_run=False):
    database = resolve_database_path(database)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = provision_account(conn.cursor(), username, password, email=email, dry_run=dry_run)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def repair_existing_users(cur, target):
    if target == "all":
        cur.execute("SELECT user_id, name FROM user ORDER BY user_id")
    else:
        cur.execute("SELECT user_id, name FROM user WHERE user_id = ?", (int(target),))

    users = cur.fetchall()
    results = {}
    for user in users:
        results[str(user["user_id"])] = {
            "username": user["name"],
            "entitlements": grant_current_entitlements(cur, user["user_id"]),
        }
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Create an independent Arcaea Private Server account from explicit defaults."
    )
    parser.add_argument("username", nargs="?", help="The username for the new account")
    parser.add_argument("password", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--password-stdin", action="store_true", help="Read the password from bounded stdin instead of process arguments")
    parser.add_argument("--email", help="Optional email (defaults to username@example.local)")
    parser.add_argument("--database", help="Explicit database path for isolated staging tests")
    parser.add_argument("--dry-run", action="store_true", help="Run all DB work and then roll it back")
    parser.add_argument("--repair-existing", help="Repair entitlements for an existing user_id or 'all'")
    args = parser.parse_args()

    try:
        database = resolve_database_path(args.database)
        if args.repair_existing:
            conn = sqlite3.connect(database)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.cursor()
                cur.execute("BEGIN IMMEDIATE")
                repair_results = repair_existing_users(cur, args.repair_existing)
                if args.dry_run:
                    conn.rollback()
                else:
                    conn.commit()
            finally:
                conn.close()
            print(
                json.dumps(
                    {
                        "status": "success",
                        "mode": "repair_existing",
                        "dry_run": args.dry_run,
                        "target": args.repair_existing,
                        "users": repair_results,
                    },
                    indent=2,
                )
            )
            return

        if args.password is not None:
            raise ValueError("Password arguments are disabled; use --password-stdin or an interactive prompt")
        if not args.username:
            raise ValueError("username is required unless --repair-existing is used")
        if args.password_stdin:
            raw = sys.stdin.buffer.read(131)
            if len(raw) > 130:
                raise ValueError("password input is too long")
            password = raw.decode("utf-8").removesuffix("\n").removesuffix("\r")
        elif sys.stdin.isatty():
            password = getpass.getpass("Password: ")
        else:
            raise ValueError("Use --password-stdin or an interactive prompt")
        print(
            json.dumps(
                create_account(
                    database,
                    args.username,
                    password,
                    email=args.email,
                    dry_run=args.dry_run,
                ),
                indent=2,
            )
        )
    except Exception:
        print(json.dumps({"status": "error", "message": "account creation failed"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
