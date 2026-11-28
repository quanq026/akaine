# Arcaea 7.3.1 ARM64 patch source

| Folder | Source |
| --- | --- |
| [native](native/) | Menu news limit, WAV playback, Mod UI, replay behavior, and 120 FPS rendering optimizations |
| [android](android/) | Android bindings for dynamic packs, WAV playback, and API 30+ frame rate pacing |
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

## r6-perf 120 FPS notes

- `android/AkainePerf73.smali`: Syncs Android API 30+ `Surface.setFrameRate(120.0f | 60.0f, FRAME_RATE_COMPATIBILITY_FIXED_SOURCE)` in `onSurfaceCreated` and `setAnimationInterval`, and exposes JNI hooks for `libakaine_perf73.so`.
- `native/akaine_perf73.cpp`: Preserves `r5` `libcocos2dcpp.so` bit-for-bit; adds orthographic viewport AABB cell culling on `PackSelectionCell` (`64px`), `SongGroupCell` (`48px`/`120px`), and `SongSelectionCell` (`96px`), FNV-1a static bypass for `SongListLayer::visit` (`0x1b77930` -> `Layout::visit` `0xaba3cc`), full-buffer `GL_ARRAY_BUFFER` driver orphaning (`glBufferSubData` -> `glBufferData(..., GL_STREAM_DRAW)`), and `clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME)` 60Hz native frame pacer (`paceCap60`).
