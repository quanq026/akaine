# Shared source baseline

These files are the byte-locked source baseline reused by the current 7.1
builder. They contain the AKFC loader, managed/resource helpers and semantic
runtime modules. Their `7.0.255` directory name records the version they were
first reviewed against; it is not another supported build choice.

Run only `scripts/build_android_client.py` as described in
[chapter 6](../../docs/guide/06-build-android-client.md). The current
[7.1 engine](../arcaea-7.1.0-arm64/README.md) adapts these sources and generates
all guards against the rebuilt 7.1 native core. No historical native pipeline,
patched APK, copied final library or private input map is needed.
