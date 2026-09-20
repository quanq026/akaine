"""Generate an obfuscated C header from an operator-owned RSA private key."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate(private_key_path: Path, output: Path) -> None:
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size != 3072:
        raise ValueError("AKFC requires a 3072-bit RSA private key")
    der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    mask = os.urandom(32)
    encoded = bytes(
        value ^ mask[index % len(mask)] ^ ((index * 0x37 + 0x5A) & 0xFF)
        for index, value in enumerate(der)
    )

    def array(name: str, data: bytes) -> str:
        rows = [data[index:index + 12] for index in range(0, len(data), 12)]
        body = "\n".join(
            "    " + ", ".join(f"0x{value:02x}" for value in row) + ","
            for row in rows
        )
        return f"static const unsigned char {name}[] = {{\n{body}\n}};"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "#pragma once\n"
        f"#define EMBEDDED_KEY_SIZE {len(der)}\n"
        + array("EMBEDDED_KEY_DATA", encoded)
        + "\n"
        + array("EMBEDDED_KEY_XOR", mask)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.private_key, args.output)
    print(f"Generated header: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
