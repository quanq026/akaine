from __future__ import annotations

import base64
import hashlib
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"AKFC"
VERSION = 1
FLAGS = 0
NONCE_SIZE = 12
TAG_SIZE = 16
DEK_SIZE = 32
HASH_SIZE = 32
MAX_PLAINTEXT_SIZE = 32 * 1024 * 1024
MAX_WRAPPED_KEY_SIZE = 1024
HEADER = struct.Struct("<4sBBHIQHBB32s32s")


class AKFCError(ValueError):
    pass


@dataclass(frozen=True)
class AffIdentity:
    release_id: str
    song_id: str
    file_name: str
    key_epoch: int

    def __post_init__(self) -> None:
        for name, value in (
            ("release_id", self.release_id),
            ("song_id", self.song_id),
            ("file_name", self.file_name),
        ):
            if not value or "\n" in value or "\x00" in value:
                raise AKFCError(f"invalid {name}")
        if not self.file_name.endswith(".aff"):
            raise AKFCError("file_name must end with .aff")
        if not 0 <= self.key_epoch <= 0xFFFFFFFF:
            raise AKFCError("invalid key epoch")


@dataclass(frozen=True)
class EncryptedAff:
    identity: AffIdentity
    plaintext_size: int
    plaintext_sha256: bytes
    context_hash: bytes
    aad: bytes
    nonce: bytes
    ciphertext: bytes
    tag: bytes

    def __post_init__(self) -> None:
        if not 0 <= self.plaintext_size <= MAX_PLAINTEXT_SIZE:
            raise AKFCError("invalid plaintext size")
        if len(self.plaintext_sha256) != HASH_SIZE:
            raise AKFCError("invalid plaintext hash length")
        if len(self.context_hash) != HASH_SIZE:
            raise AKFCError("invalid context hash length")
        if len(self.nonce) != NONCE_SIZE:
            raise AKFCError("invalid nonce length")
        if len(self.tag) != TAG_SIZE:
            raise AKFCError("invalid tag length")
        if len(self.ciphertext) != self.plaintext_size:
            raise AKFCError("ciphertext size mismatch")
        if hashlib.sha256(self.aad).digest() != self.context_hash:
            raise AKFCError("context hash mismatch")


@dataclass(frozen=True)
class ParsedContainer:
    identity: AffIdentity
    plaintext_size: int
    plaintext_sha256: bytes
    context_hash: bytes
    wrapped_key: bytes
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    aad: bytes


def build_aad(
    identity: AffIdentity,
    plaintext_size: int,
    plaintext_sha256: bytes,
) -> bytes:
    if len(plaintext_sha256) != HASH_SIZE:
        raise AKFCError("invalid plaintext hash length")
    if not 0 <= plaintext_size <= MAX_PLAINTEXT_SIZE:
        raise AKFCError("invalid plaintext size")
    return "\n".join(
        (
            "AKFC1",
            identity.release_id,
            identity.song_id,
            identity.file_name,
            str(identity.key_epoch),
            str(plaintext_size),
            plaintext_sha256.hex(),
        )
    ).encode("utf-8")


def encrypt_aff(
    plaintext: bytes,
    dek: bytes,
    identity: AffIdentity,
    *,
    nonce: bytes,
) -> EncryptedAff:
    if len(dek) != DEK_SIZE:
        raise AKFCError("DEK must be 32 bytes")
    if len(nonce) != NONCE_SIZE:
        raise AKFCError("nonce must be 12 bytes")
    if len(plaintext) > MAX_PLAINTEXT_SIZE:
        raise AKFCError("plaintext size exceeds limit")
    plaintext_sha256 = hashlib.sha256(plaintext).digest()
    aad = build_aad(identity, len(plaintext), plaintext_sha256)
    encrypted = AESGCM(dek).encrypt(nonce, plaintext, aad)
    return EncryptedAff(
        identity=identity,
        plaintext_size=len(plaintext),
        plaintext_sha256=plaintext_sha256,
        context_hash=hashlib.sha256(aad).digest(),
        aad=aad,
        nonce=nonce,
        ciphertext=encrypted[:-TAG_SIZE],
        tag=encrypted[-TAG_SIZE:],
    )


def assemble_container(encrypted: EncryptedAff, wrapped_key: bytes) -> bytes:
    if not 1 <= len(wrapped_key) <= MAX_WRAPPED_KEY_SIZE:
        raise AKFCError("invalid wrapped key length")
    header_size = HEADER.size + len(wrapped_key) + len(encrypted.nonce)
    fixed = HEADER.pack(
        MAGIC,
        VERSION,
        FLAGS,
        header_size,
        encrypted.identity.key_epoch,
        encrypted.plaintext_size,
        len(wrapped_key),
        len(encrypted.nonce),
        len(encrypted.tag),
        encrypted.context_hash,
        encrypted.plaintext_sha256,
    )
    return b"".join(
        (
            fixed,
            wrapped_key,
            encrypted.nonce,
            encrypted.ciphertext,
            encrypted.tag,
        )
    )


