# Akaine V36 runtime for Arcaea 7.0.255

Use [chapter 6](../../docs/guide/06-build-android-client.md) for the current
source build. The entry point is `scripts/build_v36_client.py`.

`runtime/` contains one current set of C++/ARM64/Java/Smali sources. Its small
`sources.json` maps those files into a fresh build directory. `pin-layout.json`
describes version-specific byte guards; the builder reads their bytes from the
freshly rebuilt core rather than accepting generated private headers or final
libraries as inputs. The native core must match V36 before APK assembly.

The required external inputs are the verified V9 APK, matching native songlist,
Windows NDK and Java tools, a prefixed static BoringSSL archive, and the matching
opaque AKFC key header. No key, APK, generated DEX/SO, operator path map, physical
disk identity or deployment journal belongs in this directory.

`native/akfc_loader.cpp` is compiled with the external key header. Its JNI and
static-crypto contract is verified; an operator's different key is expected to
produce a different loader hash. Existing charts require their matching key.

The older `native-plan.json` and managed patch sources remain for the original
upstream-XAPK tooling. They are not an alternative V36 build path. The current
guide never combines their baseline hashes with V9.
