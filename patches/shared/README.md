# Shared source baseline

These files are the byte-locked source baseline reused by the current 7.1
builder. They contain the AKFC loader, managed/resource helpers and semantic
runtime modules. The version-specific patch directory selects the supported build.

Run only `python -m akaine_build.android` as described in
[chapter 6](../../docs/guide/06-build-android-client.md). The current
[7.1 engine](../arcaea-7.1.0-arm64/README.md) adapts these sources and generates
all guards against the rebuilt 7.1 native core. No historical native pipeline,
patched APK, copied final library or private input map is needed.
