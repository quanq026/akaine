"""Build the arm64 AKFC loader with the configured Android NDK."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

def build(source: Path, key_header: Path, crypto: Path, output: Path, compiler: Path) -> None:
    for path in (compiler, crypto, source):
        if not path.is_file():
            raise RuntimeError("Loader build input is unavailable")
    if key_header.name != "embedded_key.h" or not key_header.is_file() or key_header.is_symlink():
        raise ValueError("Existing opaque embedded_key.h is required")
    if output.exists():
        raise ValueError("Loader output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler), "-Wl,--no-undefined", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
        "-Wno-unused-variable", "-Wno-unused-parameter", "-Wno-sign-compare",
        "-std=c++17", "-O2", "-shared", "-fPIC", "-fvisibility=hidden",
        "-fvisibility-inlines-hidden", "-static-libstdc++", "-Wl,--strip-all",
        f"-I{key_header.parent}", "-MD", "-MF", str(output.with_suffix('.d')),
        str(crypto), str(source), "-llog", "-ldl", "-o", str(output),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Loader compiler failed; private diagnostics suppressed") from None
    if result.returncode:
        # Compiler diagnostics can quote a private include line; never print or persist them.
        raise RuntimeError("Loader compiler failed; private diagnostics suppressed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--key-header", type=Path, required=True)
    parser.add_argument("--crypto", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ndk_root = os.environ.get("ANDROID_NDK_ROOT")
    if not ndk_root:
        raise RuntimeError("ANDROID_NDK_ROOT is required")
    toolchain = Path(ndk_root) / "toolchains" / "llvm" / "prebuilt" / "windows-x86_64" / "bin"
    compiler = toolchain / "aarch64-linux-android24-clang++.cmd"
    build(args.source, args.key_header, args.crypto, args.output, compiler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
