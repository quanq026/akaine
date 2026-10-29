# Current staging build and verification

This is the current local source workflow for the combined big-update staging profile **V26**. The final profile, checkout-source map and replacement plan are named `staging-final-*.json`. R5 and V20 profiles remain immutable historical controls. The client application is still `7.0.255`; content version in this source profile is `7.0.255.20`. New bundle profiles have their own separately verified content versions and activation gates.

## Bound source and inputs

The build resolves versioned authored runtime code, finite Reset and integrity/run-once assembly, cap60 smali and active format helpers from this checkout. Generated native instruction/ABI pins, game assets/catalog, original APK and crypto/toolchain inputs stay in the operator-owned private kit. The complete candidate source lock contains **1011 roles**, including **65 authored-source bindings**. Expected compiled payloads are hash controls only; the build must compile/assemble all five outputs rather than copy accepted binaries into the output.

The opaque production-compatible loader include is supplied through environment reference `AKAINE_PRODUCTION_KEY_HEADER`, outside the checkout. The driver does not open, copy, hash, decode or log its contents; the compiler consumes it. Compiler diagnostics and the `.d` path list stay private. Do not regenerate or rotate a key for an equivalence build.

SDK/NDK/JDK and emulator remain on fast W; heavy private kits and build output remain on the recognized physical D drive. Use a fresh output directory. The configured local JSON supplies the private role paths; it does not contain the opaque header material or a signing password. Never commit that local JSON, generated pin contents or key include.

## One build command

With the existing project Python and installed dependencies:

```text
python scripts/build_final_release_profile.py build --local-paths <final-private-paths.json> --output D:/AkaineBuilds/<fresh-final-build>
```

The existing engines perform the work: verified role hydration, `build_dynamic_core` for the owned pack gates, the reviewed Reset helper, `build_integrity_core` for incoming-asset SHA, exact task-size and run-once gates, monitor/owned compilation, RawDexTool source-file launch for early preparation and cap60 DEX, the loader equivalence wrapper, and `build_android_client.py` for unsigned APK assembly. There is no second APK engine, dependency installation, emulator action or server deployment in this command.

The loader compiler is deliberately taken from the original pinned installed NDK path. A hydrated logical `loader/compiler` file alone lacks its sibling `clang++.exe` and toolchain. The first clean attempt stopped at this guard. The current driver passes `loader_paths(paths)`, while other hydrated project inputs remain inside the fresh private kit. A focused regression prevents changing it back to `loader_paths(hydrated)`.

The actual V26 clean build from the current checkout reproduced these five exact payload hashes:

| Payload | SHA-256 |
|---|---|
| Core with pack, Reset, incoming-SHA, exact-size and run-once gates | `c29edd5f07010fcdcbba28e614f6791f60d5dafb22574640420b56fab9cba3fc` |
| High-FPS CLI, asset capability, owned pack and typed bundle error monitor | `2d59e229522d6e0a01d3fdd7c261a81b4aeca27869f05f6a65d5706312704f7f` |
| Exact production-compatible V6 loader | `81beea88f021c4620019be6f4fdd4be76aa25300e1b90ccd889d9e067d5d99f8` |
| classes3.dex with early preparation and cap60 pacing | `ec16e94016acb1d602e9f01bd99beacd4a9c5b7eac9fa84825f078d6fabc6153` |
| Unchanged early preparation classes4.dex | `6c4b63c3168a25a98c476862bc84f8de53de31257439c1e7473acfb3315f0ba0` |

The signed V26 assembly receipt binds unsigned APK `1f9f71eb6c1be583a4df3fb99a15060c45a7e4f752d4552f84e5363c8bfa4e60`. The fresh source build reproduced that complete unsigned ZIP identity exactly, then the final verification command bound it to the signed V26 artifact. Matching five payloads alone remains insufficient. Exact assets remained 4,996 files / 1,183,742,598 bytes, canonical asset-set digest `eccacb215213b17e1be6df318bbe716b0154942742c4e42c5e52e693ded8c5ab`. This is a source/artifact result, not runtime acceptance.

## Signing boundary

The source build ends at an unsigned APK and `BUILD_RECEIPT.json`. Use the established operator signing helper with the private keystore and environment password slot; it already invokes Android `zipalign -P 16` and `apksigner`, preserves the install-compatible certificate and verifies v2 signatures. Passwords are passed as `env:<slot>`, never literal argv values. No signing key or password is a public source-lock input.

