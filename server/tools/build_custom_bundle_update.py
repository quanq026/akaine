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
BASE_BUNDLE_VERSION = "6.14.11"
CUSTOM_BUNDLE_VERSION = os.environ.get("ARCAEA_CUSTOM_BUNDLE_VERSION", "6.14.12")
DETAIL_HASH_KEY = bytes.fromhex(
    "d41fdbe337d001680c2a4d43afe570c71fde85d8f3d4c46f"
    "3799c18f1f508277aca7ab633283710c2bb41a078efbe7c1"
    "9cf087a7e137752ab7581c8d9c0e3de9"
)


def digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def detail_digest(data: bytes) -> str:
    return base64.b64encode(hmac.new(DETAIL_HASH_KEY, data, hashlib.sha256).digest()).decode()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_bundle_file(bundle_dir: Path, manifest: dict, path: str) -> bytes:
    entry = next(item for item in manifest["added"] if item["path"] == path)
    part = bundle_dir / f"{BASE_BUNDLE_VERSION}_{entry['partIndex']}.cb"
    with part.open("rb") as f:
        f.seek(entry["byteOffset"])
        return f.read(entry["length"])


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


def add_payload(manifest: dict, part_file, path: str, payload: bytes, detail: bool = False):
    offset = part_file.tell()
    part_file.write(payload)
    file_hash = digest(payload)
    manifest["added"].append({
        "path": path,
        "byteOffset": offset,
        "length": len(payload),
        "partIndex": 0,
        "sha256HashBase64Encoded": file_hash,
    })
    manifest["pathToHash"][path] = file_hash
    if detail:
        manifest["pathToDetails"][path] = detail_digest(payload)


def main():
    bundle_dir = SERVER_ROOT / "database" / "bundle"
    source_dir = SERVER_ROOT / "database" / "custom_catalog_source"
    output_dir = SERVER_ROOT / "database" / "songs" / "_custom_catalog"
    output_songs_dir = output_dir / "songs"
    output_songs_dir.mkdir(parents=True, exist_ok=True)

    base_manifest_path = bundle_dir / f"{BASE_BUNDLE_VERSION}.json"
    base_manifest = read_json(base_manifest_path)

    songlist = json.loads(extract_bundle_file(bundle_dir, base_manifest, "songs/songlist"))
    packlist = json.loads(extract_bundle_file(bundle_dir, base_manifest, "songs/packlist"))

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
    }

    if assets_dir.is_dir():
        for asset_path in sorted(path for path in assets_dir.rglob("*") if path.is_file()):
            payloads[asset_path.relative_to(assets_dir).as_posix()] = asset_path.read_bytes()

    for pack in extra_packs:
        fallback_pack_image_path = f"songs/pack/1080_select_{pack['id']}.png"
        if fallback_pack_image_path not in payloads:
            payloads[fallback_pack_image_path] = extract_bundle_file(
                bundle_dir,
                base_manifest,
                "songs/pack/1080_select_base.png",
            )

    update_manifest = {
        "versionNumber": CUSTOM_BUNDLE_VERSION,
        "previousVersionNumber": BASE_BUNDLE_VERSION,
        "applicationVersionNumber": APP_VERSION,
        "uuid": hashlib.sha1(f"{CUSTOM_BUNDLE_VERSION}-{time.time()}".encode()).hexdigest()[:9],
        "removed": [],
        "generatedUnixTimestamp": int(time.time()),
        "totalPartitions": 1,
        "added": [],
        "pathToHash": {},
        "pathToDetails": {},
    }

    manifest_path = bundle_dir / f"{CUSTOM_BUNDLE_VERSION}.json"
    part_path = bundle_dir / f"{CUSTOM_BUNDLE_VERSION}.cb"
    backup_dir = bundle_dir.parent / "bundle_backups" / f"custom-update-{time.strftime('%Y%m%d-%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for existing in (manifest_path, part_path):
        if existing.exists():
            shutil.copy2(existing, backup_dir / existing.name)

    part_tmp = part_path.with_suffix(part_path.suffix + ".tmp")
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with part_tmp.open("wb") as part_file:
        for path, payload in payloads.items():
            add_payload(
                update_manifest,
                part_file,
                path,
                payload,
                detail=path in {"songs/songlist", "songs/packlist", "songs/unlocks"},
            )
    manifest_tmp.write_text(json.dumps(update_manifest, separators=(",", ":")), encoding="utf-8")
    part_tmp.replace(part_path)
    manifest_tmp.replace(manifest_path)

    (output_songs_dir / "songlist").write_bytes(payloads["songs/songlist"])
    (output_songs_dir / "packlist").write_bytes(payloads["songs/packlist"])
    (output_dir / "meta.cb").write_text(json.dumps(update_manifest, separators=(",", ":")), encoding="utf-8")

    report = {
        "base_bundle_version": BASE_BUNDLE_VERSION,
        "custom_bundle_version": CUSTOM_BUNDLE_VERSION,
        "songs": len(songlist["songs"]),
        "packs": len(packlist["packs"]),
        "extra_songs": [song["id"] for song in extra_songs],
        "extra_packs": [pack["id"] for pack in extra_packs],
        "payload_paths": sorted(payloads.keys()),
        "patched_bundle": str(manifest_path),
        "part": str(part_path),
        "backup": str(backup_dir),
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
