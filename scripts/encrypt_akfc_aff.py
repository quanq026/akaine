"""Encrypt one AFF as an AKFC container for the 7.0.255 client."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from core.akfc import (  # noqa: E402
    AffIdentity,
    assemble_container,
    decrypt_container,
    encrypt_aff,
    key_id_from_public_key,
    public_key_spki_der,
    wrap_dek,
)


RELEASE_ID = "fan-sec-v1"
SONG_ID = re.compile(r"^[a-z0-9_]+$")
AFF_NAME = re.compile(r"^[0-4]\.aff$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_public_key(path: Path) -> rsa.RSAPublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 3072:
        raise ValueError("AKFC public key must be RSA-3072")
    return key


def build(
    source: Path,
    public_key_path: Path,
    song_id: str,
    file_name: str,
    output: Path,
    receipt: Path | None,
    key_epoch: int,
) -> dict:
    if not source.is_file():
        raise FileNotFoundError(source)
    if not public_key_path.is_file():
        raise FileNotFoundError(public_key_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if receipt and receipt.exists():
        raise FileExistsError(f"refusing to overwrite receipt: {receipt}")
    if receipt and receipt.resolve() == output.resolve():
        raise ValueError("receipt and output must use different paths")
    if not SONG_ID.fullmatch(song_id):
        raise ValueError("song ID must contain only lowercase ASCII letters, digits, and underscores")
    if not AFF_NAME.fullmatch(file_name):
        raise ValueError("file name must be one of 0.aff, 1.aff, 2.aff, 3.aff, or 4.aff")
    if not 0 <= key_epoch <= 0xFFFFFFFF:
        raise ValueError("key epoch is outside the uint32 range")

    plaintext = source.read_bytes()
    if b"AudioOffset:" not in plaintext or b"\n-" not in plaintext:
        raise ValueError("source does not look like an AFF file")
    public_key = load_public_key(public_key_path)
    identity = AffIdentity(RELEASE_ID, song_id, file_name, key_epoch)
    dek = os.urandom(32)
    encrypted = encrypt_aff(plaintext, dek, identity, nonce=os.urandom(12))
    container = assemble_container(encrypted, wrap_dek(public_key, dek))
    if decrypt_container(container, dek, identity) != plaintext:
        raise RuntimeError("AKFC in-memory verification failed")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(container)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    spki = public_key_spki_der(public_key)
    report = {
        "status": "verified",
        "identity": {
            "release_id": RELEASE_ID,
            "song_id": song_id,
            "file_name": file_name,
            "key_epoch": key_epoch,
        },
        "public_key_id": key_id_from_public_key(spki),
        "source": {
            "bytes": len(plaintext),
            "md5": hashlib.md5(plaintext).hexdigest(),  # DownloadList plaintext contract
            "sha256": sha256(plaintext),
        },
        "container": {
            "bytes": len(container),
            "sha256": sha256(container),
            "magic": container[:4].decode("ascii"),
        },
        "output": str(output.resolve()),
    }
    if receipt:
        try:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--song-id", required=True)
    parser.add_argument("--file-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--key-epoch", type=int, default=1)
    args = parser.parse_args()
    try:
        report = build(
            args.source,
            args.public_key,
            args.song_id,
            args.file_name,
            args.output,
            args.receipt,
            args.key_epoch,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
