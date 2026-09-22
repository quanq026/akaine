"""Build a pinned, symbol-prefixed static BoringSSL archive for AKFC."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


REVISION = "b75f405cde1cc3c9fb811be155eecabe38f379bb"
REPOSITORY = "https://github.com/google/boringssl.git"


def run(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(
        command, cwd=cwd, check=True, text=True, capture_output=True
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ndk = Path(os.environ["ANDROID_NDK_ROOT"]).resolve()
    host_bin = ndk / "toolchains/llvm/prebuilt/windows-x86_64/bin"
    objcopy = host_bin / "llvm-objcopy.exe"
    nm = host_bin / "llvm-nm.exe"
    toolchain = ndk / "build/cmake/android.toolchain.cmake"
    for path in (objcopy, nm, toolchain):
        if not path.is_file():
            raise FileNotFoundError(path)

    work = args.work.resolve()
    source = work / "boringssl"
    build = work / "build-android-arm64-static"
    if not source.exists():
        work.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", REPOSITORY, str(source)])
        run(["git", "checkout", REVISION], source)
    if run(["git", "rev-parse", "HEAD"], source).strip() != REVISION:
        raise RuntimeError("BoringSSL checkout is not at the pinned revision")

    ninja = shutil.which("ninja")
    if not ninja:
        candidates = sorted(ndk.parents[1].glob("cmake/*/bin/ninja.exe"), reverse=True)
        if not candidates:
            raise FileNotFoundError("ninja.exe; install CMake from Android SDK Tools")
        ninja = str(candidates[0])
    run([
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}", f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
        "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-24",
        "-DBUILD_SHARED_LIBS=OFF", "-DCMAKE_BUILD_TYPE=Release",
    ])
    run(["cmake", "--build", str(build), "--target", "crypto", "-j", "8"])
    built = build / "crypto/libcrypto.a"
    if not built.is_file():
        built = build / "libcrypto.a"
    if not built.is_file():
        raise FileNotFoundError("BoringSSL static libcrypto.a")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    symbols = {
        line.rsplit(maxsplit=1)[-1]
        for line in run([str(nm), "--defined-only", "--extern-only", str(built)]).splitlines()
        if line.strip() and not line.rstrip().endswith(":")
    }
    mapping = work / "akfc-symbol-map.txt"
    mapping.write_text(
        "".join(f"{name} akfc_{name}\n" for name in sorted(symbols)), encoding="utf-8"
    )
    run([str(objcopy), f"--redefine-syms={mapping}", str(built), str(args.output)])
    print(f"Built symbol-prefixed AKFC crypto archive: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
