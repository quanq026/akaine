# Arcaea 7.3.1 ARM64 patch source

| Folder | Source |
| --- | --- |
| [native](native/) | Menu news limit, WAV playback, Mod UI and replay behavior |
| [android](android/) | Android bindings for dynamic packs and WAV playback |
| [cli](cli/) | Device-side semantic CLI and scene actions |

The original ARM64 package is Arcaea 7.3.1, build 1210500.
[Download the ARM64 XAPK on APKPure](https://d.apkpure.net/b/XAPK/moe.low.arc?versionCode=1210500&nc=arm64-v8a&sv=24).
The input verifier in [akaine_build](../../akaine_build/android.py) checks the
XAPK, merges its five modules and verifies the merged APK hash.

This is a source checkpoint. The native modules still need generated ABI
headers and a public packaging step. See the [client input guide](../../docs/guide/06-build-android-client.md) to prepare the original package.

## r5 bugfix notes

- **Lagrange (partner ID `45`) skill bypass** (`libcocos2dcpp.so`):
  - `0x14e1bc8`: `01030054` -> `18000014` (`b #0x14e1c28`, UI gate)
  - `0x1a049f0`: `41030054` -> `1a000014` (`b #0x1a04a58`, gameplay gate)
  - Preserves partner level, uncapped, Skill Seal, and `replay_pins` checks.
- **Anomaly transition crash fix** (`axiumcrisis` -> `grievouslady`, `etherstrike` -> `fractureray`):
  - Server `DownloadList.add_songs()` in `server/core/download.py` automatically expands requested Anomaly source songs to include their unlocked target charts.
  - Client `native/official_code73.h` checks `target_song_ready()` via `0x1a3a2bc` in `official_init()` before arming Anomaly Replay if target song files are absent locally.
