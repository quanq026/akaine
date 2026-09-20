import base64
import hashlib
import json
import os
import sys
from pathlib import Path


APP_VERSION = "6.14.11"
REQUIRED_PATHS = [
    "songs/songlist",
    "songs/packlist",
    "songs/unlocks",
    "songs/executioner/2.aff",
    "songs/executioner/base.jpg",
    "songs/executioner/base.ogg",
    "songs/executioner/base_256.jpg",
    "songs/pack/1080_select_fanmade.png",
]


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        os.environ.get("ARCAEA_SERVER_ROOT", Path(__file__).resolve().parents[1])
    )
    manifest = json.loads((root / "database" / "bundle" / f"{APP_VERSION}.json").read_text(encoding="utf-8"))

    for path in REQUIRED_PATHS:
        entry = next((item for item in manifest["added"] if item["path"] == path), None)
        if entry is None:
            raise AssertionError(f"missing manifest entry: {path}")
        part_path = root / "database" / "bundle" / f"{APP_VERSION}_{entry['partIndex']}.cb"
        part = part_path.read_bytes()
        start = entry["byteOffset"]
        end = start + entry["length"]
        if end > len(part):
            raise AssertionError(f"entry outside part bounds: {path}")
        payload = part[start:end]
        file_hash = base64.b64encode(hashlib.sha256(payload).digest()).decode()
        if file_hash != entry["sha256HashBase64Encoded"] or file_hash != manifest["pathToHash"][path]:
            raise AssertionError(f"hash mismatch: {path}")

    songlist_entry = next(item for item in manifest["added"] if item["path"] == "songs/songlist")
    songlist_part = (root / "database" / "bundle" / f"{APP_VERSION}_{songlist_entry['partIndex']}.cb").read_bytes()
    songlist = json.loads(
        songlist_part[
            songlist_entry["byteOffset"] : songlist_entry["byteOffset"] + songlist_entry["length"]
        ]
    )
    song = next((item for item in songlist["songs"] if item["id"] == "executioner"), None)
    if song is None:
        raise AssertionError("executioner missing from songlist")

    packlist_entry = next(item for item in manifest["added"] if item["path"] == "songs/packlist")
    packlist_part = (root / "database" / "bundle" / f"{APP_VERSION}_{packlist_entry['partIndex']}.cb").read_bytes()
    packlist = json.loads(
        packlist_part[
            packlist_entry["byteOffset"] : packlist_entry["byteOffset"] + packlist_entry["length"]
        ]
    )
    pack = next((item for item in packlist["packs"] if item["id"] == "fanmade"), None)
    if pack is None:
        raise AssertionError("fanmade missing from packlist")

    print(json.dumps({
        "required_paths": len(REQUIRED_PATHS),
        "detail_paths": sorted(manifest["pathToDetails"].keys()),
        "song": song,
        "pack": pack,
        "backup_in_bundle": (root / "database" / "bundle" / "backups").exists(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
