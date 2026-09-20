import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path


SERVER_ROOT = Path(os.environ.get("ARCAEA_SERVER_ROOT", Path(__file__).resolve().parents[1]))
DB_PATH = SERVER_ROOT / "database" / "arcaea_database.db"
BUNDLE_DIR = SERVER_ROOT / "database" / "bundle"
APP_VERSION = "6.14.11"


def load_songlist():
    manifest = json.loads((BUNDLE_DIR / f"{APP_VERSION}.json").read_text())
    entry = next(item for item in manifest["added"] if item["path"] == "songs/songlist")
    part_path = BUNDLE_DIR / f"{APP_VERSION}_{entry['partIndex']}.cb"
    with part_path.open("rb") as part:
        part.seek(entry["byteOffset"])
        return json.loads(part.read(entry["length"]))


def find_missing_self_purchased_singles(conn, songlist):
    conn.row_factory = sqlite3.Row
    purchase_names = {
        row["purchase_name"]
        for row in conn.execute("select purchase_name from purchase")
    }
    purchase_items = {
        (row["purchase_name"], row["item_id"], row["type"])
        for row in conn.execute("select purchase_name, item_id, type from purchase_item")
    }
    items = {
        (row["item_id"], row["type"]): row["is_available"]
        for row in conn.execute("select item_id, type, is_available from item")
    }

    missing = []
    for song in songlist["songs"]:
        song_id = song.get("id")
        purchase = song.get("purchase")
        if song.get("set") != "single" or not purchase:
            continue
        # Some old single-set songs use a pack purchase, e.g. guardina -> dynamix.
        # Only self-purchased Memory Archive style singles should have a single item.
        if purchase != song_id:
            continue

        issue = {
            "idx": song.get("idx"),
            "id": song_id,
            "title": (song.get("title_localized") or {}).get("en"),
            "purchase": purchase,
            "date": song.get("date"),
            "date_utc": (
                dt.datetime.utcfromtimestamp(int(song["date"])).strftime("%Y-%m-%d")
                if song.get("date")
                else None
            ),
            "missing_purchase": purchase not in purchase_names,
            "missing_purchase_item": (purchase, purchase, "single") not in purchase_items,
            "missing_item": (purchase, "single") not in items,
            "item_not_available": (
                (purchase, "single") in items and items[(purchase, "single")] != 1
            ),
        }
        if (
            issue["missing_purchase"]
            or issue["missing_purchase_item"]
            or issue["missing_item"]
            or issue["item_not_available"]
        ):
            missing.append(issue)
    return missing


def apply_fixes(conn, missing):
    cur = conn.cursor()
    users = [row[0] for row in cur.execute("select user_id from user")]
    for issue in missing:
        purchase = issue["purchase"]
        cur.execute(
            "insert or ignore into purchase values (?, ?, ?, ?, ?, ?)",
            (purchase, 100, 100, -1, -1, ""),
        )
        cur.execute(
            "insert or ignore into purchase_item values (?, ?, ?, ?)",
            (purchase, purchase, "single", 1),
        )
        cur.execute(
            "insert or ignore into item values (?, ?, ?)",
            (purchase, "single", 1),
        )
        cur.execute(
            "update item set is_available = 1 where item_id = ? and type = 'single'",
            (purchase,),
        )
        for user_id in users:
            cur.execute(
                "insert or ignore into user_item values (?, ?, ?, ?)",
                (user_id, purchase, "single", 1),
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    songlist = load_songlist()
    conn = sqlite3.connect(DB_PATH)
    try:
        missing = find_missing_self_purchased_singles(conn, songlist)
        result = {
            "mode": "apply" if args.apply else "dry_run",
            "missing_count": len(missing),
            "missing": missing,
        }

        if args.apply:
            backup = (
                DB_PATH.parent
                / f"arcaea_database.db.bak-pre-missing-single-purchases-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            shutil.copy2(DB_PATH, backup)
            apply_fixes(conn, missing)
            conn.commit()
            after = find_missing_self_purchased_singles(conn, songlist)
            result["backup"] = str(backup)
            result["remaining_count"] = len(after)
            result["remaining"] = after
        else:
            conn.rollback()

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
