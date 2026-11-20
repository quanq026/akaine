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
headers and a public packaging step. For a complete build command, use the
[7.1.0 guide](../../docs/guide/06-build-android-client.md).