The source workflow reproduces the five payloads and observed unsigned ZIP. It does not claim byte-for-byte reproducibility of signing output or read signing material. The current signed staging artifact is `AkaineXD-7.0.255-staging-big-update-v26-20261024.apk`. Its receipt records APK `325dff2c0d6bb81d69c242adbb46102705015d68ee696764b5563534e434567d` with signer certificate digest `d8001c4321e553ace0b748b592946b0aa4c7cbcae92afe3bd30dd4f5f33471b6`. A later signing run must receive its own receipt and actual verification.

## One verification command

Verify source/plan/private hashes without compiling, accessing the opaque include or touching a device:

```text
python scripts/verify_final_release.py --local-paths <final-private-paths.json>
```

To bind the same source profile, build receipt and signed artifact in one read-only command:

```text
python scripts/verify_final_release.py --local-paths <final-private-paths.json> --build-receipt <final-build/BUILD_RECEIPT.json> --apk <signed-staging.apk> --apk-receipt <signed-staging.receipt.json>
```

The second form checks the current source map/lock, five actual ZIP members, whole APK hash/size, source and unsigned-build identity, the actual certificate and v2 signature using the existing `apksigner.jar`, and every APK asset against the private canonical asset manifest. The output reports counts/hashes only. It never exports the private asset list or accesses a device.

Full role/asset verification reads large files and should run outside matched FPS capture windows. A same-object byte-resume claim also needs actual restart evidence: the observed StartScene lifecycle clears `dltemp` on initialization, so a correct in-process Range prefix test does not establish retained bytes across process restart. Full-download recovery and byte efficiency are separate results. The retained verifier fixtures check payload/receipt/signature mismatch rejection and the loader path regression. `python -m unittest test_integrity_core` from `scripts/` checks compiled gate opcodes, distinct callback capture/task ownership, fresh/active/terminal run states, private pin regeneration and rejected source/gate identities. These fixtures do not substitute for running the command against the actual release.

## V26 native and CLI boundaries

The exact-size gate reads expected bytes from **x25**, the task resolved by the actual callback ID and owning the final file path. The shared callback capture x24 can belong to another transfer and is not the expected-size owner. The original skip-hash flag path remains unchanged. Incoming added/replaced assets take the existing actual SHA path; unchanged reused assets keep the existing fast path.

The run-once gate skips an object with a native handle or terminal flag. Known bundle and song queue retry paths construct fresh tasks. This fixes the observed synchronous cached-JSON reentrant duplicate launch; it is not an atomic guard for arbitrary concurrent callers. Runtime acceptance must include a single part task at the retained Range offset, ordinary song download, and failure followed by a new attempt.

The paired host CLI and monitor recognize the exact one-button content error before a stale progress node. `bundle dismiss-error` releases only that typed native button with fresh ownership/pin/deadline checks. The two-button transport failure is observed as failed and blocks underlying actions; Retry/Cancel actions are not exposed. Keep `akaine_stag.py` and the monitor from the same accepted profile. Generated `bundle_error_pins.h` stays in the private map.

The host-only amendment keeps the same V26 APK and native payloads. Each public `Client.execute` starts a fresh configured 1â€“30 second deadline and clears only its per-command dispatch/credential-ownership flags. A reused client still rejects a changed bridge session; it never resets identity or retries an action automatically. All ADB work inside one command shares that deadline; existing bounded lock cleanup remains separate. A previous fill cannot own credential files created for a later command.

The portable host suite contains 109 passing tests, including six reused-client cases: delayed first command, separate command budgets, preserved admission time, no extra budget/retry, no stale unknown-outcome flag before dispatch, and no later foreign credential cleanup. Run `python -m unittest discover -s scripts/akaine_cli -p "test*.py"` from the checkout. This host-only source-lock amendment changes the bound host role and checkout-map digest; the five APK payload hashes, unsigned ZIP and signed APK remain unchanged. The amended profile passed a fresh complete build and all 996-role signed-artifact checks, with the same whole unsigned identity and signed V26 APK. A fresh full source build and the usual verification command must bind the amended profile; the earlier profile receipt cannot be reused silently.

V23 is withdrawn because its first size gate used the wrong callback capture. Range/short-body diagnostic APKs are temporary evidence tools, never release or rollback targets. V22 is a historical baseline with the incoming-asset trust defect and duplicate scheduling behavior; it is not an automatic recovery choice for integrity failures.

## Runtime and rollback

