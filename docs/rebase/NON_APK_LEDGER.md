# Bundle, server, bot and database parity

This ledger separates the production V9 baseline released on 2026-10-22 from
later staging work. An APK contains client code. It does not deploy a bundle,
change server configuration, migrate ownership, publish R2 objects, update a
Worker or install bot assets.

`NON_APK_LEDGER.json` records sixteen entries, exact source hashes, external
historical evidence hashes and separate rollout requirements. Deployment receipts
describe historical actions; they are not authorization to repeat them.

## Production baseline to preserve

| ID | Component | Existing evidence |
|---|---|---|
| P01 | Content18, native Mod/Fan Charts, Collapse FTR10 with the epilogue background | Production bundle/API/native download and restart checks passed. Keep original-quality media. |
| P02 | Arghena/DIEIN compatibility and Title/BGM/scenery ownership prerequisites | The production18 additive migration inserted6,118 missing ownership rows for98 users while preserving scores, progress, consumables and positive amounts. Do not replay these historical counts. |
| P03 | Bot Collapse jacket and character98 full/icon/multiplayer assets | Four assets and the actual loading helpers were checked; bot source, database and service were unchanged. |

## Accepted staging source to carry with separate rollout gates

| ID | Component | Rebase handling |
|---|---|---|
| S01 | Dynamic pack representation and legacy62 fallback | Carry `client_packs.py`, the pack contract and API/download callsites. Keep defaults disabled until the rebased native client and pinned catalog pass. Headers never grant ownership. |
| S02 | Shared additive nonconsumable policy | Carry `content_grants.py` and caller-owned transactions. Two staging QA accounts passed; existing users were not backfilled. |
| S03 | Version-gated cloud unlock/story/score projections | Preserve Arghena minima, story completion, Testify score-ID compatibility and DIEIN projection in both dynamic and legacy responses. Preserve larger and unrelated progress. |
| S04 | Content-bundle `private, no-store` hook | Carry the small response hook and tests. Staging verification does not mean it is deployed in production or prove public CDN behavior. |
| S05 | Exact APK assetset profiles and forward complete recovery | Carry parser and guards. Preserve explicit enrollment and historical manifest registrations. Recompute the assetset for the rebased APK. |
| S06 | Aurora native catalog and signed delivery | Track1,532 imported songs/4,820 real charts separately from media. New constants remain-1; hidden compatibility charts do not establish PTT eligibility or universal gameplay compatibility. |
| S07 | Accepted protected-assets Worker allowlist extension | Preserve the historical deployed source under `operations/protected-assets/accepted-20261023`. It is different from the generic manifest-driven Worker. |
| S08 | Normalized atomic account/mapping, password-stdin and password guard source | Carry existing source and fixtures, but inspect actual bot/provisioner entrypoints and SQLite journal modes before rollout. Source parity is not live execution parity. |
| S09 | Exact APK-backed file omission | Carry the byte-preserving method and proof contract. The earlier3,791-path saving was672,980,805 bytes. Do not reuse its payloads or assetset proof blindly. |

The server source references are repository-relative. External evidence paths in
the JSON resolve through the operator archive; no private input map, live config,
database or account record is copied here.

## Rejected and deferred work

- **R01: rejected quality loss.** Earlier jacket resizing/recompression and
  preview22.05kHz/32kbps conversion are not accepted optimization. Do not carry
  those generators or outputs into a new release. Preserve original bytes,
  dimensions, channels and sample rate.
- **R02: unresolved format compatibility.** Forty-eight original MP3 gameplay
  files were converted to lossy Vorbis; seventeen lossless preview clips need an
  explicit native-format decision. These are not permission for further lossy
  encoding. Original recovery remains offline and its build is paused.
- **D01: deferred performance features.** Worker-thread loading and preload were
  not implemented. Reader cache remained an isolated, unaccepted candidate.
- **D02: canceled or unrequested features.** ArcCreate runtime was canceled.
  Extra Practice/autoplay, automatic chart upload/build and CI/CD are not part of
  this rebase.

The controlled emulator gameplay comparison did not reproduce sustained hollow
sound in its matched windows. That finding does not undo the confirmed media
quality regression or identify the physical-device audio cause.

## Operator constraints

1. Keep code, config, catalog, media, DB migration, Worker and bot deployment as
   separate reviewed changes. Do not overwrite live modules wholesale with the
   normalized checkout.
2. Preserve scores, saves, progression, currency, consumables, missions and
   existing positive ownership. Existing-user repair needs its own backup,
   additive transaction, completeness check and private change ledger.
3. Do not unregister old profile manifests while leaving their JSONs below the
   recursively scanned bundle directory: they become legacy graph entries.
   After a client consumes a higher content version, repair through a higher
   complete version rather than restoring a lower target.
4. Old base23/full24 objects are online but inactive and inherit rejected light
   media. They are not approved quality releases.
5. Track authored source, tests and sanitized digests. Keep config secrets,
   account data, databases, keys, APKs, game media, bundles and private build-input
   maps outside Git. Root reviews, commits and pushes milestones.

## Focused preservation checks

The accepted Worker reference retains its historical source bytes and a pure
literal patcher. Its four existing synthetic tests, an exact patch reproduction,
an owned rollback check and Node syntax checks can run without any deployment.
The repository-content check remains required before a push. See the reference
directory README and `PROVENANCE.json` for exact commands and results.

No server, database, device, R2 object, Worker or bot was changed while preparing
this ledger. Production activation and original-quality media recovery remain
separate work.

## Subsequent original-quality bundle milestone

The user later selected production18 as the exact baseline plus Aurora additions,
with per-song Download retained and all quality-reducing optimization rejected.
The complete base25 candidate has now been built and independently hash-verified
offline. See [its scope, receipt and pending native gates](../bundles/prod18-aurora-original.md).
No activation or live metadata/Worker/R2 change followed from that build.

## Subsequent production25 promotion — 2026-10-27

The reviewed production operation completed with `APPLIED_PRODUCTION25`. The
ordinary production target is now the complete original-quality `.25` base,
alias `7.0.255-prod-original-base25-20261027`. This later milestone supersedes
the rollout-state summary above; the individual P/S observations remain
historical evidence. See the
[separate production overlay and rollback record](../../operations/production25-20261027/README.md)
and [sanitized activation receipt](../../operations/production25-20261027/DEPLOYMENT.json).

The promotion carried the accepted dynamic63/legacy62 pack behavior, shared
six-type grant policy, dynamic/legacy world projection, bundle no-store hook and
default-off assetset parser. It preserved production password/OAuth guards,
score/PTT/Testify compatibility, character/banner handling and per-version
download routing. Exactly 1,532 Aurora chart rows were added with all five
constants `-1`; all 1,012 old production chart rows were retained. JTR test
content and staging-only aliases were excluded. No staging DB was copied.

The live nonconsumable completeness pass checked 99 users and found no gaps:
zero users changed, zero grants inserted or raised. Protected account, score,
save, currency and progress tables were unchanged. Staging and bot controls were
preserved. Worker loading, preload and Reader cache remain deferred.

Twelve production-adapted source siblings are archived outside the normalized
`server/` tree. Eleven retain exact deployed bytes. The archived
`core/config_manager.py` redacts only two secret literals; its exact deployed
whole-file hash, sanitized hash and allowed AST difference are recorded in
provenance. Private config, DBs, account identifiers, metadata/media, full
parameters and private rollback inputs remain outside Git. This archival step
did not perform a live operation. Native APK acceptance is recorded separately
in the production V36 release record.