def parse_container(
    container: bytes,
    identity: AffIdentity,
) -> ParsedContainer:
    if len(container) < HEADER.size:
        raise AKFCError("truncated container header")
    (
        magic,
        version,
        flags,
        header_size,
        key_epoch,
        plaintext_size,
        wrapped_key_size,
        nonce_size,
        tag_size,
        context_hash,
        plaintext_sha256,
    ) = HEADER.unpack_from(container)
    if magic != MAGIC or version != VERSION or flags != FLAGS:
        raise AKFCError("unsupported container")
    if key_epoch != identity.key_epoch:
        raise AKFCError("key epoch mismatch")
    if plaintext_size > MAX_PLAINTEXT_SIZE:
        raise AKFCError("plaintext size exceeds limit")
    if not 1 <= wrapped_key_size <= MAX_WRAPPED_KEY_SIZE:
        raise AKFCError("invalid wrapped key size")
    if nonce_size != NONCE_SIZE or tag_size != TAG_SIZE:
        raise AKFCError("invalid nonce or tag size")
    expected_header_size = HEADER.size + wrapped_key_size + nonce_size
    if header_size != expected_header_size:
        raise AKFCError("invalid header size")
    expected_size = header_size + plaintext_size + tag_size
    if len(container) != expected_size:
        raise AKFCError("truncated or oversized container")

    wrapped_start = HEADER.size
    nonce_start = wrapped_start + wrapped_key_size
    ciphertext_start = nonce_start + nonce_size
    tag_start = ciphertext_start + plaintext_size
    aad = build_aad(identity, plaintext_size, plaintext_sha256)
    if hashlib.sha256(aad).digest() != context_hash:
        raise AKFCError("context hash mismatch")
    return ParsedContainer(
        identity=identity,
        plaintext_size=plaintext_size,
        plaintext_sha256=plaintext_sha256,
        context_hash=context_hash,
        wrapped_key=container[wrapped_start:nonce_start],
        nonce=container[nonce_start:ciphertext_start],
        ciphertext=container[ciphertext_start:tag_start],
        tag=container[tag_start:],
        aad=aad,
    )


def decrypt_container(
    container: bytes,
    dek: bytes,
    identity: AffIdentity,
) -> bytes:
    if len(dek) != DEK_SIZE:
        raise AKFCError("DEK must be 32 bytes")
    parsed = parse_container(container, identity)
    plaintext = AESGCM(dek).decrypt(
        parsed.nonce,
        parsed.ciphertext + parsed.tag,
        parsed.aad,
    )
    if hashlib.sha256(plaintext).digest() != parsed.plaintext_sha256:
        raise AKFCError("plaintext hash mismatch")
    return plaintext


def public_key_spki_der(public_key: rsa.RSAPublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def validate_public_key(spki_der: bytes) -> rsa.RSAPublicKey:
    if not spki_der or len(spki_der) > 1024:
        raise AKFCError("invalid public key size")
    try:
        public_key = serialization.load_der_public_key(spki_der)
    except (TypeError, ValueError) as exc:
        raise AKFCError("invalid public key encoding") from exc
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise AKFCError("public key must be RSA")
    if public_key.key_size != 3072:
        raise AKFCError("RSA public key must be 3072 bits")
    if public_key.public_numbers().e != 65537:
        raise AKFCError("RSA public exponent must be 65537")
    return public_key


def key_id_from_public_key(spki_der: bytes) -> str:
    validate_public_key(spki_der)
    return base64.urlsafe_b64encode(
        hashlib.sha256(spki_der).digest()
    ).rstrip(b"=").decode("ascii")


def _oaep_padding() -> padding.OAEP:
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA1()),
        algorithm=hashes.SHA256(),
        label=None,
    )


def wrap_dek(public_key: rsa.RSAPublicKey, dek: bytes) -> bytes:
    if len(dek) != DEK_SIZE:
        raise AKFCError("DEK must be 32 bytes")
    validate_public_key(public_key_spki_der(public_key))
    return public_key.encrypt(dek, _oaep_padding())


def unwrap_dek(private_key: rsa.RSAPrivateKey, wrapped_key: bytes) -> bytes:
    if private_key.key_size != 3072:
        raise AKFCError("RSA private key must be 3072 bits")
    dek = private_key.decrypt(wrapped_key, _oaep_padding())
    if len(dek) != DEK_SIZE:
        raise AKFCError("unwrapped DEK must be 32 bytes")
    return dek



