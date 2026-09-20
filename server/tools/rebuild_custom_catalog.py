import base64
import hashlib
import hmac
import json
import os
import shutil
import time
from pathlib import Path


SERVER_ROOT = Path(os.environ.get("ARCAEA_SERVER_ROOT", Path(__file__).resolve().parents[1]))
APP_VERSION = "6.14.11"
DETAIL_HASH_KEY = bytes.fromhex(
    "d41fdbe337d001680c2a4d43afe570c71fde85d8f3d4c46f"
    "3799c18f1f508277aca7ab633283710c2bb41a078efbe7c1"
    "9cf087a7e137752ab7581c8d9c0e3de9"
)


def digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def detail_digest(data: bytes) -> str:
    return base64.b64encode(hmac.new(DETAIL_HASH_KEY, data, hashlib.sha256).digest()).decode()


def extract_bundle_file(bundle_dir: Path, manifest: dict, path: str):
    entry = next(item for item in manifest["added"] if item["path"] == path)
    part = bundle_dir / f"{APP_VERSION}_{entry['partIndex']}.cb"
    with part.open("rb") as f:
        f.seek(entry["byteOffset"])
        return f.read(entry["length"]), entry


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def merge_by_id(items, extras):
    output = list(items)
    index_by_id = {item["id"]: index for index, item in enumerate(output)}
    for item in extras:
        existing_index = index_by_id.get(item["id"])
        if existing_index is None:
            index_by_id[item["id"]] = len(output)
            output.append(item)
        else:
            output[existing_index] = item
    return output


def update_manifest_entry(
    manifest: dict,
    path: str,
    payload: bytes,
    part_index: int,
    byte_offset: int,
    with_detail_hash: bool = False,
):
    file_hash = digest(payload)
    manifest["pathToHash"][path] = file_hash
    if with_detail_hash:
        manifest["pathToDetails"][path] = detail_digest(payload)
    else:
        manifest.get("pathToDetails", {}).pop(path, None)

    target_entry = next((item for item in manifest["added"] if item["path"] == path), None)
    if target_entry is None:
        target_entry = {"path": path}
        manifest["added"].append(target_entry)
    target_entry["partIndex"] = part_index
    target_entry["byteOffset"] = byte_offset
    target_entry["length"] = len(payload)
    target_entry["sha256HashBase64Encoded"] = file_hash


def patch_live_bundle(bundle_dir: Path, manifest_path: Path, updated_manifest: dict, payloads: dict):
    part_index = 0
    part_path = bundle_dir / f"{APP_VERSION}_{part_index}.cb"
    backup_dir = bundle_dir.parent / "bundle_backups" / f"custom-catalog-{time.strftime('%Y%m%d-%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, backup_dir / manifest_path.name)
    shutil.copy2(part_path, backup_dir / part_path.name)

    part_tmp = part_path.with_suffix(part_path.suffix + ".tmp")
    shutil.copy2(part_path, part_tmp)
    with part_tmp.open("ab") as f:
        for path, payload in payloads.items():
            offset = f.tell()
            f.write(payload)
            update_manifest_entry(
                updated_manifest,
                path,
                payload,
                part_index,
                offset,
                with_detail_hash=path in {"songs/songlist", "songs/packlist", "songs/unlocks"},
            )
    part_tmp.replace(part_path)

    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_tmp.write_text(
        json.dumps(updated_manifest, separators=(",", ":")),
        encoding="utf-8",
    )
    manifest_tmp.replace(manifest_path)
    return backup_dir


def main():
    bundle_dir = SERVER_ROOT / "database" / "bundle"
    source_dir = SERVER_ROOT / "database" / "custom_catalog_source"
    output_dir = SERVER_ROOT / "database" / "songs" / "_custom_catalog"
    output_songs_dir = output_dir / "songs"
    output_songs_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = bundle_dir / f"{APP_VERSION}.json"
    manifest = read_json(manifest_path)

    songlist_raw, songlist_entry = extract_bundle_file(bundle_dir, manifest, "songs/songlist")
    packlist_raw, packlist_entry = extract_bundle_file(bundle_dir, manifest, "songs/packlist")
    unlocks_raw, unlocks_entry = extract_bundle_file(bundle_dir, manifest, "songs/unlocks")

    songlist = json.loads(songlist_raw)
    packlist = json.loads(packlist_raw)

    song_entries_dir = source_dir / "song_entries"
    pack_entries_dir = source_dir / "pack_entries"
    assets_dir = source_dir / "assets"
    extra_songs = [
        read_json(path)
        for path in sorted(song_entries_dir.glob("*.json"))
    ] if song_entries_dir.is_dir() else []
    extra_packs = [
        read_json(path)
        for path in sorted(pack_entries_dir.glob("*.json"))
    ] if pack_entries_dir.is_dir() else []

    songlist["songs"] = merge_by_id(songlist.get("songs", []), extra_songs)
    packlist["packs"] = merge_by_id(packlist.get("packs", []), extra_packs)

    payloads = {
        "songs/songlist": json.dumps(songlist, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "songs/packlist": json.dumps(packlist, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "songs/unlocks": unlocks_raw,
    }

    if assets_dir.is_dir():
        for asset_path in sorted(path for path in assets_dir.rglob("*") if path.is_file()):
            bundle_path = asset_path.relative_to(assets_dir).as_posix()
            payloads[bundle_path] = asset_path.read_bytes()

    for pack in extra_packs:
        fallback_pack_image_path = f"songs/pack/1080_select_{pack['id']}.png"
        if (
            fallback_pack_image_path not in payloads
            and not any(item["path"] == fallback_pack_image_path for item in manifest["added"])
        ):
            base_pack_image, _ = extract_bundle_file(
                bundle_dir,
                manifest,
                "songs/pack/1080_select_base.png",
            )
            payloads[fallback_pack_image_path] = base_pack_image

    updated_manifest = json.loads(json.dumps(manifest))
    for path, payload in payloads.items():
        source_entry = {
            "songs/songlist": songlist_entry,
            "songs/packlist": packlist_entry,
            "songs/unlocks": unlocks_entry,
        }.get(path)
        if source_entry is None:
            continue
        update_manifest_entry(
            updated_manifest,
            path,
            payload,
            source_entry["partIndex"],
            source_entry["byteOffset"],
            with_detail_hash=True,
        )

    (output_songs_dir / "songlist").write_bytes(payloads["songs/songlist"])
    (output_songs_dir / "packlist").write_bytes(payloads["songs/packlist"])
    (output_songs_dir / "unlocks").write_bytes(payloads["songs/unlocks"])
    backup_dir = patch_live_bundle(bundle_dir, manifest_path, updated_manifest, payloads)
    (output_dir / "meta.cb").write_text(
        json.dumps(updated_manifest, separators=(",", ":")),
        encoding="utf-8",
    )
    report = {
        "songs": len(songlist["songs"]),
        "packs": len(packlist["packs"]),
        "extra_songs": [song["id"] for song in extra_songs],
        "extra_packs": [pack["id"] for pack in extra_packs],
        "output": str(output_dir),
        "patched_bundle": str(manifest_path),
        "backup": str(backup_dir),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
