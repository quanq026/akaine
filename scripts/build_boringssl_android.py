"""Build a pinned arm64 Android libcrypto for the AKFC loader."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


REVISION = "b75f405cde1cc3c9fb811be155eecabe38f379bb"
REPOSITORY = "https://github.com/google/boringssl.git"
REQUIRED_SYMBOLS = (
    "EVP_sha256", "EVP_sha1", "EVP_aes_256_gcm", "EVP_CIPHER_CTX_new",
    "EVP_CIPHER_CTX_free", "EVP_DecryptInit_ex", "EVP_DecryptUpdate",
    "EVP_DecryptFinal_ex", "EVP_CIPHER_CTX_ctrl", "d2i_AutoPrivateKey",
    "EVP_PKEY_free", "EVP_PKEY_CTX_new", "EVP_PKEY_CTX_free",
    "EVP_PKEY_decrypt_init", "EVP_PKEY_decrypt",
    "EVP_PKEY_CTX_set_rsa_padding", "EVP_PKEY_CTX_set_rsa_oaep_md",
    "EVP_PKEY_CTX_set_rsa_mgf1_md", "EVP_aead_aes_256_gcm",
    "EVP_AEAD_CTX_new", "EVP_AEAD_CTX_free", "EVP_AEAD_CTX_open",
)


def run(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ndk_value = os.environ.get("ANDROID_NDK_ROOT")
    if not ndk_value:
        raise RuntimeError("ANDROID_NDK_ROOT is required")
    ndk = Path(ndk_value).resolve()
    host_bin = ndk / "toolchains" / "llvm" / "prebuilt" / "windows-x86_64" / "bin"
    strip = host_bin / "llvm-strip.exe"
    nm = host_bin / "llvm-nm.exe"
    toolchain = ndk / "build" / "cmake" / "android.toolchain.cmake"
    for path in (strip, nm, toolchain):
        if not path.is_file():
            raise FileNotFoundError(path)

    work = args.work.resolve()
    source = work / "boringssl"
    build = work / "build-android-arm64"
    if not source.exists():
        work.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", REPOSITORY, str(source)])
        run(["git", "checkout", REVISION], source)
    if run(["git", "rev-parse", "HEAD"], source).strip() != REVISION:
        raise RuntimeError("BoringSSL checkout is not at the pinned revision")

    ninja = shutil.which("ninja")
    if not ninja:
        sdk = ndk.parents[1]
        candidates = sorted(sdk.glob("cmake/*/bin/ninja.exe"), reverse=True)
        if not candidates:
            raise FileNotFoundError("ninja.exe; install CMake from Android SDK Tools")
        ninja = str(candidates[0])

    run([
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}", f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
        "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-24",
        "-DBUILD_SHARED_LIBS=ON", "-DCMAKE_BUILD_TYPE=Release",
    ])
    run(["cmake", "--build", str(build), "--target", "crypto", "-j", "8"])
    built = build / "libcrypto.so"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, args.output)
    run([str(strip), "--strip-all", str(args.output)])
    symbols = run([str(nm), "-D", "--defined-only", str(args.output)])
    missing = [name for name in REQUIRED_SYMBOLS if name not in symbols]
    if missing:
        args.output.unlink(missing_ok=True)
        raise RuntimeError(f"built libcrypto is missing symbols: {missing}")
    print(f"Built pinned arm64 libcrypto: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
