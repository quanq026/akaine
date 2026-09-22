"""Build and verify a 7.0.255 full-root content bundle from a known-good root."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import shutil
import tempfile
import time
from pathlib import Path, PurePosixPath


APP_VERSION = "7.0.255"
DEFAULT_MAX_PART_BYTES = 480 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_bundle_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "\\" not in value


def source_part(source: Path, index: int) -> Path:
    return source / f"source_{index}.cb"


def read_span(source: Path, row: dict) -> bytes:
    with source_part(source, row["partIndex"]).open("rb") as stream:
        stream.seek(row["byteOffset"])
        data = stream.read(row["length"])
    require(len(data) == row["length"], f"source-span-short:{row['path']}")
    return data


def validate_source(source: Path, manifest: dict) -> None:
    require(manifest.get("applicationVersionNumber") == APP_VERSION, "source-app-version-mismatch")
    require(manifest.get("previousVersionNumber") is None, "source-is-not-full-root")
    require(manifest.get("removed") == [], "source-root-has-removed-paths")
    count = manifest.get("totalPartitions")
    require(isinstance(count, int) and count > 0, "source-partition-count-invalid")
    rows = manifest.get("added")
    require(isinstance(rows, list) and rows, "source-added-invalid")
    path_hashes = manifest.get("pathToHash")
    require(isinstance(path_hashes, dict), "source-path-hashes-invalid")

    seen: set[str] = set()
    positions = [0] * count
    streams = []
    try:
        for index in range(count):
            part = source_part(source, index)
            require(part.is_file(), f"source-part-missing:{index}")
            streams.append(part.open("rb"))
        for row in rows:
            path = row.get("path")
            part_index = row.get("partIndex")
            offset = row.get("byteOffset")
            length = row.get("length")
            encoded = row.get("sha256HashBase64Encoded")
            require(isinstance(path, str) and valid_bundle_path(path), f"source-path-invalid:{path}")
            require(path not in seen, f"source-path-duplicate:{path}")
            require(isinstance(part_index, int) and 0 <= part_index < count, f"source-part-invalid:{path}")
            require(offset == positions[part_index], f"source-span-gap-or-overlap:{path}")
            require(isinstance(length, int) and length >= 0, f"source-length-invalid:{path}")
            require(path_hashes.get(path) == encoded, f"source-path-hash-map-drift:{path}")
            entry = hashlib.sha256()
            remaining = length
            while remaining:
                chunk = streams[part_index].read(min(CHUNK_SIZE, remaining))
                require(bool(chunk), f"source-span-short:{path}")
                entry.update(chunk)
                remaining -= len(chunk)
            actual = base64.b64encode(entry.digest()).decode("ascii")
            require(actual == encoded, f"source-span-hash-mismatch:{path}")
            positions[part_index] += length
            seen.add(path)
        for index, stream in enumerate(streams):
            require(positions[index] == source_part(source, index).stat().st_size, f"source-part-tail:{index}")
    finally:
        for stream in streams:
            stream.close()


def overlay_files(root: Path) -> dict[str, Path]:
    require(root.is_dir(), "overlay-directory-missing")
    result: dict[str, Path] = {}
    for file in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = file.relative_to(root).as_posix()
        require(valid_bundle_path(relative), f"overlay-path-invalid:{relative}")
        result[relative] = file
    require(bool(result), "overlay-is-empty")
    return result


def validate_catalog(source: Path, rows: dict[str, dict], overlay: dict[str, Path]) -> None:
    def data(path: str) -> bytes:
        if path in overlay:
            return overlay[path].read_bytes()
        require(path in rows, f"catalog-file-missing:{path}")
        return read_span(source, rows[path])

    try:
        songlist = json.loads(data("songs/songlist").decode("utf-8-sig"))
        packlist = json.loads(data("songs/packlist").decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("catalog-json-invalid") from exc
    songs = songlist.get("songs")
    packs = packlist.get("packs")
    require(isinstance(songs, list) and isinstance(packs, list), "catalog-shape-invalid")
    song_ids = [row.get("id") for row in songs if isinstance(row, dict)]
    pack_ids = [row.get("id") for row in packs if isinstance(row, dict)]
    require(len(song_ids) == len(songs) and all(isinstance(x, str) and x for x in song_ids), "song-id-invalid")
    require(len(pack_ids) == len(packs) and all(isinstance(x, str) and x for x in pack_ids), "pack-id-invalid")
    require(len(song_ids) == len(set(song_ids)), "song-id-duplicate")
    require(len(pack_ids) == len(set(pack_ids)), "pack-id-duplicate")
    known_packs = set(pack_ids)
    for song in songs:
        pack = song.get("set")
        require(pack == "single" or pack in known_packs, f"song-pack-missing:{song['id']}:{pack}")
    for pack in packs:
        parent = pack.get("pack_parent")
        require(not parent or parent in known_packs, f"pack-parent-missing:{pack['id']}:{parent}")


def copy_payload(source: Path, row: dict, replacement: Path | None, output, *digests) -> int:
    if replacement is not None:
        stream = replacement.open("rb")
        size = replacement.stat().st_size
    else:
        stream = source_part(source, row["partIndex"]).open("rb")
        stream.seek(row["byteOffset"])
        size = row["length"]
    remaining = size
    try:
        while remaining:
            chunk = stream.read(min(CHUNK_SIZE, remaining))
            require(bool(chunk), f"payload-short:{row['path']}")
            output.write(chunk)
            for digest in digests:
                if digest is not None:
                    digest.update(chunk)
            remaining -= len(chunk)
    finally:
        stream.close()
    return size


def verify_output(root: Path, alias: str, manifest: dict) -> dict:
    positions = [0] * manifest["totalPartitions"]
    for row in manifest["added"]:
        index = row["partIndex"]
        require(row["byteOffset"] == positions[index], f"output-span-gap-or-overlap:{row['path']}")
        part = root / f"{alias}_{index}.cb"
        with part.open("rb") as stream:
            stream.seek(row["byteOffset"])
            remaining = row["length"]
            digest = hashlib.sha256()
            while remaining:
                chunk = stream.read(min(CHUNK_SIZE, remaining))
                require(bool(chunk), f"output-span-short:{row['path']}")
                digest.update(chunk)
                remaining -= len(chunk)
        encoded = base64.b64encode(digest.digest()).decode("ascii")
        require(encoded == row["sha256HashBase64Encoded"], f"output-span-hash:{row['path']}")
        require(manifest["pathToHash"].get(row["path"]) == encoded, f"output-path-hash:{row['path']}")
        positions[index] += row["length"]
    parts = []
    for index, size in enumerate(positions):
        path = root / f"{alias}_{index}.cb"
        require(path.stat().st_size == size, f"output-part-size:{index}")
        parts.append({"file": path.name, "bytes": size, "sha256": sha256_file(path)})
    return {"entries": len(manifest["added"]), "parts": parts}


def build(args: argparse.Namespace) -> dict:
    source = args.source.resolve()
    output = args.output.resolve()
    require(source.is_dir(), "source-directory-missing")
    require(not output.exists(), "output-already-exists")
    require(args.alias and "/" not in args.alias and "\\" not in args.alias, "alias-invalid")
    require(args.version.startswith("7.0.255."), "bundle-version-must-be-7.0.255.x")
    manifest_path = source / "manifest.json"
    require(manifest_path.is_file(), "source-manifest-missing")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_source(source, source_manifest)
    overlays = overlay_files(args.overlay.resolve())
    source_rows = {row["path"]: row for row in source_manifest["added"]}
    validate_catalog(source, source_rows, overlays)
    detail_paths = set(source_manifest.get("pathToDetails", {}))
    changed_details = detail_paths & set(overlays)
    detail_key = None
    if changed_details:
        require(args.detail_key_file is not None and args.detail_key_file.is_file(), "detail-key-required")
        detail_key = args.detail_key_file.read_bytes()
        require(bool(detail_key), "detail-key-empty")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        rows: list[dict] = []
        path_hashes: dict[str, str] = {}
        path_details = dict(source_manifest.get("pathToDetails", {}))
        part_hashes = [hashlib.sha256() for _ in range(source_manifest["totalPartitions"])]
        positions = [0] * source_manifest["totalPartitions"]
        streams = [(temp / f"{args.alias}_{index}.cb").open("xb") for index in range(len(positions))]
        try:
            ordered = list(source_manifest["added"])
            for path, file in overlays.items():
                if path not in source_rows:
                    ordered.append({"path": path, "partIndex": len(positions) - 1, "byteOffset": 0, "length": file.stat().st_size})
            for source_row in ordered:
                path = source_row["path"]
                index = source_row["partIndex"]
                replacement = overlays.get(path)
                entry_hash = hashlib.sha256()
                detail_hash = hmac.new(detail_key, digestmod=hashlib.sha256) if path in changed_details else None
                start = positions[index]
                size = copy_payload(source, source_row, replacement, streams[index], part_hashes[index], entry_hash, detail_hash)
                positions[index] += size
                require(positions[index] <= args.max_part_bytes, f"part-size-limit:{index}")
                encoded = base64.b64encode(entry_hash.digest()).decode("ascii")
                rows.append({
                    "path": path,
                    "byteOffset": start,
                    "length": size,
                    "partIndex": index,
                    "sha256HashBase64Encoded": encoded,
                })
                path_hashes[path] = encoded
                if detail_hash is not None:
                    path_details[path] = base64.b64encode(detail_hash.digest()).decode("ascii")
        finally:
            for stream in streams:
                stream.close()

        manifest = dict(source_manifest)
        manifest.update({
            "added": rows,
            "applicationVersionNumber": APP_VERSION,
            "generatedUnixTimestamp": int(time.time()),
            "pathToDetails": path_details,
            "pathToHash": path_hashes,
            "previousVersionNumber": None,
            "removed": [],
            "totalPartitions": source_manifest["totalPartitions"],
            "uuid": secrets.token_hex(4),
            "versionNumber": args.version,
        })
        target_manifest = temp / f"{args.alias}.json"
        target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        verification = verify_output(temp, args.alias, manifest)
        report = {
            "status": "PASS",
            "application_version": APP_VERSION,
            "bundle_version": args.version,
            "alias": args.alias,
            "source_manifest_sha256": sha256_file(manifest_path),
            "manifest": {"file": target_manifest.name, "sha256": sha256_file(target_manifest)},
            "partition_count_preserved": True,
            "overlay_files": sorted(overlays),
            **verification,
        }
        report_path = temp / "build-report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        ready = {
            "status": "ready",
            "artifact_verified": True,
            "manifest": report["manifest"],
            "report_sha256": sha256_file(report_path),
        }
        (temp / "ready-manifest.json").write_text(json.dumps(ready, indent=2) + "\n", encoding="utf-8")
        temp.rename(output)
        return report
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="directory with manifest.json and source_N.cb")
    parser.add_argument("--overlay", type=Path, required=True, help="replacement/addition tree using bundle-relative paths")
    parser.add_argument("--output", type=Path, required=True, help="new output directory; must not exist")
    parser.add_argument("--alias", required=True, help="immutable filename prefix for manifest and parts")
    parser.add_argument("--version", required=True, help="new 7.0.255.x content version")
    parser.add_argument("--detail-key-file", type=Path, help="private raw HMAC key; required when a detail path changes")
    parser.add_argument("--max-part-bytes", type=int, default=DEFAULT_MAX_PART_BYTES)
    args = parser.parse_args()
    require(args.max_part_bytes > 0, "max-part-bytes-invalid")
    return args


def main() -> int:
    try:
        report = build(parse_args())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps({"status": "PASS", "alias": report["alias"], "parts": len(report["parts"]), "entries": report["entries"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
