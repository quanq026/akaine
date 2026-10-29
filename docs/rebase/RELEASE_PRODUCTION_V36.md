# Production V36: signed build and bounded runtime checkpoint

The production V36 APK completed a clean source rebuild and signed-artifact
verification on 2026-10-27. Independent verification was repeated on 2026-10-28.
This record covers the APK. The separate guarded operator workflow subsequently
reported `APPLIED_PRODUCTION25`; its [deployment evidence and rollback](../../operations/production25-20261027/README.md)
cover content and server activation. Core production emulator QA has also passed
the [recorded bounded cases](../performance/20261028-production-v36-runtime.md).
Restart, login persistence and cache persistence passed on that same signed
build. Runtime acceptance is limited to the cases recorded here.

## Artifact identity

| Item | Verified value |
| --- | --- |
| APK | `AkaineXD-7.0.255-prod-v36-20261027.apk` |
| SHA-256 | `a8b243c59adc527e8fa1ada27a0394979234d345b2063da40fcc2fbcc2ffc5fd` |
| Bytes | `1,209,824,845` |
| Application version / package | `7.0.255` / `akai.arc.lmao` |
| Signer certificate SHA-256 | `d8001c4321e553ace0b748b592946b0aa4c7cbcae92afe3bd30dd4f5f33471b6` |
| Signature | APK v2 verified |
| Intended content version | `7.0.255.25`, separately activated standalone base |

The authentic production V9 APK remains the sole raw core/DEX and archive root.
All five payloads were rebuilt again after sealing their candidate controls.
The loader and `classes4.dex` reproduce the accepted V36 bytes; the production
core, monitor and `classes3.dex` have distinct controls for production routes,
strict production CLI identity and production bundle partial caching.

## Verified scope

- Source lock, checkout map and all 1,063 input roles match the clean build.
- All five signed payloads match the sealed source controls.
- Visible auth, aggregate and content-bundle routes match production V9. The
  encrypted shared API base also matches; login alone is not the route proof.
- All 4,996 APK assets remain unchanged: `1,183,742,598` bytes, asset-set SHA-256
  `eccacb215213b17e1be6df318bbe716b0154942742c4e42c5e52e693ded8c5ab`.
- All 5,413 original members outside the five replacements remain unchanged,
  including the original manifest, package and application version.
- Signature verification uses the existing pinned certificate. The signing
  receipt also records successful 16 KiB alignment verification.
- All 106 accepted staging V36 authored roles remain byte-identical. V34/V35
  profiles and old source builders remain unchanged.
- Actual native `.eh_frame` and `.eh_frame_hdr` remain byte-identical to accepted
  normal V36 and authentic production V9. No unwind metadata was removed.
- Production source/signed-verifier tests passed `12/12`; strict production CLI
  tests passed `5/5`. Production Java fixtures passed 35 cases and 101 assertions.

The accepted guide CLI, ten-card date-ranked news UI, native owning descriptors
and original APK media remain. No QA timing probes, culling, worker, preload,
ANGLE or Vulkan experiments are included. The three unfinished loading/scene-lag
investigations remain deferred.

## Evidence binding

The [sanitized JSON record](RELEASE_PRODUCTION_V36.json) contains all five payload
hashes and hashes for the source lock, checkout map, assembly plan, exact clean
build receipt, signing receipt and signed verification. Rebuild and verification
commands are in [BUILD_PRODUCTION_V36.md](BUILD_PRODUCTION_V36.md).

The independent static check reads the signed APK, verifies its signature and
payloads, compares both routing layers against authentic production V9, and
compares every preserved member. It does not infer production runtime acceptance
from the previously accepted staging V36 runtime evidence.

## Bounded production runtime results

The exact signed production build passed login and Cloud Sync Download, pack
navigation, DIE IN ETR, Arghena FTR, Testify BYD with Replay Off and On, production
per-song Download and gameplay for Aurora `reflex`, and legacy FTR gameplay.
Tempest character35 showed expected/actual gauge6 and life bar6; asset-verified
Grievous Lady character7 showed gauge2 and life bar2. Character98 was previewed
only. [The runtime report](../performance/20261028-production-v36-runtime.md)
records the exact intervals, guard responses, test-ID correction and two existing
30-second CLI deadline timeouts followed by confirmed eventual completion.

These checks used an existing private QA account. Credentials, account identity,
raw cloud state, raw logs and the full-screen screenshot remain outside Git.
The sanitized installed-identity and restart receipts, with selected-state
derivation proof, are linked from the runtime report. Restart retained login and
bundle25, and cached Aurora FTR entered gameplay through direct Play without a
repeat Download prompt. Final state was Song Select with Replay Off.

## Bounds and deferred work

Native account persistence was checked at Main Menu after Title Continue, not
from an early title-screen signed-in flag. The three unfinished loading/scene-lag
investigations remain deferred. These bounded cases make no full-song clear,
score/PTT upload, physical-device speedup, exhaustive song/partner, long-duration
FPS, thermal or audio-quality claim. The APK asset identity does not replace the
separate online bundle activation evidence.

No credentials, private input map, key material, native binary, APK or game media
are included in this documentation record.
