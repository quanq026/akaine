# Build and release a 7.0.255 content bundle

This chapter starts with a verified full-root bundle, applies a small content
overlay, builds a new immutable release and promotes the same bytes through
staging to production. It uses `scripts/build_content_bundle.py`; the older
6.14 tools under `server/tools` do not produce the 7.0.255 release format.

Complete chapters 1 through 6 first. You also need a staging server that uses
the same server source and configuration shape as production.

Use one PowerShell window for the local build and upload sections. If you close
it, no artifact is lost; return to "Prepare a known-good source" and rerun only
the variable-setting block before continuing. Do not rerun the builder against
an existing output directory. A completed candidate is immutable, while a
failed candidate should use a new empty output path after its error is
understood.

## Understand the three names

The application version is `7.0.255`. It identifies the Android client and
does not change when you publish content.

The content version looks like `7.0.255.9`. The final number must increase for
each accepted release so the server and client can compare versions.

The alias is the filename prefix used by the manifest and every `.cb` part,
for example `7.0.255-fan-album-r1`. An alias is immutable: once uploaded, do
not put different bytes at the same R2 key.

A release contains one `<alias>.json` manifest and the number of
`<alias>_<index>.cb` files declared by `totalPartitions`. The proven Akaine
7.0.255 baseline has seven partitions. The builder reads the count from the
source manifest instead of assuming a number.

## Prepare a known-good source

Use the full-root source from the verified private resource kit. A full root
has `previousVersionNumber: null`; it can install on a clean client without a
chain of older updates.

The source directory must contain:

```text
bundle-source/
  manifest.json
  source_0.cb
  source_1.cb
  ... one source_N.cb for every declared partition
```

Choose the paths for this release in PowerShell. Keep the source, overlay and
output outside the Git repository because they contain private game data.
The content-detail key is the raw binary key file from the private kit; do not
convert it to hexadecimal or Base64 text.

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$sourceRoot = (Get-Item (Read-Host "Full path to the verified 7.0.255 bundle source")).FullName
$overlayRoot = [IO.Path]::GetFullPath((Read-Host "Full path for the new overlay directory"))
$outputRoot = [IO.Path]::GetFullPath((Read-Host "Full path for the new bundle output"))
$detailKey = (Get-Item (Read-Host "Full path to the private content-detail key")).FullName
$alias = Read-Host "New immutable alias, for example 7.0.255-my-content-r1"
$bundleVersion = Read-Host "New content version, for example 7.0.255.9"

New-Item -ItemType Directory -Force $overlayRoot | Out-Null
```

Check the source manifest before editing anything:

```powershell
$sourceManifest = Get-Content (Join-Path $sourceRoot "manifest.json") -Raw | ConvertFrom-Json

if ($sourceManifest.applicationVersionNumber -ne "7.0.255") {
    throw "The source belongs to a different application version."
}
if ($null -ne $sourceManifest.previousVersionNumber) {
    throw "The source is a delta, not a full-root bundle."
}
if ($sourceManifest.totalPartitions -lt 1) {
    throw "The source partition count is invalid."
}

$sourceManifest | Select-Object versionNumber, applicationVersionNumber, totalPartitions
```

Do not use a bundle merely because the client once downloaded it. Keep its
expected manifest SHA-256 in the private kit and compare it before every new
build.

## Create the overlay

The overlay uses paths relative to the bundle root. A file with the same path
replaces the source file; a new path is appended to the final partition.

The overlay is additive and replacement-only. Omitting a source path from the
overlay does not remove it from the bundle. To remove a song from the selector,
edit the catalogue coherently; do not expect deleting a local overlay file to
delete bytes already present in the source full root.

```text
overlay/
  songs/
    songlist
    packlist
    pack/
      1080_select_your_pack.png
    your_song/
      1080_base.jpg
      1080_base_256.jpg
      preview.ogg
    dl_your_song/
      1080_base.jpg
      1080_base_256.jpg
      preview.ogg
