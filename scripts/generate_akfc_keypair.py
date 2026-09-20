"""Generate an operator-owned AKFC RSA key pair."""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    if args.private_key.exists() or args.public_key.exists():
        raise FileExistsError("refusing to overwrite an existing AKFC key")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    args.private_key.parent.mkdir(parents=True, exist_ok=True)
    args.public_key.parent.mkdir(parents=True, exist_ok=True)
    args.private_key.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    args.public_key.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    print("Generated AKFC key pair. Keep the private key offline and out of Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
