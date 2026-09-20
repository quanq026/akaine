"""Read-only workstation readiness check for Akaine contributors."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def version(command: str, *arguments: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    result = subprocess.run(
        [executable, *arguments], capture_output=True, text=True, timeout=15
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if result.returncode == 0 and output else "available"


def sdk_tool(name: str) -> str | None:
    direct = version(name, "version" if name == "apksigner" else "-h")
    if direct:
        return direct
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk:
        return None
    build_tools = Path(sdk) / "build-tools"
    candidates = sorted(
        build_tools.glob(f"*/{name}*"), reverse=True
    ) if build_tools.is_dir() else []
    return str(candidates[0]) if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="require only public CI tools")
    parser.add_argument(
        "--android",
        action="store_true",
        help="require the Android build and APK patch toolchain",
    )
    args = parser.parse_args()
    checks = {
        "git": version("git", "--version"),
        "python": sys.version.split()[0],
        "node": version("node", "--version"),
        "npm": version("npm", "--version"),
        "java": version("java", "-version"),
        "adb": version("adb", "version"),
        "zipalign": sdk_tool("zipalign"),
        "apksigner": sdk_tool("apksigner"),
    }
    apktool_jar = os.environ.get("APKTOOL_JAR")
    checks["apktool"] = (
        str(Path(apktool_jar).resolve())
        if apktool_jar and Path(apktool_jar).is_file()
        else version("apktool", "--version")
    )
    for name, value in checks.items():
        print(f"{'OK' if value else 'MISSING':7} {name:10} {value or ''}")
    required = ["git", "python"]
    if args.android:
        required.extend(("java", "adb", "zipalign", "apksigner", "apktool"))
    missing = [name for name in required if not checks[name]]
    if missing:
        print("Required tools missing: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("Requested toolchain is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
