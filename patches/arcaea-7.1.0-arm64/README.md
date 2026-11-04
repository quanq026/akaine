# Arcaea 7.1.0 ARM64 patches

Use the single command in [chapter 6](../../docs/guide/06-build-android-client.md).
The supported original is APKPure 7.1.0, build 1209907, arm64-v8a. Another build
must not be forced through these guards by changing hashes or offsets.

`build.py` rebuilds native code, Android payloads and Mod assets. The native
plan checks original bytes before applying each feature group. `bindings.json`
and the source adapter port the shared runtime; `pins.py` generates guards for
the resulting core. The SFX bridge resolves declared WAV files from the native
song cache. All unrelated APK members, including music and jackets, are checked
unchanged by the caller.

The `production-*` controls describe the published Akaine package and endpoints.
A matching song catalogue supplies diagnostic pack labels and declared WAV
names. Its contents may change the monitor output; its generated source and
hashes are recorded. The operator's external AKFC header and static crypto
archive produce the loader from public C++ source. Keys and build outputs stay
outside Git.

The older version directory holds only the shared, locked source baseline.
It is reused rather than copied into this folder. No staging build, one-time
operator script, deployment backup or binary payload is included here.
