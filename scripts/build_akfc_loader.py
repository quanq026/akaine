"""Build the arm64 AKFC loader with the configured Android NDK."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--key-header", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ndk_root = os.environ.get("ANDROID_NDK_ROOT")
    if not ndk_root:
        raise RuntimeError("ANDROID_NDK_ROOT is required")
    toolchain = Path(ndk_root) / "toolchains" / "llvm" / "prebuilt" / "windows-x86_64" / "bin"
    compiler = toolchain / "aarch64-linux-android24-clang++.cmd"
    if not compiler.is_file():
        raise FileNotFoundError(compiler)
    if args.key_header.name != "embedded_key.h":
        raise ValueError("key header must be named embedded_key.h")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler), "-std=c++17", "-O2", "-shared", "-fPIC",
        "-fvisibility=hidden", "-fvisibility-inlines-hidden", "-static-libstdc++",
        "-Wl,--strip-all", "-Wl,--exclude-libs,ALL",
        f"-I{args.key_header.parent}", str(args.source), "-llog", "-ldl",
        "-o", str(args.output),
    ]
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
