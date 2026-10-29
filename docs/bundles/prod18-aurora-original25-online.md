# Original25 online staging release — 2026-10-26

Ordinary staging previously served the rejected lite bundle `7.0.255.20`, seven
CB parts totaling 1,984,651,176 bytes. It now serves the complete original-quality
`7.0.255.25` base, alias
`7.0.255-staging-prod18-aurora-original-base25-20261026`.

| Property | Verified value |
|---|---|
| Parent | `previousVersionNumber=null`; standalone base |
| Parts | 10 |
| CB payload | 4,532,838,207 bytes |
| Manifest | 5,450,689 bytes |
| Total download | 4,538,288,896 bytes |
| Manifest SHA-256 | `6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891` |
| Logical files | 20,903 |
| Catalog | 2,543 songs / 63 packs |

All ten CBs and the manifest passed full R2 GET and public CDN GET checks for
exact length and SHA-256. A prepublication cached 404 on the manifest was purged
for that exact URL; the subsequent GET returned the original manifest bytes.
The unchanged production18 media and accepted Aurora originals were not resized,
recompressed or reencoded. Per-song Download remains enabled. The 829 source IDs
without sufficient accepted data were not fabricated.

## Server and audio activation

- Staging assetset profiles are disabled; their historical manifests remain
  registered and do not leak into the ordinary legacy graph.
- Clients at `.0/.19/.20/.21/.22/.24` receive one complete `.25` response.
  Clients at `.25/.26` receive `orderedResults=[]`.
- Public API returns HTTP 200, `CF-Cache-Status: DYNAMIC`, and
  `Cache-Control: private, no-store`.
- Fifty original audio objects were conditionally created under fresh private
  keys. All fifty passed signed Worker full GET/hash checks. The other 6,384
  existing objects are reused; this release did not retest every body again.
- Both staging metadata files changed exactly fifty audio hashes. Files lists,
  chart hashes, encryption identities and chart objects were preserved.
- The signed staging audio route and its direct-storage denial route are
  documented in `operations/protected-assets/original25/README.md`.
- Production files, bundle manifests, services and API were checked unchanged.
  Activation did not write account, save, score or chart database rows.

The first activation stopped on a file-owner preservation error and restored its
owned changes. The successful retry uses the existing `sudo -n chown --reference`
pattern. Its backup is:

```text
/home/ec2-user/arcaea-server-test/database/backups/original25-online-20261026-retry2
```

## Native acceptance

**Bundle download, apply and cold restart passed.** The existing V36 APK installed
successfully on isolated `emulator-5580`; no new APK was built. The ordinary title
screen at bundle `0.0.0` offered 4328.04 MB. Its native bridge reported pending
`.25` and exactly 4,538,288,896 bytes. All ten downloaded CBs and the manifest
were observed at their complete lengths, totaling that exact value. No bundle
was injected by ADB.

The downloaded manifest and installed `files/cb/meta.cb` both have the expected
SHA-256. Apply produced all 20,903 logical files; the bridge reached `ready` and
the title footer showed `.25`. After a force-stop and cold launch, the same bundle
remained installed, `dltemp` was absent, and the bridge returned `ready`, no pending
versions and zero pending bytes. No repeat bundle download was observed. The
emulator's Google Games sign-in overlay was dismissed on launch; it is separate
from bundle acceptance.

The test emulator pauses automatically during the menu owner's capture lock.
`emulator-5556` and physical devices are outside this task's control. The initial
disposable AVD on D: had slow USB writes and blank streamed-install failures;
moving its userdata to C: NVMe allowed V36 installation. APKs and source bundle
media remain on D:.

An open network transfer expired during a capture pause and displayed 9804.
Ordinary Retry retained completed parts and finished the download. This did not
require a downloader or APK patch.

**Native per-song Download and playback were not tested.** The account form reports
`login_terms_required`. The repository CLI restricts `terms-accept` to an explicit
user confirmation. The user explicitly declined the login terms and selected
stopping at bundle verification. No terms were accepted, no QA account was
created and no credentials were retrieved. Official Sheriruth and Axium Crisis
metadata were separately checked equal to production; all fifty changed Aurora
audio bodies passed signed network checks. These checks do not substitute for
authenticated native playback tests. Do not describe the entire
song-download/playback acceptance as complete.

## Rollback and forward repair

1. Inspect current hashes against the receipt before restoring anything. Preserve
   concurrent changes; do not overwrite a file that no longer matches this
   release's candidate hash.
2. The backup contains original config, both metadata files, prior manifests and
   an operation receipt. Restore only this task's three files and withdraw only
   its manifest if immediate server rollback is required. Restart only
   `arcaea-server-test`; verify the old API and production preservation again.
3. Restore the matching metadata and signed prefix together. Reverting the Worker
   while staging still signs the `original25` path would break downloads. Its old
   source is the pinned accepted source above. Keep the new private-storage deny
   route while candidate objects exist, including after a Worker rollback.
4. A client that already consumed `.25` will not downgrade to `.20`. Repair such
   clients with a verified complete version above `.25` and a new immutable alias.
   Do not silently reactivate the rejected lite media as an original-quality
   recovery. Leave old immutable R2 objects intact for diagnosis and rollback.

The machine-specific operator inputs, secret references, media and full runtime
logs remain outside Git. The receipt contains sanitized identities and results.
