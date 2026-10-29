# Historical production25 server overlay

The reviewed production25 operation completed on 2026-10-27. Its sanitized
[deployment receipt](DEPLOYMENT.json) records `APPLIED_PRODUCTION25`, the exact
before/after file hashes, the production import gate and the bundle API matrix.
This archive was recorded locally on 2026-10-28 without another live operation.

The ordinary production target is content `7.0.255.25`, alias
`7.0.255-prod-original-base25-20261027`: one standalone full base with ten CB
parts, 4,538,288,896 total download bytes and original media. The original25
manifest SHA256 is
`6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891`.
APK and native QA are tracked separately in
[the production V36 release record](../../docs/rebase/RELEASE_PRODUCTION_V36.md).

## Source boundary

`server-overlay/` contains the twelve production-adapted source siblings below.
The normalized/staging `server/` tree was left intact. The production overlay
preserves production password validation, OAuth opt-in, score/PTT and Testify
compatibility, character/banner handling and the existing per-version download
prefix. It excludes JTR test content, staging-only signing aliases and the
metadata filter that would hide thirteen existing official production IDs.

| Production-relative destination | Accepted change |
|---|---|
| `core/bundle.py` | Guarded assetset parser; profile activation stays disabled. |
| `core/client_packs.py` | Pinned dynamic pack representation. |
| `core/config_manager.py` | Independent default-off dynamic/profile controls. |
| `core/content_grants.py` | Six-type additive nonconsumable policy. |
| `core/download.py` | Dynamic authorization and catalog reload; production metadata/routing retained. |
| `core/pack_contract.py` | Catalog validation and dynamic ownership projection with legacy62 retained. |
| `core/user.py` | Shared registration grants and dynamic pack methods. |
| `server/others.py` | Bundle `private, no-store` and assetset forwarding. |
| `server/purchase.py` | Dynamic client response representation. |
| `server/user.py` | Dynamic/legacy world projection with production serialization retained. |
| `tools/check_dynamic_pack_catalog.py` | Read-only catalog checker. |
| `tools/create_user_cli.py` | Shared grant policy with production character/transaction checks retained. |

Eleven files are byte-identical to the deployed candidates. The archived
`core/config_manager.py` has only the `Config.SECRET_KEY` and
`Config.LINKPLAY_TCP_SECRET_KEY` string literals replaced with empty strings.
The exact deployed whole-file hash and the sanitized archive hash are both in
[PROVENANCE.json](PROVENANCE.json). An AST comparison verified that every other
node is unchanged. No individual secret value or secret-value hash is stored.
Current values must come from private operator configuration or an approved
runtime secret source. The sanitized file is not a drop-in deployment artifact.

## Deployment scope and result

The operation backed up seventeen source/config/metadata/catalog targets and an
online SQLite snapshot before applying changes. It appended exactly 1,532
accepted Aurora server entries, both metadata additions and chart rows. All five
new chart constants remain `-1`; all 1,012 prior production chart rows, including
the thirteen official rows absent from staging, were retained. No staging DB was
copied. No JTR positive-constant test row was promoted.

The six permitted grant types were `pack`, `single`, `character`,
`course_banner`, `world_song` and `world_unlock`. The live completeness pass
checked 99 users and found no missing grants: zero users changed, zero inserts
and zero raised amounts. Protected tables were unchanged. Production restarted;
staging and bot services and files were preserved.

Local bundle requests at `0.0.0`, `.18`, `.20` and `.24` returned one complete
`.25` result; `.25` and `.26` returned no update. The actual production
interpreter imported ten reviewed modules from production paths and validated
the pinned 63-pack catalog. These checks do not establish all-song playback or
physical-device audio acceptance.

## Operator references and reproduction

- `operator/production25_runtime.py` is the exact deployed guarded runtime source.
- `operator/operate_production25.reference.py` and
  `operator/test_production25_operator.reference.py` preserve the authored
  orchestration and synthetic fixture source. Machine-specific input locations
  were replaced with explicit external environment paths.
- `PLAN.json`, `REVIEW.json` and `OPERATOR_TESTS.json` retain sanitized historical
  evidence. The seven operator fixtures passed, including scoped rollback,
  concurrent progress preservation, SQL-trigger denial and foreign-edit guards.
- Full parameters, metadata/catalog payloads, config, DBs, account identifiers,
  media, original preimages and the private grant ledger remain outside Git.
  Historical input digests identify those external inputs without packaging them.

The reference scripts are not portable activation commands. Their original
private workspace layout and inputs are required through
`AKAINE_PROD25_OPERATOR_DIR`; the original manifest path is supplied through
`AKAINE_ORIGINAL25_MANIFEST`. Sanitizing the references changes their hashes, so
an old review cannot authorize execution. Any future operation needs fresh live
inspection, new immutable outputs and a new independent digest-bound review.
Do not regenerate private parameters or run an apply from this archive.

Run the archive's offline preservation and scoped repository-content check:

```text
python operations/production25-20261027/verify_archive.py
```

The command checks source hashes, Python syntax, exact redaction boundaries and
all new files against the existing repository-content policy. It makes no
network, server, account or deployment calls. Root runs the full repository check
before committing the complete release milestone.

## Rollback constraints

The production backup is:

```text
/home/ec2-user/arcaea-server/database/backups/20261027T165652Z-before-prod25
```

Inspect its durable receipt and current hashes first. Stop only production for
an authorized repair. Restore only owned source/config/metadata/catalog files
that still match this operation's candidate hashes; remove an originally absent
file only when its current hash matches the owned candidate. Withdraw only this
operation's manifest. Preserve foreign and concurrent changes.

Never restore the whole live DB over newer user progress. The operator reverses
only its exact inserted chart rows and private owned grant changes inside a
transaction; this deployment's grant ledger was empty. Foreign chart or grant
values block automatic rollback. Verify the old production18 API and service
health after a scoped restoration.

Clients that consumed `.25` require a verified complete forward repair above
`.25`; lowering the target will not repair them. Keep immutable R2 objects and
the shared original25 Worker and private-storage deny route, because staging
continues to use them. Restore matching signing/metadata behavior together.
Rejected light20/base23/full24 media is not an original-quality recovery path.