```

Copy the editable `songlist` and `packlist` supplied with the same source
bundle into `overlay/songs/`, then make the smallest required changes. Do not
start from catalogues belonging to another bundle version.

Each song `id` must be unique. Its `set` must be either `single` or the `id` of
an existing pack. Every `pack_parent` must also point to an existing pack. A
missing parent can pass download and checking, then crash the client before
the start screen on every later launch.

For selector display, include the jacket and preview files used by the
catalogue. A remote-download song normally keeps playable chart and audio
files in protected R2 storage; the bundle still needs its selector jackets and
preview. When a difficulty has `audioOverride: true`, include the matching
`<ratingClass>_preview.ogg` under `songs/dl_<song_id>/`.

Keep charts and full audio out of the public bundle when the server is meant
to deliver them through signed URLs. The `song_metadata.json`, private R2
allowlist and actual private objects must agree before release.

## Build the full-root candidate

Run the repository builder:

```powershell
Set-Location $repoRoot

python scripts\build_content_bundle.py `
  --source $sourceRoot `
  --overlay $overlayRoot `
  --output $outputRoot `
  --alias $alias `
  --version $bundleVersion `
  --detail-key-file $detailKey

if ($LASTEXITCODE -ne 0) {
    throw "Bundle build failed. Read the reported error before retrying."
}
```

The builder does the following work:

- verifies every source span against the manifest hash;
- rejects duplicate paths, gaps, overlaps and missing source parts;
- validates `songlist`, `packlist`, song sets and pack parents;
- preserves the source partition count and enforces a 480 MiB limit per part;
- recomputes SHA-256 for every output entry and HMAC details for changed
  protected catalogue files;
- writes into a temporary directory and publishes the output only after a
  complete second verification pass.

The output is releasable only when `ready-manifest.json` exists, says
`"status": "ready"`, and `failure.json` does not exist.

```powershell
$ready = Get-Content (Join-Path $outputRoot "ready-manifest.json") -Raw | ConvertFrom-Json
$report = Get-Content (Join-Path $outputRoot "build-report.json") -Raw | ConvertFrom-Json

if ($ready.status -ne "ready" -or -not $ready.artifact_verified) {
    throw "The candidate is not ready."
}
if (Test-Path (Join-Path $outputRoot "failure.json")) {
    throw "The candidate contains a failure receipt."
}

$report | Select-Object application_version, bundle_version, alias, entries, partition_count_preserved
$report.parts | Format-Table file, bytes, sha256
```

Do not merge partitions or convert this result into a one-part delta. The
7.0.255 client has rejected unproven delta and single-part layouts with
`-1013`.

## Publish immutable objects to staging

Create a new short-lived R2 token restricted to the asset bucket, then restore
the `akaine-r2` AWS CLI profile from chapter 5. Confirm that none of the target
keys already exists. An existing key is a reason to choose a new alias, not to
overwrite it.

```powershell
$bucket = Read-Host "R2 bucket name"
$endpoint = Read-Host "R2 S3 endpoint"
$publishFiles = @(
    Get-Item (Join-Path $outputRoot "$alias.json")
    Get-ChildItem -LiteralPath $outputRoot -Filter "$alias`_*.cb" | Sort-Object Name
)

foreach ($file in $publishFiles) {
    $existing = aws s3api list-objects-v2 `
      --bucket $bucket `
      --prefix "bundle/$($file.Name)" `
      --query "Contents[].Key" `
      --output text `
      --endpoint-url $endpoint `
      --profile akaine-r2
    if ($LASTEXITCODE -ne 0) {
        throw "Could not verify the R2 key: bundle/$($file.Name)"
    }
    if ($existing) {
        throw "R2 key already exists: bundle/$($file.Name)"
    }
}

