"""Small shared helpers for a local, version-guarded Android source build."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

from build_android_client import sha256_file as digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Python build helper is unavailable")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run(arguments):
    try:
        result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Local build tool failed; private diagnostics suppressed") from None
    if result.returncode:
        raise RuntimeError("Local build tool failed: " + Path(arguments[0]).name)
    return result.stdout


def fresh_output(path):
    path = Path(path).absolute()
    if path.exists():
        raise ValueError("Output directory must be fresh")
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.exists() and getattr(parent.stat(), "st_file_attributes", 0) & 1024:
            raise ValueError("Output symlink or junction is not allowed")
    return {"output": str(path), "fresh": True}


# Existing stage builders use this name; no machine or physical-drive identity is required.
physical_output = fresh_output
