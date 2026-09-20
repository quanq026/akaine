import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
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


def upsert_user_item(cur, user_id, item_id, item_type, amount):
    amount = 1 if amount is None else int(amount)
    cur.execute(
        "SELECT amount FROM user_item WHERE user_id = ? AND item_id = ? AND type = ?",
        (user_id, item_id, item_type),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO user_item (user_id, item_id, type, amount) VALUES (?, ?, ?, ?)",
            (user_id, item_id, item_type, amount),
        )
        return "inserted"

    current_amount = 0 if row["amount"] is None else int(row["amount"])
    if current_amount < amount:
        cur.execute(
            "UPDATE user_item SET amount = ? WHERE user_id = ? AND item_id = ? AND type = ?",
            (amount, user_id, item_id, item_type),
        )
        return "updated"
    return "unchanged"


def grant_current_entitlements(cur, user_id):
    """Grant current catalogue entitlements without reading another user's state."""
    stats = {
        "purchase_item_inserted": 0,
        "purchase_item_updated": 0,
        "available_item_inserted": 0,
        "available_item_updated": 0,
    }

    cur.execute(
        """
        SELECT item_id, type, MAX(COALESCE(amount, 1)) AS amount
        FROM purchase_item
        GROUP BY item_id, type
        """
    )
    for row in cur.fetchall():
        result = upsert_user_item(cur, user_id, row["item_id"], row["type"], row["amount"])
        if result == "inserted":
            stats["purchase_item_inserted"] += 1
        elif result == "updated":
            stats["purchase_item_updated"] += 1

    cur.execute(
        """
        SELECT item_id, type
        FROM item
        WHERE is_available = 1
        """
    )
    for row in cur.fetchall():
        result = upsert_user_item(cur, user_id, row["item_id"], row["type"], 1)
        if result == "inserted":
            stats["available_item_inserted"] += 1
        elif result == "updated":
            stats["available_item_updated"] += 1

    return stats


def verify_created_account(cur, user_id):
    """Fail the transaction instead of committing a partially provisioned account."""
    expected_characters = cur.execute("SELECT COUNT(*) FROM character").fetchone()[0]
    actual_characters = cur.execute(
        "SELECT COUNT(*) FROM user_char_full WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    missing_entitlements = cur.execute(
        """
        WITH expected AS (
            SELECT item_id, type, MAX(amount) AS amount
            FROM (
                SELECT item_id, type, COALESCE(amount, 1) AS amount FROM purchase_item
                UNION ALL
                SELECT item_id, type, 1 AS amount FROM item WHERE is_available = 1
            )
            GROUP BY item_id, type
        )
        SELECT COUNT(*)
        FROM expected e
        LEFT JOIN user_item u
          ON u.user_id = ? AND u.item_id = e.item_id AND u.type = e.type
        WHERE u.user_id IS NULL OR COALESCE(u.amount, 0) < e.amount
        """,
        (user_id,),
    ).fetchone()[0]
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


def create_account(database, username, password, email=None, dry_run=False):
    database = resolve_database_path(database)
    username = username.strip()
    password = password.strip()
    if not username or not password:
        raise ValueError("username and password are required")
    email = email.strip() if email else f"{username}@example.local"

    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
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
    parser.add_argument("password", nargs="?", help="The password for the new account")
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

        if not args.username or not args.password:
            raise ValueError("username and password are required unless --repair-existing is used")
        print(
            json.dumps(
                create_account(
                    database,
                    args.username,
                    args.password,
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
