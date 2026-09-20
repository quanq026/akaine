"""Build an unsigned APK from a verified source and private replacement plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


SCHEMA = "akaine.client-build.v1"
COPY_BUFFER = 4 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BUFFER), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(COPY_BUFFER), b""):
        digest.update(block)
    return digest.hexdigest()


def archive_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or ".." in path.parts:
        raise ValueError(f"unsafe archive path: {value!r}")
    return path.as_posix()


def private_file(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe private-kit path: {value!r}")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"private-kit path escapes root: {value!r}")
    return path


def is_v1_signature(name: str) -> bool:
    upper = name.upper()
    if not upper.startswith("META-INF/"):
        return False
    leaf = upper.rsplit("/", 1)[-1]
    return leaf == "MANIFEST.MF" or leaf.endswith((".SF", ".RSA", ".DSA", ".EC"))


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != SCHEMA:
        raise ValueError(f"plan schema must be {SCHEMA!r}")
    expected = plan.get("source_sha256")
    source_entries = plan.get("source_entries", {})
    if expected is not None and (
        len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected.lower())
    ):
        raise ValueError("source_sha256 must contain 64 hexadecimal characters")
    if not expected and not source_entries:
        raise ValueError("plan requires source_sha256 or source_entries")
    if not isinstance(source_entries, dict):
        raise ValueError("source_entries must be an object")
    for name, value in source_entries.items():
        archive_path(name)
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
            raise ValueError(f"invalid source entry SHA-256: {name}")
    replacements = plan.get("replacements", [])
    binary_patches = plan.get("binary_patches", [])
    if not isinstance(replacements, list) or not isinstance(binary_patches, list):
        raise ValueError("replacements and binary_patches must be arrays")
    if not replacements and not binary_patches:
        raise ValueError("plan requires a replacement or binary patch")
    return plan


def patch_binary(source_zip: zipfile.ZipFile, row: dict) -> tuple[str, bytes, list[str]]:
    target = archive_path(row["archive_path"])
    try:
        data = bytearray(source_zip.read(target))
    except KeyError as error:
        raise ValueError(f"source APK is missing binary patch target: {target}") from error
    actual_source_hash = hashlib.sha256(data).hexdigest()
    expected_source_hash = row["source_sha256"].lower()
    if actual_source_hash != expected_source_hash:
        raise ValueError(
            f"binary patch source hash mismatch for {target}: "
            f"expected {expected_source_hash}, got {actual_source_hash}"
        )
    occupied: set[int] = set()
    labels: list[str] = []
    for operation in row.get("operations", []):
        offset = operation["offset"]
        before = bytes.fromhex(operation["before"])
        after = bytes.fromhex(operation["after"])
        if not isinstance(offset, int) or offset < 0 or len(before) != len(after):
            raise ValueError(f"invalid binary patch operation for {target}")
        end = offset + len(before)
        positions = set(range(offset, end))
        if end > len(data) or occupied.intersection(positions):
            raise ValueError(f"out-of-range or overlapping binary patch for {target}")
        if data[offset:end] != before:
            raise ValueError(
                f"binary patch guard mismatch for {target} at offset {offset:#x}"
            )
        data[offset:end] = after
        occupied.update(positions)
        labels.append(operation.get("label", f"{offset:#x}"))
    actual_output_hash = hashlib.sha256(data).hexdigest()
    expected_output_hash = row["output_sha256"].lower()
    if actual_output_hash != expected_output_hash:
        raise ValueError(
            f"binary patch output hash mismatch for {target}: "
            f"expected {expected_output_hash}, got {actual_output_hash}"
        )
    return target, bytes(data), labels


def build(source: Path, plan_path: Path, kit_root: Path, output: Path) -> dict:
    source = source.resolve()
    plan_path = plan_path.resolve()
    kit_root = kit_root.resolve()
    output = output.resolve()
    if not source.is_file() or not plan_path.is_file() or not kit_root.is_dir():
        raise FileNotFoundError("source APK, plan, or private-kit root is missing")
    if output == source:
        raise ValueError("output must not overwrite the source APK")

    plan = load_plan(plan_path)
    actual_source_hash = sha256_file(source)
    expected_source_hash = plan.get("source_sha256")
    if expected_source_hash and actual_source_hash != expected_source_hash.lower():
        raise ValueError(
            "source APK hash mismatch: "
            f"expected {expected_source_hash.lower()}, got {actual_source_hash}"
        )

    replacements: dict[str, tuple[Path, str]] = {}
    for row in plan.get("replacements", []):
        target = archive_path(row["archive_path"])
        payload = private_file(kit_root, row["file"])
        expected = row["sha256"].lower()
        if target in replacements:
            raise ValueError(f"duplicate replacement target: {target}")
        if not payload.is_file() or sha256_file(payload) != expected:
            raise ValueError(f"replacement missing or hash mismatch: {row['file']}")
        replacements[target] = (payload, expected)

    binary_patch_rows = plan.get("binary_patches", [])
    binary_patch_targets = [archive_path(row["archive_path"]) for row in binary_patch_rows]
    if len(set(binary_patch_targets)) != len(binary_patch_targets):
        raise ValueError("duplicate binary patch target")
    if set(binary_patch_targets).intersection(replacements):
        raise ValueError("an entry cannot be both replaced and binary-patched")

    required = {archive_path(value) for value in plan.get("required_entries", [])}
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=output.name + ".", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    written: set[str] = set()
    removed_signatures: list[str] = []

    try:
        with zipfile.ZipFile(source, "r") as source_zip, zipfile.ZipFile(
            temporary, "w", allowZip64=True
        ) as output_zip:
            source_name_list = source_zip.namelist()
            source_names = set(source_name_list)
            if len(source_names) != len(source_name_list):
                raise ValueError("source APK contains duplicate archive paths")
            missing = sorted(required - source_names)
            if missing:
                raise ValueError(f"source APK is missing required entries: {missing}")
            for name, expected in plan.get("source_entries", {}).items():
                if name not in source_names:
                    raise ValueError(f"source APK is missing guarded entry: {name}")
                with source_zip.open(name, "r") as stream:
                    actual = sha256_stream(stream)
                if actual != expected.lower():
                    raise ValueError(
                        f"source entry hash mismatch for {name}: "
                        f"expected {expected.lower()}, got {actual}"
                    )
            binary_payloads: dict[str, tuple[bytes, list[str]]] = {}
            for row in binary_patch_rows:
                target, payload, labels = patch_binary(source_zip, row)
                binary_payloads[target] = (payload, labels)

            for info in source_zip.infolist():
                name = archive_path(info.filename)
                if info.is_dir():
                    output_zip.writestr(info, b"")
                    continue
                if is_v1_signature(name):
                    removed_signatures.append(name)
                    continue
                if name in replacements:
                    payload, _ = replacements[name]
                    with payload.open("rb") as source_stream, output_zip.open(info, "w") as target_stream:
                        shutil.copyfileobj(source_stream, target_stream, COPY_BUFFER)
                    written.add(name)
                    continue
                if name in binary_payloads:
                    payload, _ = binary_payloads[name]
                    output_zip.writestr(info, payload)
                    written.add(name)
                    continue
                with source_zip.open(info, "r") as source_stream, output_zip.open(info, "w") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, COPY_BUFFER)

            for name, (payload, _) in replacements.items():
                if name in written:
                    continue
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                with payload.open("rb") as source_stream, output_zip.open(info, "w") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, COPY_BUFFER)
                written.add(name)

        declared_targets = set(replacements) | set(binary_patch_targets)
        if written != declared_targets:
            raise RuntimeError("not every declared patch target was written")
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    receipt = {
        "schema": SCHEMA,
        "status": "unsigned-built",
        "source_sha256": actual_source_hash,
        "plan_sha256": sha256_file(plan_path),
        "output": output.name,
        "output_sha256": sha256_file(output),
        "output_bytes": output.stat().st_size,
        "replaced_entries": sorted(written),
        "binary_patch_labels": {
            name: labels for name, (_, labels) in sorted(binary_payloads.items())
        },
        "removed_v1_signatures": sorted(removed_signatures),
        "expected": plan.get("expected", {}),
    }
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--kit-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build(args.source, args.plan, args.kit_root, args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
