"""Build a new offline core/monitor candidate; never packages APK or uses ADB."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = None
source = None

LLVM = None
BUILD = None
INSERT = 0x1a7d4d0
MAILBOX = 0x1c031c0
HOOKS = {
    0x13f24c0: "owned_constructor_gate", 0x17840b4: "owned_reset_gate",
    0x1784110: "owned_append_gate", 0x1716a5c: "owned_reserved_gate",
    0x17842e0: "owned_finish_gate", 0xf2bed8: "owned_pointer_member_gate",
    0x10a1c9c: "owned_song_member_gate", 0x1a55208: "owned_id_member_gate",
    0x11aa88c: "owned_header_gate",
}
SYMBOLS = {
    "owned_mailbox": MAILBOX, "native_constructor_continue": 0x13f24c4,
    "native_reset_continue": 0x17840cc, "native_append_continue": 0x1784124,
    "native_reserved_continue": 0x1716a60, "native_finish_continue": 0x17842e4,
    "native_song_member_continue": 0x10a1de0, "native_id_member_missing": 0x1a55300,
    "native_id_member_owned": 0x1a5559c, "native_string_equal": 0x18910e8,
    "native_header_continue": 0x11aa890,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def branch(pc, target):
    delta = target - pc
    assert delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27)
    return struct.pack("<I", 0x14000000 | ((delta // 4) & 0x3ffffff))


def virtual_bytes(blob, address, size):
    offset = struct.unpack_from("<Q", blob, 32)[0]
    entry, count = struct.unpack_from("<HH", blob, 54)
    for index in range(count):
        kind, flags, file_offset, va, pa, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", blob, offset + index * entry)
        if kind == 1 and va <= address and address + size <= va + filesz:
            return bytes(blob[file_offset + address - va:file_offset + address - va + size])
    raise ValueError("Unmapped file-backed virtual span")


def build_core(kit, output, llvm, source_api):
    global HERE, BUILD, LLVM, source
    HERE, BUILD, LLVM, source = kit / 'semantic/owned', output, llvm, source_api
    assert not BUILD.exists(), 'Fresh output required'
    BUILD.mkdir(parents=True)
    run([LLVM / "clang.exe", "--target=aarch64-linux-android24", "-c", HERE / "owned_gates.S", "-o", BUILD / "gates.o"])
    run([LLVM / "ld.lld.exe", "--entry=owned_constructor_gate", f"--section-start=.owned_gates={INSERT:#x}",
         *[f"--defsym={name}={address:#x}" for name, address in SYMBOLS.items()], BUILD / "gates.o", "-o", BUILD / "gates.elf"])
    run([LLVM / "llvm-objcopy.exe", "-O", "binary", "--only-section=.owned_gates", BUILD / "gates.elf", BUILD / "gates.bin"])
    payload = (BUILD / "gates.bin").read_bytes()
    assert len(payload) <= 0x2b30
    symbol_text = run([LLVM / "llvm-nm.exe", "--defined-only", BUILD / "gates.elf"])
    symbols = {name: int(address, 16) for address, kind, name in (line.split() for line in symbol_text.splitlines() if len(line.split()) == 3)}
    (BUILD / "gates.disassembly.txt").write_text(run([LLVM / "llvm-objdump.exe", "-d", BUILD / "gates.elf"]), encoding="utf-8")
    original = source.elf.raw
    candidate = bytearray(original[:INSERT] + payload + bytes(0x4000 - len(payload)) + original[INSERT:])
    phoff = struct.unpack_from("<Q", original, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", original, 54)
    for index in range(phcount):
        at = phoff + phsize * index
        ptype, flags, offset, va, pa, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", original, at)
        if offset >= INSERT and filesz: struct.pack_into("<Q", candidate, at + 8, offset + 0x4000)
        if ptype == 1 and flags == 5 and va == 0:
            struct.pack_into("<QQ", candidate, at + 32, filesz + len(payload), memsz + len(payload))
        if ptype == 1 and va == 0x1ba4920:
            assert memsz == 0x5e8a0
            struct.pack_into("<Q", candidate, at + 40, 0x5e920)
    shoff = struct.unpack_from("<Q", original, 40)[0]
    shsize, shcount = struct.unpack_from("<HH", original, 58)
    struct.pack_into("<Q", candidate, 40, shoff + 0x4000)
    for index in range(shcount):
        old_at, new_at = shoff + shsize * index, shoff + 0x4000 + shsize * index
        fields = struct.unpack_from("<IIQQQQIIQQ", original, old_at)
        if fields[4] >= INSERT: struct.pack_into("<Q", candidate, new_at + 24, fields[4] + 0x4000)
        if fields[1] == 8 and fields[3] == 0x1be49d0:
            assert fields[5] == 0x1e770
            struct.pack_into("<Q", candidate, new_at + 32, 0x1e870)
    operations = []
    for address, name in HOOKS.items():
        section = next(s for s in source.elf.sections if s["type"] != 8 and s["address"] <= address < s["address"] + s["size"])
        offset = section["offset"] + address - section["address"]
        patch = branch(address, symbols[name])
        operations.append({"address": hex(address), "before": original[offset:offset + 4].hex(), "after": patch.hex(), "target": hex(symbols[name]), "label": name})
        candidate[offset:offset + 4] = patch
    core = BUILD / "libcocos2dcpp-owned-dynamic-v19.so"
    core.write_bytes(candidate)
    updated = source.Elf(candidate)
    # All original section payloads retain their virtual locations, except9pinned instructions.
    allowed = {int(op["address"], 16) + delta for op in operations for delta in range(4)}
    for section in source.elf.sections:
        if section["type"] == 8 or not section["flags"] & 2: continue
        old, new = source.elf.bytes(section["address"], section["size"]), updated.bytes(section["address"], section["size"])
        assert len(old) == len(new)
        assert all(a == b or section["address"] + index in allowed for index, (a, b) in enumerate(zip(old, new))), section["name"]
    pins = []
    for address in HOOKS:
        function = source.unwind.containing(address)
        start, size = int(function["start"], 16), function["span"]
        if not any(p[0] == start for p in pins): pins.append((start, size, updated.bytes(start, size)))
    # Also pin the native vector helper called under the C++ exception boundary.
    f = source.unwind.containing(0x1325c0c); pins.append((0x1325c0c, f["span"], updated.bytes(0x1325c0c, f["span"])))
    pins.append((INSERT, len(payload), payload))
    pins.append((0x238, 0xbc, virtual_bytes(candidate, 0x238, 0xbc)))
    header = ["#pragma once", "#include <cstddef>", "#include <cstdint>"]
    header.append(f"inline constexpr uintptr_t OWNED_RX_END = {INSERT + len(payload):#x};")
    for index, (address, size, data) in enumerate(pins):
        header.append(f"inline constexpr unsigned char owned_pin_{index}[] = {{" + ",".join(hex(v) for v in data) + "};")
    header.append("struct OwnedPin { uintptr_t address; const unsigned char* bytes; size_t size; };")
    header.append("inline constexpr OwnedPin OWNED_CORE_PINS[] = {")
    header += [f"{{{address:#x},owned_pin_{index},sizeof(owned_pin_{index})}}," for index, (address, size, data) in enumerate(pins)]
    header.append("};")
    (BUILD / "owned_core_pins.h").write_text("\n".join(header) + "\n", encoding="utf-8")
    return core