foreach ($file in $publishFiles) {
    aws s3 cp $file.FullName "s3://$bucket/bundle/$($file.Name)" `
      --endpoint-url $endpoint `
      --profile akaine-r2 `
      --no-progress
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed: $($file.Name)"
    }
}
```

Upload failure does not require a rebuild. Inspect the failed object, then
resume the same upload. If the API returns `429`, wait for its retry window and
resume the interrupted check instead of changing the candidate.

## Verify the CDN bytes

Download the manifest and every part through the public asset hostname. This
checks R2, the custom domain and Cloudflare rather than only local files.

```powershell
$assetHost = Read-Host "Asset hostname, for example assets.example.com"
$verifyRoot = Join-Path ([IO.Path]::GetTempPath()) "akaine-bundle-$alias"
New-Item -ItemType Directory -Force $verifyRoot | Out-Null

foreach ($file in $publishFiles) {
    $download = Join-Path $verifyRoot $file.Name
    curl.exe --fail --location --output $download "https://$assetHost/bundle/$($file.Name)"
    if ($LASTEXITCODE -ne 0) {
        throw "CDN download failed: $($file.Name)"
    }
    $localHash = (Get-FileHash -Algorithm SHA256 $file.FullName).Hash
    $remoteHash = (Get-FileHash -Algorithm SHA256 $download).Hash
    if ($localHash -ne $remoteHash) {
        throw "CDN hash mismatch: $($file.Name)"
    }
}
```

Make a Range request twice and confirm that the response is `206`, reports the
correct total size and eventually becomes a Cloudflare cache `HIT`:

```powershell
$firstPart = ($publishFiles | Where-Object Name -Like "*.cb" | Select-Object -First 1).Name
curl.exe -sS -D bundle-range-1.txt -o NUL --range 0-31 "https://$assetHost/bundle/$firstPart"
curl.exe -sS -D bundle-range-2.txt -o NUL --range 0-31 "https://$assetHost/bundle/$firstPart"
Select-String -Path bundle-range-1.txt,bundle-range-2.txt -Pattern "HTTP/","Content-Range","CF-Cache-Status"
```

## Activate it on staging

Back up the staging bundle directory and configuration. Put only the new
manifest in the active bundle directory; the `.cb` files remain on R2. Set
`BUNDLE_DOWNLOAD_LINK_PREFIX` to `https://<asset-host>/bundle/`, restart the
staging service, and keep the backup path printed by your shell.

In the staging `config.py`, use the new public asset prefix and allow an older
7.0.255 content version to advance to the latest full root:

```python
BUNDLE_DOWNLOAD_LINK_PREFIX = "https://assets.example.com/bundle/"
BUNDLE_STRICT_MODE = False
FRESH_INSTALL_ONLY_BUNDLE_VERSION = ""
```

Upload the manifest, back up the active directory and activate the candidate.
The commands prompt for remote paths instead of assuming where you installed
the server:

```powershell
$sshTarget = Read-Host "SSH target, for example ec2-user@staging-api.example.com"
$serverRoot = Read-Host "Absolute server root on staging"
$serviceName = Read-Host "Staging systemd service name"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$manifestPath = Join-Path $outputRoot "$alias.json"

scp $manifestPath "${sshTarget}:/tmp/$alias.json"
if ($LASTEXITCODE -ne 0) {
    throw "Manifest upload to staging failed."
}

$deployScript = @'
set -eu
server_root="$1"
alias="$2"
stamp="$3"
service_name="$4"
bundle_dir="$server_root/database/bundle"
backup_dir="$server_root/backups/bundle-$stamp"

test -f "/tmp/$alias.json"
install -d "$server_root/backups" "$bundle_dir"
cp -a "$bundle_dir" "$backup_dir"
cp -a "$server_root/config.py" "$server_root/backups/config-$stamp.py"
find "$bundle_dir" -maxdepth 1 -type f -name '*.json' -delete
install -m 0644 "/tmp/$alias.json" "$bundle_dir/$alias.json"
systemctl restart "$service_name"
systemctl is-active --quiet "$service_name"
printf 'Bundle backup: %s\n' "$backup_dir"
'@

$deployScript | ssh $sshTarget "sudo bash -s -- '$serverRoot' '$alias' '$stamp' '$serviceName'"
if ($LASTEXITCODE -ne 0) {
    throw "Staging activation failed. Restore the printed backup before retrying."
}
```

The active server must parse `<alias>.json`, so its filename must stay aligned
with the uploaded `<alias>_<index>.cb` files. Never rename only the manifest.

Test the API with an empty content version and with the target version:

```powershell
$stagingApi = Read-Host "Staging API base URL, for example https://staging-api.example.com/t"

function Get-BundleResult([string]$contentVersion) {
    Invoke-RestMethod `
      -Uri "$stagingApi/game/content_bundle" `
      -Headers @{
        AppVersion = "7.0.255"
        ContentBundle = $contentVersion
        DeviceId = "guide-bundle-check"
      }
}

$fromEmpty = Get-BundleResult "0.0.0"
$atTarget = Get-BundleResult $bundleVersion

if ($fromEmpty.value.orderedResults.Count -ne 1) {
    throw "A clean client did not receive exactly one bundle."
}
if ($fromEmpty.value.orderedResults[0].contentBundleVersion -ne $bundleVersion) {
    throw "The server returned the wrong target version."
}
if ($fromEmpty.value.orderedResults[0].bundleParts.Count -ne $sourceManifest.totalPartitions) {
    throw "The API partition count differs from the manifest."
}
if ($atTarget.value.orderedResults.Count -ne 0) {
    throw "A current client is being told to download again."
}
```

The content-bundle API response must use `Cache-Control: private, no-store`,
and Cloudflare must report it as dynamic. Never apply the bundle asset cache
rule to the API hostname.

## Test the real client

Static hashes prove byte identity, not client compatibility. Use a clean test
account and a client pointed at staging.

1. Start with no downloaded content and record the device's current content
   version.
2. Download the candidate and let checking reach 100%.
3. Reach the title screen and main menu.
4. Open Music Play, the changed pack and several changed songs.
5. Check jacket, preview, every declared difficulty and remote download.
6. Play at least one changed chart and submit a score.
7. Close the app completely, start it again and confirm there is no second
   download, logout, bootstrap crash or loading loop.

Capture server logs and Android logcat during this test. A successful download
alone is not a pass.

## Promote the same bytes to production

Do not rebuild after staging passes. Record the SHA-256 values from
`build-report.json`, back up the production configuration and active bundle
directory, then activate the same manifest and R2 objects in production.

Repeat the API matrix against production before announcing the release. Then
run one cold download and restart test through the production domain. Revoke
the temporary R2 token and remove its local AWS profile after verification.

Keep the previous production backup until the new release has survived a cold
install, a restart and normal song downloads.

## Roll back safely

If the API check fails before any client downloads the bundle, restore the
backed-up bundle directory and configuration, restart the service, and repeat
the API matrix. Leave the immutable R2 objects in place until the incident is
understood.

Once a client has installed a higher content version, restoring the server
does not downgrade that client. Fix the candidate under a new, higher content
version and a new alias. Reusing the failed alias can leave different bytes in
Cloudflare caches around the world.

## Failure map

| Symptom | Check first |
| --- | --- |
| `-1013` while downloading or checking | Manifest span hashes, part names, part count, Range support and whether an old delta/single-part tool was used |
| Checking reaches 100%, then every launch crashes | Missing `song.set` pack, broken `pack_parent`, invalid catalogue JSON, or a startup/selector resource absent from the full root |
| Bundle downloads on every launch | Target-version API response is not empty, API caching, stale server manifest, or content version mismatch |
| Pack or song is missing | `songlist`, `packlist`, selector asset paths and server purchase/unlock data do not describe the same ID |
| Download icon never clears | `remote_dl`, `song_metadata.json`, protected allowlist and actual R2 objects disagree |
| Jacket is black or preview is silent | Required selector jacket or preview path is missing; `audioOverride` may need a difficulty-specific preview |
| CDN works in a browser but the client times out | Test full concurrent client delivery; a tiny Range probe does not prove sustained transfer |
| API returns `429` | Wait for the retry window and resume the interrupted request; do not rebuild or rename the release |

## Release checklist

- The source is a verified 7.0.255 full root.
- The content version increased and the alias has never been used.
- Catalogues pass song-pack and pack-parent checks.
- `ready-manifest.json` says the artifact is verified.
- Every R2 object was absent before upload.
- Full CDN downloads match local SHA-256 values.
- Empty-version and target-version API checks pass without caching.
- A clean staging client downloads, reaches the menu, plays changed content
  and restarts without another download or crash.
- Production uses the exact staging-tested bytes.
- Production backup and rollback paths are recorded.
- The temporary R2 credential has been revoked.
