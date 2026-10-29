# One local source build for accepted staging R5

Historical workflow for source commit `7bc006e3322fde54e2e4b45d0bd7014854fa6e8c`. The current build command defaults to V20; use `local-release-build-v20.md` with current source. To reproduce R5, use this source commit and its immutable R5 profiles.

This executable path supersedes the pending path-normalization section in `source-reliability-v19-r5.md`. It reuses `scripts/build_android_client.py`; it does not add a second APK assembly engine, deploy to a server, publish a bundle, start an emulator or sign an APK.

## Observed result

A fresh private kit on physical D rebuilt all four source payloads to **exact accepted R5 hashes**:

| Payload | SHA-256 |
|---|---|
| Core native | `7f3811cbe0308b709c9dcd4c72b6ffe18ee23454973fcb852a966ca5cf0c36c8` |
| Monitor native | `34fa0f2106f2e3ee43e125f05e5fbdd57ace57b4b6f1ded52fe381ee2aa209fc` |
| classes3.dex | `a4376908eee34e5c9eb405f763342322f35cfbb2dd516e39c6344a14c8d43b88` |
| classes4.dex | `6c4b63c3168a25a98c476862bc84f8de53de31257439c1e7473acfb3315f0ba0` |

The existing builder assembled an unsigned APK SHA-256 `e026e0abb9d3c337eba832fd0cab89b1526a2d28fed775899f57d069aa68874a`. Its receipt is `D:/AkaineBuilds/big-update-20261024/r5-clean-build/BUILD_RECEIPT.json`. Core gates were assembled/patched again from the pinned V18 core; monitor and owned code were recompiled; DEX inputs were freshly disassembled, patched and reassembled. The expected replacement files were controls for hashes only, not copied into the compile output.

This does not reproduce the final signed APK bytes: alignment/signing remains the established separate operation. No signing key, password or credential provider was read by this build. An unsigned rebuilt APK is not installable release acceptance.

The44-file checkout-source normalization was then built independently at `D:/AkaineBuilds/big-update-20261024/r5-checkout-source-build/build/BUILD_RECEIPT.json`. It reproduced all four payload hashes and the same unsigned APK hash above. Its checkout-source map SHA-256 is `176aab42e9e3aa0df0daee4a724dac05ff386670b681b9aeef6d7ae692e4708f`. This run used Java's source-file launcher rather than the old compiled class.

## Private kit roles and boundaries

The committed source lock and replacement plan use logical paths, not machine drive paths. `staging-v19-r5-checkout-sources.json` binds44 authored files to this checkout:40 runtime/owned source files, three active Python format helpers and `RawDexTool.java`. The files live under `patches/arcaea-7.0.255-arm64/runtime/`, with exactly the accepted R5 bytes. Generated instruction/ABI pin headers, widget-address tables and telemetry catalog stay private.

The driver verifies those44 roles against the checkout; a stale or missing private copy cannot replace them. `all` and `hydrate` copy those checkout bytes into the fresh kit. Separate `build` verifies both the checkout and the hydrated kit before compiling the kit. It checks the checkout map against the immutable source-lock hash and checks every file against that lock. The operator keeps a local ignored mapping JSON outside Git for the remaining roles:

The scoped `.gitattributes` preserves the release JSON and runtime source bytes. Accepted sources contain41 LF files and3 CRLF files; automatic line-ending conversion would invalidate the source lock even when the compiler sees equivalent text.

```json
{"status":"LOCAL_ONLY_DO_NOT_COMMIT","paths":{"base/v18-staging.apk":"<private original path>","semantic/native/pins_official.h":"<private generated pins path>"}}
```

The real map requires every private role in the lock, not just these examples. Old maps that still include authored roles remain accepted, but those entries are overridden by checkout files. The development session's complete map remains outside the public candidate at `work/big-update-20261024/R5_LOCAL_PATHS.json`. It contains file locations and hashes only. Game payloads, version-locked generated pin bytes, telemetry catalog and original APK remain private. Signing material is not a mapped role.

Hydration verifies978 roles, then copies checkout sources and private project inputs into a fresh physical-D kit. The SDK/NDK and JDK runtime stay installed on fast W. The kit contains source, pure format helpers, DEX source files, RawDexTool/JAR and accepted hash controls; it contains no signing keys. Toolchain header/link dependencies are pinned in the source lock. No dependency is downloaded or installed. Unused historical wrappers and prior built artifacts remain hash controls in the original lock; they are not promoted as the current operator workflow.

## Commands

Use the project's existing Python with its already-installed dependencies. Run from the clean repository containing the driver, its test, both profile JSON files, replacement plan and versioned runtime sources.

Verify original role paths without writing:

```text
python scripts/build_release_profile.py verify --local-paths <local-role-map.json>
```

One command hydrates a fresh private kit and builds source payloads plus an unsigned APK:

```text
python scripts/build_release_profile.py all --local-paths <local-role-map.json> --output D:/AkaineBuilds/<fresh-local-build>
```

For diagnosis, the same operations can run separately:

```text
python scripts/build_release_profile.py hydrate --local-paths <local-role-map.json> --output D:/AkaineBuilds/<fresh-kit>
python scripts/build_release_profile.py build --local-paths D:/AkaineBuilds/<fresh-kit>/local-paths.json --output D:/AkaineBuilds/<fresh-build>
```

The driver refuses existing output directories, an unrecognized physical D device, junctions/symlinks, changed input hashes, duplicate/unsafe logical roles, unpinned compiler includes and mismatched source payloads. If generated payloads differ, it preserves outputs and `PAYLOAD_MISMATCH.json` for diagnosis and does not assemble an APK. Do not overwrite controls merely to make a build pass.

## Pipeline reuse

`build_dynamic_core.py` contains the accepted core gate assembly/patch routine with environment paths supplied by the driver. Gate/branch constants and the actual original-section preservation checks remain the same. The driver uses the retained ELF/unwind readers inside the hydrated kit, avoiding dated absolute work-tree imports.

Native monitor flags remain no exceptions/no RTTI; owned code retains its C++ exception boundary. The link keeps static C++,16 KiB page alignment and original library/export behavior. The source lock binds the NDK inputs, not a claim that any future compiler is interchangeable.

RawDexTool uses the existing Java/dexlib2 format path. Java17's source-file launcher compiles the versioned `RawDexTool.java`; the retained `.class` is not executed. The versioned DEX compare helper proves only early preparation changed and V18 pacing methods remain exact. DEX037 checksums are checked again. The four matching outputs are then fed to the existing APK builder.

## Verification and remaining work

Five focused driver tests cover unsafe/duplicate roles, input hash/missing-role rejection, checkout-source precedence and the existing four-payload profile contract. Actual clean native/DEX build and unsigned assembly passed for both the earlier hydrated-source profile and the44-file checkout normalization. Both actual compiler dependency files resolved only pinned inputs. Re-run the same guards for a later source/profile change; the earlier receipts are not acceptance of a changed candidate.

Root still needs independent review of the normalized driver and its build receipts, then may integrate the source files. Existing R5 runtime acceptance belongs to the source-equivalent control. Rebuilt signing/alignment and fresh device install are separate gates; this task performs neither. Production profile generation and bundle-thinning remain outside this staging build command.
