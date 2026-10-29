# Current 7.0.255 patch set

Follow [chapter 6](../../docs/guide/06-build-android-client.md). The single user
entry point is `scripts/build_android_client.py`; it starts from the original
APKPure arm64 XAPK and produces V36. Do not run individual internal stages.

This directory holds the current changes for that exact version:

- `native-plan.json` checks original bytes before applying the native changes.
- Native assembly/runtime source is compiled for the current V36 behavior.
- Managed source patches update Android code, package resources and the Mod UI.
- Version-specific guard data is checked against freshly built code.

The build merges the original package, applies the guarded changes, compiles
native and managed code, and verifies unrelated APK members are unchanged.
It does not use an older Akaine APK, an accepted final library, generated
private pin headers or a maintainer's disk/path map as a build input.

The AKFC loader uses the matching external key header and prefixed static
BoringSSL archive. A different operator key produces a different loader hash;
existing encrypted charts require their matching key. Keep keys, APKs and build
outputs outside Git.

Historical releases and development experiments belong in the private
development repository. This public patch set follows the current guide.
