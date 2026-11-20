"""Verify Arcaea 7.3.1 input and provide guarded Android packaging helpers."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import stat
import subprocess
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


def is_signature_metadata(name: str) -> bool:
    # APKPure's source-stamp certificate no longer describes an operator-signed APK.
    return name == 'stamp-cert-sha256' or is_v1_signature(name)


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
                if is_signature_metadata(name):
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
        "removed_signature_metadata": sorted(removed_signatures),
        "expected": plan.get("expected", {}),
    }
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt



EDITOR = (7733037, 'a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67')
XAPK_73 = (1282543787, 'b996a23570e927f907a096da950f4347c818a388fc610a84fd0b8f58a7faa91e')
MERGED_73 = (1270354570, 'c622e705c5818d5773b61ca57bd3ea712e49668e984d38f6ae49003978f6908b')
MODULES_73 = {
    'moe.low.arc.apk': 'base',
    'config.arm64_v8a.apk': 'config.arm64_v8a',
    'config.en.apk': 'config.en',
    'config.xxxhdpi.apk': 'config.xxxhdpi',
    'arcassets.apk': 'arcassets',
}


def checked_path(value, *, fresh=False):
    path = Path(value)
    if '..' in path.parts:
        raise ValueError('Input/output path traversal is not allowed')
    path = path.absolute()
    for current in (path, *path.parents):
        if current.is_symlink() or current.exists() and getattr(current.stat(), 'st_file_attributes', 0) & 1024:
            raise ValueError('Input/output symlinks and junctions are not allowed')
    if fresh:
        if path.exists():
            raise ValueError('Input preparation requires a fresh output directory')
    elif not path.is_file():
        raise ValueError('A regular input/tool file is required')
    return path


def prepare_input(source, java, apkeditor, outputdir):
    """Verify and merge the original Arcaea 7.3.1 ARM64 input."""
    xapk, merged, modules = XAPK_73, MERGED_73, MODULES_73
    app_version, version_code = '7.3.1', '1210500'
    metadata = {'manifest.json'}
    source = checked_path(source)
    outputdir = checked_path(outputdir, fresh=True)
    size = source.stat().st_size
    if size not in (xapk[0], merged[0]):
        raise ValueError(f'Use the verified APKPure {app_version} arm64 XAPK or its verified merged APK; a base/split APK alone is incomplete')
    source_hash = sha256_file(source)
    kind = 'xapk' if (size, source_hash) == xapk else 'merged' if (size, source_hash) == merged else None
    if kind is None:
        raise ValueError(f'Input does not match the verified APKPure {app_version} arm64 input')
    if kind == 'xapk':
        java, apkeditor = checked_path(java), checked_path(apkeditor)
        if (apkeditor.stat().st_size, sha256_file(apkeditor)) != EDITOR:
            raise ValueError('APKEditor must match the verified 1.4.9 release')
        with zipfile.ZipFile(source) as archive:
            rows = archive.infolist()
            names = [row.filename for row in rows]
            if len(set(names)) != len(names) or set(names) != set(modules) | metadata:
                raise ValueError('XAPK must contain exactly the verified APK modules and metadata')
            for row in rows:
                path = PurePosixPath(row.filename)
                if (path.is_absolute() or path.as_posix() != row.filename or '..' in path.parts
                        or '\\' in row.filename or ':' in row.filename or row.is_dir()
                        or stat.S_ISLNK(row.external_attr >> 16) or row.flag_bits & 1):
                    raise ValueError('Unsafe XAPK entry')
            manifest_row = archive.getinfo('manifest.json')
            if manifest_row.file_size > 65536:
                raise ValueError('XAPK manifest is too large')
            manifest = json.loads(archive.read(manifest_row))
            if (manifest.get('package_name') != 'moe.low.arc' or manifest.get('version_name') != app_version
                    or str(manifest.get('version_code')) != version_code
                    or manifest.get('split_apks') != [{'file': name, 'id': value} for name, value in modules.items()]
                    or manifest.get('split_configs') != list(modules.values())[1:]):
                raise ValueError('XAPK package/version/split identity differs')
    outputdir.mkdir(parents=True)
    target = outputdir / 'merged.apk'
    if kind == 'merged':
        shutil.copy2(source, target)
    else:
        try:
            result = subprocess.run([str(java), '-Xmx4g', '-jar', str(apkeditor), 'merge',
                                     '-i', str(source), '-o', str(target)], capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('APKPure merge failed or timed out; private tool diagnostics suppressed') from None
        if result.returncode:
            raise RuntimeError('APKPure merge failed; private tool diagnostics suppressed')
        if (apkeditor.stat().st_size, sha256_file(apkeditor)) != EDITOR:
            raise ValueError('APKEditor changed during input preparation')
    target = checked_path(target)
    if (target.stat().st_size, sha256_file(target)) != merged:
        raise ValueError('Merged APK does not match the verified reference; stop before patching')
    if (source.stat().st_size, sha256_file(source)) != (size, source_hash):
        raise ValueError('Source input changed during preparation')
    return target

def verify_unchanged_members(base, output, replacements):
    with zipfile.ZipFile(base) as before, zipfile.ZipFile(output) as after:
        old = {row.filename for row in before.infolist() if not row.is_dir()
               and not is_signature_metadata(row.filename)}
        new = {row.filename for row in after.infolist() if not row.is_dir()}
        if new != old | set(replacements):
            raise ValueError("APK member set changed outside the declared payloads")
        for name in old - set(replacements):
            with before.open(name) as left, after.open(name) as right:
                if sha256_stream(left) != sha256_stream(right):
                    raise ValueError("Undeclared APK member changed")


ROOT = Path(__file__).resolve().parents[1]


def verify_sources(hashes):
    for path, expected in hashes.items():
        if sha256_file(ROOT / path) != expected:
            raise ValueError('Source changed during build; do not install or publish the output')


def sign_apk(output, build_tools, keystore, key_alias, java):
    """Align and sign with the operator's key; passwords travel through stdin only."""
    keystore = checked_path(keystore)
    try:
        keystore.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError('Signing key must remain outside the repository')
    align = Path(build_tools) / 'zipalign.exe'
    signer = Path(build_tools) / 'lib/apksigner.jar'
    if not align.is_file() or not signer.is_file():
        raise ValueError('Android Build-Tools with zipalign and apksigner are required')
    aligned, signed = output / 'aligned.apk', output / 'Akaine-7.3.1.apk'
    run_tool([align, '-P', '16', '-f', '4', output / 'unsigned.apk', aligned])
    run_tool([align, '-c', '-P', '16', '4', aligned])
    store_password = getpass.getpass('Keystore password: ')
    key_password = getpass.getpass('Key password (Enter to reuse keystore password): ') or store_password
    try:
        result = subprocess.run([str(java), '-Dfile.encoding=UTF-8', '-jar', str(signer), 'sign', '--ks', str(keystore), '--ks-key-alias', key_alias,
            '--ks-pass', 'stdin', '--key-pass', 'stdin', '--v1-signing-enabled', 'false',
            '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true', '--v4-signing-enabled', 'false', '--out', str(signed), str(aligned)],
            input=(store_password + '\n' + key_password + '\n').encode(), capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError('APK signing failed; check the keystore, alias and passwords')
    finally:
        store_password = key_password = ''
    run_tool([java, '-Dfile.encoding=UTF-8', '-jar', signer, 'verify', '--verbose', signed])
    verify_unchanged_members(output / 'unsigned.apk', signed, {})
    return signed


def load_patch_module(name, path):
    spec = importlib.util.spec_from_file_location('akaine_' + name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Current versioned patch helper is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_tool(arguments):
    try:
        result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Android tool failed or timed out; diagnostics suppressed') from None
    if result.returncode:
        raise RuntimeError('Android tool failed: ' + Path(arguments[0]).name)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description='Verify and merge the original Arcaea 7.3.1 ARM64 XAPK.')
    parser.add_argument('--source', type=Path, required=True, help='Original ARM64 XAPK or its verified merge')
    parser.add_argument('--java', type=Path, required=True, help='Java executable')
    parser.add_argument('--apkeditor', type=Path, required=True, help='APKEditor 1.4.9 JAR')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository')
    args = parser.parse_args()
    try:
        if args.output.resolve().is_relative_to(ROOT):
            raise ValueError('Output must remain outside the repository')
        apk = prepare_input(args.source, args.java, args.apkeditor, args.output)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f'{error}\n')
    print(f'Verified original APK: {apk}')


if __name__ == '__main__':
    main()
