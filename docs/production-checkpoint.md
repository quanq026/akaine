# Production checkpoint: V36 client and original-quality base25

English | [Tiếng Việt](production-checkpoint.vi.md)

This page identifies the production checkpoint represented by this source
update. It records the release promoted on 2026-10-27 and its existing bounded
emulator checks. Updating GitHub does not deploy a server, publish another
bundle, change player data or establish new runtime results.

## Identify the release

| Component | Checkpoint |
| --- | --- |
| Client build | V36, application `7.0.255`, version code `1209852` |
| Android package | `akai.arc.lmao` |
| Published APK | `AkaineXD-7.0.255-prod-v36-20261027.apk` |
| APK SHA-256 | `a8b243c59adc527e8fa1ada27a0394979234d345b2063da40fcc2fbcc2ffc5fd` |
| Ordinary production content | `7.0.255.25` |
| Production bundle alias | `7.0.255-prod-original-base25-20261027` |
| Bundle shape | Standalone full base, ten CB parts, 4,538,288,896 total download bytes |
| Catalogue at promotion | 2,543 songs and 63 packs |

The content base preserves original-quality media and Download for individual
songs. A full base is an independent installation root, not a promise that all
full song audio and charts are embedded. Game media, chart files, APKs, signing
keys and private build inputs are supplied separately. The public source
license does not grant redistribution rights for those materials.

See [the signed client release record](rebase/RELEASE_PRODUCTION_V36.md),
[production server/content deployment archive](../operations/production25-20261027/README.md)
and [bounded production runtime results](performance/20261028-production-v36-runtime.md).
Later experimental checkpoints are not part of this release.

## Build the current client

Use [the production V36 source profile](rebase/BUILD_PRODUCTION_V36.md). Its raw
core, DEX and archive input is the authentic production V9 APK from 2026-10-22:

```text
SHA-256 f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545
```

The [older fresh-XAPK chapter](guide/06-build-android-client.md) uses a different
baseline and patch set. It remains useful for that historical build, but is not
the V36 recipe. Do not replace the V9 input with a staging APK or an earlier
merged upstream baseline.

Before starting V36, obtain and verify the matching private source-build kit,
toolchain inputs, opaque loader key reference and local path map through an
authorized private channel. Keep them outside the repository. The production
profile documents candidate generation, review, sealed source controls, a clean
five-payload rebuild and signed verification. Expected final binaries are hash
controls, not compiler inputs. An APK signed with your own key will differ from
the published APK and cannot replace its signing identity for install-over
updates.

The included profile keeps the published Akaine production hosts. Using another
server still requires a separately verified native route change covering login,
aggregate, content bundle and the encrypted shared API base. Editing a server
configuration or DNS alone does not change those client routes.

## Control the production client with commands

V36 includes a local semantic bridge. Use the production host client:

```powershell
adb devices -l
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> status
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> ui list
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> bundle status
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> account status
```

Replace `<adb-serial>` with the explicit device returned by ADB. These four
commands inspect state. The production client rejects a staging bridge;
`akaine_stag.py` is the separate staging client. Use `--help` for commands for
catalogue search, song/difficulty selection, packs, characters, filters,
settings, Cloud Sync Download, recognized guides and gameplay pause controls.
Actions invoke validated native callbacks; they do not click screen coordinates
or generate notes and scores.

For an offered UI action, refresh `ui list` and activate its exact current
token. A changed scene, unknown modal or hidden input blocker can prevent the
action. After a timeout, inspect fresh state before trying again; the previous
outcome may be unknown. The [first-run guide reference](guide/07-staging-semantic-cli.md)
uses staging examples; on production use `akaine_prod.py`. Legal acceptance
remains an explicit user-operated interactive step, and Android permission
prompts remain separate OS choices. Never put credentials in shell arguments,
public issues or logs.

## Server, bot and content are separate components

The public `server/` tree starts from the twelve production-adapted siblings in
the [production25 overlay archive](../operations/production25-20261027/README.md),
with two integration exceptions. `tools/create_user_cli.py` retains the accepted
atomic `provision_account` helper used by the public bot. In
`core/config_manager.py`, five identity/secret defaults are empty: `USERNAME`,
`PASSWORD`, `SECRET_KEY`, `LINKPLAY_AUTHENTICATION` and
`LINKPLAY_TCP_SECRET_KEY`. Supply your own private configuration. The historical
archive keeps its original bytes and records its narrower two-literal
redaction; the main server tree does not claim twelve byte-identical copies.

This is a source projection, not a copy of the live deployment or its config.
Dynamic-pack and assetset-profile sample controls remain disabled until you
configure and verify the corresponding catalogue and client. Production
metadata, databases and player records are not included.

The production promotion carried dynamic pack handling with a legacy fallback,
shared additive nonconsumable grants, compatibility projections, original song
download routing and a non-cacheable content-bundle API. Catalogue, metadata,
chart constants, ownership policy, Worker signing and bot resources need their
own matching inputs; installing V36 does not update them. Current public bot
fixes remain available independently of the historical server deployment.

For a new installation, begin with [the setup guide](guide/README.md), then use
this page for the current client and production-source boundary. Use the
[content-release chapter](guide/07-build-release-content-bundle.md) for immutable
full-base build and verification principles. Its sample versions and partition
count are examples; the base25 release above has ten parts. Do not overwrite an
old bundle alias or treat a historical deployment receipt as a command to run
again against production.

## Verification limits

The [source-export validation record](production-source-export.json) binds this
public update to 114 unchanged authored source paths and the locally verified
1,063 input roles. Local tests passed 241 cases; one native guide fixture was
skipped because it requires a host C++ compiler. This export did not rebuild an
APK or repeat device runtime tests.

The recorded production checks cover login and Cloud Sync Download, pack
navigation, selected official/fan-chart gameplay, partner skill gauges, and
restart/login/cache retention on an emulator. They do not claim exhaustive
chart compatibility, a fresh physical-device test, full-song score/PTT
acceptance or a general FPS improvement. Three unfinished scene/loading lag
areas remain deferred. Worker loading, preload, ANGLE and Vulkan experiments
are not included in V36.
