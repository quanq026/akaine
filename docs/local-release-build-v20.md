# Local source build for staging V20

Historical checkpoint. Use [the final five-payload workflow](local-release-build-final.md) for the current combined staging profile. This document retains the earlier V20 command and its evidence only.

The current build driver defaults explicitly to the V20 source lock, checkout-source map and replacement plan. It uses the existing native/DEX steps and `build_android_client.py`. The historical R5 profiles remain unchanged; source commit `7bc006e3322fde54e2e4b45d0bd7014854fa6e8c` preserves the R5 command.

## Bound candidate

V20 changes five authored monitor files: `anomaly_monitor_mod.cpp`, `cli_ui_native.h`, `mod_category_bridge.h`, `sampler_read_probe.h` and `staging_cli_bridge.h`. Their paths remain inside `patches/arcaea-7.0.255-arm64/runtime/semantic/native/`. The checkout-source map still binds44 authored files, and the complete input lock still has978 roles.

| Payload | Expected SHA-256 |
|---|---|
| Core native, unchanged R5 | `7f3811cbe0308b709c9dcd4c72b6ffe18ee23454973fcb852a966ca5cf0c36c8` |
| V20 monitor native | `803355ee785dbc705d63c8f0b0111b86088d70dc09eda48378017ea90c386ca8` |
| classes3.dex, unchanged R5 | `a4376908eee34e5c9eb405f763342322f35cfbb2dd516e39c6344a14c8d43b88` |
| classes4.dex, unchanged R5 | `6c4b63c3168a25a98c476862bc84f8de53de31257439c1e7473acfb3315f0ba0` |

The `v19-r5/payload/` logical role names are retained for compatibility with the existing private kit and builder. Their expected hashes select the candidate; that historical prefix is not the release version. Generated native output filenames retain their earlier `owned-v19` names for the same reason.

V20 continues to use the pinned private V18 APK as its input base and content version `7.0.255.20`. It does not change the content bundle, signer, server profile or production endpoint. Signing material is not a mapped input.

## Local commands

Run from the merged source checkout, with the existing project Python and installed toolchain. The operator's private role map supplies934 private inputs; the44 authored source paths are resolved from this checkout.

```text
python scripts/build_release_profile.py verify --local-paths <V20-private-input-map.json>
python scripts/build_release_profile.py all --local-paths <V20-private-input-map.json> --output D:/AkaineBuilds/<fresh-v20-source-build>
```

The development-session private map is kept outside the candidate tree at `work/big-update-20261024/V20_PRIVATE_PATHS.json`. It reuses the hydrated R5 kit and changes only the expected monitor-control path to the reviewed V20 monitor. Do not commit that machine-local map.

The driver verifies source and private hashes, hydrates a fresh kit on the recognized physical D drive, rebuilds all four payloads and requires every expected hash before unsigned APK assembly. It compiles `RawDexTool.java` through the existing Java17 source-file launcher. The scoped `.gitattributes` preserves runtime and profile bytes across checkout.

## Evidence and execution order

Profile preparation and six focused tests are separate from a clean native/DEX build. A clean V20 build must produce its own `BUILD_RECEIPT.json`; an R5 receipt or the earlier CLI-only monitor build cannot substitute for that proof. The unsigned APK hash will be measured from the actual V20 assembly.

Root is running emulator A/B benchmarks. Defer native compilation, DEX generation, APK assembly and full input hashing until root signals that the measurement window has ended. After source build acceptance, signature, install and emulator runtime gates remain separate. The user requires emulator acceptance before physical-device testing.
