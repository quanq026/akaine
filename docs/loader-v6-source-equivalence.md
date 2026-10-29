# Accepted V6 loader source equivalence

This separate staging profile restores the versioned loader source to exact accepted V6 source SHA`52ec355ff72a62a64f8fc6bb48001ea62d43d5f2ca45d6f0eba137632e80e1b2`. The running R5/V20 loader already contains these behaviors. This source restoration is not a new crypto scheme or a newly deployed runtime fix.

## Restored behavior

Two source regions differed from accepted V6:

- A later authenticated download can replace the same temporary path. Clear the stale path cache before materializing its verified plaintext; do not return early merely because the path was once decrypted.
- Check both `fwrite` and `fclose`. On a short write or close failure,remove the partial file and leave no successful cache entry.

The accepted `rbe` read-mode support,authentication algorithms,ABI/JNI exports and existing key compatibility remain byte-identical to retained V6 source. The exact retry/cache test extracts the real changed function;27 checks cover re-download at the same path,short write,close failure,cache invalidation,recovery and open failure. The prior public source fails at authenticated retry plaintext; the restored candidate passes. The retained actual hook read-mode fixture also passes.

## Private input boundary

The compiler and existing symbol-prefixed static crypto archive are nonsecret hash-pinned inputs. Keep their machine-specific locations in an ignored local JSON outside the checkout:

```json
{"paths":{"compiler":"<installed NDK aarch64-linux-android24-clang++.cmd>","crypto":"<existing private libakfc-crypto.a>"}}
```

The existing production-compatible `embedded_key.h` is supplied only through environment slot `AKAINE_PRODUCTION_KEY_HEADER`. Its location remains outside the source checkout. The driver checks that the file reference exists and passes its parent directory to the compiler. It does not open,copy,decode,hash or log that header. Never generate or rotate a key for this equivalence build. Do not rerun the historical recovery builder.

The compiler necessarily consumes the opaque include during compilation. All compiler output is captured and discarded; failures expose only a generic message because diagnostics can quote an include source line. The private output `.d` dependency file contains paths and must remain outside Git; it does not contain include contents. Signing or other credentials are not inputs to this profile.

## Commands after independent review

Run from the source checkout after merging this overlay. The helper reuses the existing `build_akfc_loader.py`; there is no second compiler engine or APK assembly path.

```text
python scripts/build_loader_equivalence.py verify --local-paths <private-loader-path-map.json>
python scripts/build_loader_equivalence.py build --local-paths <private-loader-path-map.json> --output D:/AkaineBuilds/<fresh-loader-equivalence>
```

The verify command checks source and nonsecret inputs without accessing the opaque header. Build requires the existing environment reference and a fresh recognized physical-D output directory. It preserves strict flags,hidden symbols,static C++,captured diagnostics and private dependency capture.

The new loader must match accepted binary SHA`81beea88f021c4620019be6f4fdd4be76aa25300e1b90ccd889d9e067d5d99f8`. A mismatch records a stop receipt and blocks progression to APK packaging. Do not replace the expected hash to make a build pass. Diagnose only nonsecret source/toolchain/link/ELF facts first; do not dump encoded header tables or key bytes.

This profile never creates an APK replacement plan,installs an app or changes server/content state. Existing V20 core/DEX/monitor and content profiles remain frozen. After exact binary reproduction is proved,a separate reviewed next profile can add the loader as a fifth replacement; signature and fan download/Play/restart/retry gates remain separate.

## Acceptance limits

Prepared source and mocked compiler/privacy tests do not establish a production-header build. No NDK loader compilation or header access occurred during preparation. The build profile binds the compiler executable/driver and static archive; the private `.d` file captures the actual header dependency closure for later operator review. This initial profile does not claim every NDK header was rehashed or that a changed private header remains compatible.

Never publish the opaque header,private local path map,private dependency file or compiler diagnostics. Public receipts contain the environment slot name and whole artifact hashes only. A loader binary hash is an artifact identity check,not disclosure of the opaque include's contents or its standalone hash.
