import json
import os
import shutil
import time
from pathlib import Path


APP_VERSION = "6.14.11"
SERVER_ROOT = Path(os.environ.get("ARCAEA_SERVER_ROOT", Path(__file__).resolve().parents[1]))


def main():
    bundle_dir = SERVER_ROOT / "database" / "bundle"
    manifest_path = bundle_dir / f"{APP_VERSION}.json"
    single_path = bundle_dir / f"{APP_VERSION}.cb"
    backup_dir = bundle_dir.parent / "bundle_backups" / f"single-part-{time.strftime('%Y%m%d-%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total_partitions = int(manifest.get("totalPartitions", 1) or 1)
    if total_partitions <= 1 and single_path.exists():
        print(json.dumps({
            "status": "already_single",
            "manifest": str(manifest_path),
            "part": str(single_path),
        }, indent=2))
        return

    shutil.copy2(manifest_path, backup_dir / manifest_path.name)

    part_sizes = []
    tmp_path = single_path.with_suffix(single_path.suffix + ".tmp")
    with tmp_path.open("wb") as output:
        for part_index in range(total_partitions):
            part_path = bundle_dir / f"{APP_VERSION}_{part_index}.cb"
            if not part_path.is_file():
                raise FileNotFoundError(part_path)
            shutil.copy2(part_path, backup_dir / part_path.name)
            part_sizes.append(part_path.stat().st_size)
            with part_path.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    cumulative_offsets = []
    offset = 0
    for size in part_sizes:
        cumulative_offsets.append(offset)
        offset += size

    for entry in manifest["added"]:
        old_part_index = int(entry.get("partIndex", 0) or 0)
        entry["byteOffset"] = int(entry["byteOffset"]) + cumulative_offsets[old_part_index]
        entry["partIndex"] = 0

    manifest["totalPartitions"] = 1

    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_tmp.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    tmp_path.replace(single_path)
    manifest_tmp.replace(manifest_path)

    print(json.dumps({
        "status": "merged",
        "manifest": str(manifest_path),
        "part": str(single_path),
        "part_size": single_path.stat().st_size,
        "backup": str(backup_dir),
        "old_part_sizes": part_sizes,
    }, indent=2))


if __name__ == "__main__":
    main()
