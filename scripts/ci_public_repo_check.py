"""Fail public CI if a tracked checkout contains obvious private material."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 95 * 1024 * 1024
FORBIDDEN_SUFFIXES = {".apk", ".apks", ".xapk", ".cb", ".aff", ".ogg", ".wav", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".db", ".sqlite", ".sqlite3"}
PRIVATE_KEY = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
AWS_ACCESS_KEY = re.compile(rb"AKIA[0-9A-Z]{16}")
R2_ACCESS_KEY = re.compile(
    rb"(?i)(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)\s*=\s*['\"][0-9a-f]{32,64}['\"]"
)
SENSITIVE_NAME = re.compile(r"(?i)(?:secret|token|password|access_key|api_key)")
PLACEHOLDERS = ("<set_", "your_", "example", "test-only")


def hardcoded_python_secret(path: Path, data: bytes) -> bool:
    if path.suffix.lower() != ".py":
        return False
    try:
        tree = ast.parse(data.decode("utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        lowered = value.value.lower()
        if (
            len(value.value) >= 8
            and any(SENSITIVE_NAME.search(name) for name in names)
            and not any(marker in lowered for marker in PLACEHOLDERS)
        ):
            return True
    return False


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [ROOT / raw.decode("utf-8") for raw in result.stdout.split(b"\0") if raw]


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        lowered = relative.as_posix().lower()
        if (
            path.name == "config.py"
            or (path.name.startswith(".env") and path.name != ".env.example")
            or "/backups/" in lowered
            or re.search(r"^scripts/.*_20[0-9]{6,}", lowered)
        ):
            failures.append(f"private-path:{relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden-artifact:{relative}")
            continue
        if path.stat().st_size > MAX_BYTES:
            failures.append(f"oversized-file:{relative}")
            continue
        data = path.read_bytes()
        if (
            PRIVATE_KEY.search(data)
            or AWS_ACCESS_KEY.search(data)
            or R2_ACCESS_KEY.search(data)
            or hardcoded_python_secret(path, data)
        ):
            failures.append(f"secret-pattern:{relative}")
    if failures:
        print("Public repository check failed:", *failures, sep="\n", file=sys.stderr)
        return 1
    print(f"Public repository check passed for {len(tracked_files())} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