Artifact verification does not authorize activation or prove gameplay. Emulator gates precede physical Android tests, as requested by the operator. Keep source/payload/asset receipts, the existing full bundle and accepted prior APK controls. A staging APK rollback is allowed only to an explicitly accepted, same-signer candidate with its own receipt. Preserve app data and verify current cache/content state before replacement. Follow the dynamic-pack rollback rule: an old fixed-capacity client must not start with cached ownership above its supported bound. Capability loss from a thin content version requires forward full recovery, not reverting to an older content number or dropping its canary enrollment.

The final source command changes no R2 objects, server profile, production process, database, account progress or scores. Deployments need a current live source/config inspection and their own backup, candidate, acceptance and rollback receipts. CI/CD, new Mod/theme/Practice behavior and the canceled ArcCreate runtime remain outside this update.


## Cache V4 and onboarding source amendment (apply after runtime acceptance)

This amendment preserves the accepted cache V4 classes3 hash
`20cdddd94102ef27c366379a5b11b3cb33cc8aa3e67cca502158373c62498761` and changes only
the expected monitor to onboarding and MainMenu guide monitor
`b28bb3128662d7b4f9c47e2a41b5678536a4d96bc97241dbdeb072729dd0cd9f`. The earlier
V26 table and unsigned/signed APK identities above are historical controls, not
claims that the amended full APK has already been built or verified. A fresh full
source build and signed-artifact verification must bind the amended lock.

The paired monitor and host CLI expose three fixed native onboarding UI actions:
`onboarding_setup`, `onboarding_cancel`, and `onboarding_skip`. Obtain each token
from a fresh `ui list`; send it once and inspect the returned stage. The sequence
is welcome, offset setup, skip confirmation, then the positively verified Settings
layer with both dialogs absent. Missing pins, stale identity, disabled/running
flags, unknown modals or blocking overlays make the action unavailable. A timeout
is an unknown outcome and must not be automatically retried. These actions invoke
the normal native callbacks; they do not fabricate calibration samples, write
preferences directly, accept terms, fill login fields, or submit credentials.

Generated `semantic/native/onboarding_pins.h` remains a private generated input,
like the existing UI/bundle pin headers. Add its exact path through the private
local role map; do not commit its disassembled game instruction bytes. The new
`cli_onboarding.h` and regression fixtures are authored checkout sources. The
normal final monitor compiler already follows this header include closure; no
new compiler, dependency, APK engine or runtime option is introduced.

Run the complete host suite with
`python -m unittest discover -s scripts/akaine_cli -p "test*.py"`; the reviewed
source has 113 passing tests. The fixture at
`patches/arcaea-7.0.255-arm64/runtime/onboarding/test_onboarding.cpp` compiles on a
host C++17 compiler with `-I<hydrated-private-kit>/semantic/native`. It exercises
the actual authored onboarding helper with synthetic bounded memory, never target
native code. Android compiler/ELF checks and host tests do not replace the real
Welcome-to-Settings acceptance gate. Keep the exact runtime evidence before
applying this amendment.


### Ordinary first-run MainMenu guide

The normal source also recognizes only the exact scene-owned `main_menu_hint`
ProgressionGuideLayer captured on a fresh MainMenu. The guide's completion closure
and registered touch-disable callback must match the pinned current core and scene.
Use a fresh `main_hint_continue.<context>` token from `ui list` once, then inspect
the acknowledgment and obtain a fresh token for the next native step. The token
invokes the normal guide advance callback and requires changed step/pending state
or guide disappearance on the same scene. Underlying `main_music` remains blocked
until the guide finishes. Unknown guides, wrong owners/callbacks, stale tokens,
closed deadlines, wrong threads, and failed pins stay blocked. No preference reset
or fake calibration is used. This is separate from the Welcome/offset/skip chain,
which remains guarded as described above.

`semantic/overlays/main_hint_pins.h` is an additional private generated input. Keep
its exact external role path in the private local map, not in authored Git source.
The portable fixture `runtime/onboarding/test_main_hint.cpp` covers the existing
pack guide plus the exact new MainMenu guide and rejection cases. The paired host
CLI has 113 passing tests. Apply this amendment only after root records the actual
MainMenu guide runtime outcome; static/host tests do not establish target success.


The exact single Welcome button is named `button3`, as observed on the current
DialogLayer's +0x330 field. The V2 helper accepts only that name; `button4` remains
a rejection fixture. Ordinary callback ownership, ancestry, running/enabled flags,
native pins and post-action state checks are unchanged. Root's runtime evidence
confirmed Welcome setup, cancel, Yes/skip and Settings close with offset0 unchanged;
four exact MainMenu guide acknowledgments completed and restored ordinary Music.
