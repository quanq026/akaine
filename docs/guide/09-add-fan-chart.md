# Add a fan chart and place it in a pack

This chapter follows one fan chart from a source folder to a downloadable,
playable and score-enabled song in Akaine 7.0.255. It also explains how to
create a visible pack. Perform the first import on staging and use files you
have permission to host.

Complete chapters 3 through 7 first. You need the working 7.0.255 client, its
matching AKFC public key, the verified full-root bundle source, R2 upload
access, a staging server and a test account.

## What adding a fan chart changes

A fan chart is represented in several places. Each one answers a different
question:

| Place | Question it answers |
| --- | --- |
| `packlist` | Which pack exists, what is it called and which selector image does it use? |
| `songlist` | Which song exists, which pack owns it and which difficulties are visible? |
| Bundle selector assets | Which jacket and preview can Music Play display before downloading the song? |
| `song_metadata.json` | Which playable files must the client download, and what are their plaintext MD5 values? |
| Protected R2 allowlist | Which signed filenames may the Worker return for this song? |
| R2 objects | Where the actual audio and encrypted AFF bytes are stored? |
| `chart` database row | Which chart constants make submitted scores eligible for rating and PTT? |
| Server pack entitlement | Is the player allowed to see and download songs assigned to this pack? |

The flow is:

```text
source AFF, OGG and jacket
        |
        +-> songlist + packlist + selector assets -> full-root bundle
        |
        +-> AKFC-encrypted AFF + OGG -> protected R2 objects
        |
        +-> song metadata + allowlist + chart constant -> staging server
        |
        +-> client download -> gameplay -> score -> restart verification
```

Changing only `songlist` and `packlist` can make a card appear, but it cannot
make the chart downloadable, decryptable or ranked.

## Packs and difficulties are independent

A pack may contain one song. A song does not need all five difficulties.

The difficulty mapping is:

| Class | Name | Chart filename |
| --- | --- | --- |
| `0` | Past | `0.aff` |
| `1` | Present | `1.aff` |
| `2` | Future | `2.aff` |
| `3` | Beyond | `3.aff` |
| `4` | Eternal | `4.aff` |

If the source contains only FTR, declare only class `2` and provide `2.aff`.
Do not create empty PST or PRS entries to make the song look complete. Missing
difficulties remain absent from `songlist` and use `-1` as their database
constant.

For a first custom chart, prefer FTR or ETR. New BYD IDs require an additional
native active-state registry change; adding `3.aff` and a class-3 row alone can
produce a missing or unclickable BYD tile.

## Decide whether a new pack is necessary

The released 7.0.255 client accepts at most 62 pack entitlements. Akaine already
uses that safe capacity. Adding a 63rd visible entitlement can break the account
response even if `packlist` contains the new pack.

The simplest choice is to place new charts in the existing `xd_fan_album` pack.
Creating another pack is appropriate only when you deliberately allocate one
of the 62 visible slots. A new pack therefore needs all of these changes:

1. add the pack object to bundle `packlist`;
2. add its selector cover to the bundle;
3. assign at least one song to the pack;
4. add the pack to the server's custom/free entitlement configuration;
5. include it in the 7.0.255 client pack projection while removing or hiding a
   custom pack that no longer needs a visible slot;
6. confirm the final client pack payload is no longer than 62 entries.

Do not remove an official pack merely to make room. For a clean custom setup,
replace an old custom pack slot or reuse `xd_fan_album`.

The examples below use a new pack named `my_fan_pack` and one FTR song named
`my_fan_song`. Replace both identifiers consistently.

## Step 1: create an isolated import folder

Open Windows PowerShell:

```powershell
$privateRoot = [Environment]::GetEnvironmentVariable("AKAINE_PRIVATE_ROOT", "User")
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = Join-Path $privateRoot "fan-import-$stamp"
$source = Join-Path $work "source"
$overlay = Join-Path $work "overlay"
$protected = Join-Path $work "protected"
$receipts = Join-Path $work "receipts"

New-Item -ItemType Directory -Force $source, $overlay, $protected, $receipts | Out-Null
Get-Item $python, $source, $overlay, $protected, $receipts |
  Select-Object FullName
```

`$source` keeps untouched input files. `$overlay` mirrors bundle-relative paths.
`$protected` receives files for private R2. `$receipts` records hashes and
encryption identity. Keeping this work outside Git prevents accidental asset
commits.

Copy the source archive or folder into `$source`. Do not edit the only copy
supplied by the chart author.

## Step 2: inventory the source

The minimum playable input for a single FTR chart is:

```text
2.aff
base.ogg
a square jacket image
```

A provided `preview.ogg` is useful but can be generated. List every input and
record its hash:

```powershell
Get-ChildItem -LiteralPath $source -Recurse -File |
  Sort-Object FullName |
  Select-Object FullName, Length

Get-ChildItem -LiteralPath $source -Recurse -File |
  Get-FileHash -Algorithm SHA256 |
  Format-Table Path, Hash -AutoSize
```

Open the AFF in a text editor. It must contain an `AudioOffset:` line, a line
with `-`, timing data and actual chart events. A tiny placeholder or metadata
file renamed to `.aff` is not a playable chart.

Install FFmpeg once if `ffprobe` is unavailable:

```powershell
ffprobe -version
if ($LASTEXITCODE -ne 0) {
  winget install --exact --id Gyan.FFmpeg
  if ($LASTEXITCODE -ne 0) { throw "FFmpeg installation failed." }
  throw "Close and reopen PowerShell, reload the variables from step 1, then continue."
}
```

Inspect the audio instead of trusting its extension:

```powershell
$audioSource = Get-Item (Join-Path $source "base.ogg")
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,duration `
  -of default=noprint_wrappers=1 $audioSource.FullName
if ($LASTEXITCODE -ne 0) { throw "The source audio could not be decoded." }
```

The codec should be Vorbis, with a positive duration. MP3 bytes renamed to
`.ogg`, attached video or broken timestamps should be normalized in the next
step.

## Step 3: choose stable IDs and an unused index

Use lowercase ASCII letters, digits and underscores for IDs. Do not change a
song ID after players have scores because the database uses it as the score
identity.

```powershell
$packId = "my_fan_pack"
$songId = "my_fan_song"
$chartFile = "2.aff"

if ($packId -notmatch '^[a-z0-9_]+$' -or $songId -notmatch '^[a-z0-9_]+$') {
  throw "Pack and song IDs must use lowercase ASCII letters, digits, and underscores."
}

$songlistPath = Read-Host "Full path to the editable songlist from the verified bundle source"
$packlistPath = Read-Host "Full path to the editable packlist from the same bundle source"
$songlist = Get-Content $songlistPath -Raw | ConvertFrom-Json
$packlist = Get-Content $packlistPath -Raw | ConvertFrom-Json

if ($songlist.songs.id -contains $songId) { throw "Song ID already exists." }
if ($packlist.packs.id -contains $packId) { throw "Pack ID already exists." }

$usedIndexes = @($songlist.songs | ForEach-Object { [int]$_.idx })
$songIndex = 2000
while ($usedIndexes -contains $songIndex) { $songIndex++ }
$songDate = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
"Reserved song idx: $songIndex"
"Use song date: $songDate"
```

The example starts at `2000` to stay away from the current official and XD fan
ranges. A high number is a local convention, not a permanent guarantee; the
loop still checks the active catalogue for collision.

Copy both editable catalogues into the overlay:

```powershell
$overlaySongs = Join-Path $overlay "songs"
New-Item -ItemType Directory -Force $overlaySongs | Out-Null
Copy-Item $songlistPath (Join-Path $overlaySongs "songlist")
Copy-Item $packlistPath (Join-Path $overlaySongs "packlist")
```

## Step 4: add the pack to `packlist`

Open the overlay copy:

```powershell
notepad (Join-Path $overlaySongs "packlist")
```

Append this object inside the `packs` array, adding the required comma before
it when another object precedes it:

```json
{
  "id": "my_fan_pack",
  "section": "variety",
  "plus_character": -1,
  "custom_banner": true,
  "is_extend_pack": true,
  "name_localized": {
    "en": "My Fan Pack"
  },
  "description_localized": {
    "en": "A community fan-chart collection."
  }
}
```

`id` is the internal relationship key. `name_localized` and
`description_localized` are displayed to the player. `custom_banner` tells the
selector to use the custom pack image. `section: variety` places the pack with
the variety/collaboration group used by the verified fan pack.

Validate the edited JSON immediately:

```powershell
& $python -m json.tool (Join-Path $overlaySongs "packlist") > $null
if ($LASTEXITCODE -ne 0) { throw "packlist JSON is invalid." }
```

Prepare a `374 x 750` RGB PNG and place it at:

```powershell
$packCover = Get-Item (Read-Host "Full path to the prepared 374x750 pack cover PNG")
$packAssetFolder = Join-Path $overlaySongs "pack"
New-Item -ItemType Directory -Force $packAssetFolder | Out-Null
Copy-Item $packCover.FullName (Join-Path $packAssetFolder "1080_select_my_fan_pack.png")

& $python -c "from PIL import Image; import sys; im=Image.open(sys.argv[1]); assert im.size==(374,750), im.size; assert im.mode in ('RGB','RGBA'), im.mode; print(im.size, im.mode)" (Join-Path $packAssetFolder "1080_select_my_fan_pack.png")
if ($LASTEXITCODE -ne 0) { throw "Pack cover dimensions or color mode are invalid." }
```

The displayed title is drawn into the image itself when you want styled pack
text. The JSON name remains necessary for labels and accessibility.

## Step 5: add the song to `songlist`

Open the overlay songlist:

```powershell
notepad (Join-Path $overlaySongs "songlist")
```

Append a song object inside the `songs` array. This FTR-only example does not
invent the other four difficulties:

```json
{
  "idx": 2000,
  "id": "my_fan_song",
  "title_localized": {
    "en": "My Fan Song"
  },
  "artist": "Artist name",
  "bpm": "180",
  "bpm_base": 180,
  "set": "my_fan_pack",
  "purchase": "my_fan_pack",
  "audioPreview": 30000,
  "audioPreviewEnd": 50000,
  "side": 0,
  "bg": "base_light",
  "date": 1789491600,
  "version": "7.0",
  "remote_dl": true,
  "world_unlock": false,
  "difficulties": [
    {
      "ratingClass": 2,
      "chartDesigner": "Charter name",
      "jacketDesigner": "Illustrator name",
      "rating": 10,
      "ratingPlus": false
    }
  ]
}
```

Replace `idx` with `$songIndex`, and replace the displayed metadata with the
real credits. The important relationships are:

- `set` matches the new `packlist.id`;
- `purchase` matches the server entitlement used for the pack;
- `remote_dl: true` keeps playable AFF/OGG out of the public bundle;
- `ratingClass: 2` maps to `2.aff`;
- `rating` and `ratingPlus` control the displayed difficulty label, not the
  exact rating constant used for PTT;
- `date` is the UTC Unix timestamp printed as `$songDate` in step 3;
- `audioPreview` values are millisecond positions in the full song.

Validate uniqueness and references:

```powershell
$editedSonglist = Get-Content (Join-Path $overlaySongs "songlist") -Raw | ConvertFrom-Json
$editedPacklist = Get-Content (Join-Path $overlaySongs "packlist") -Raw | ConvertFrom-Json
$songIds = @($editedSonglist.songs.id)
$songIndexes = @($editedSonglist.songs.idx | ForEach-Object { [int]$_ })
$packIds = @($editedPacklist.packs.id)

if ($songIds.Count -ne @($songIds | Sort-Object -Unique).Count) { throw "Duplicate song ID." }
if ($songIndexes.Count -ne @($songIndexes | Sort-Object -Unique).Count) { throw "Duplicate song idx." }
if ($packIds.Count -ne @($packIds | Sort-Object -Unique).Count) { throw "Duplicate pack ID." }
if ($packIds -notcontains $packId) { throw "New pack is absent from packlist." }
$addedSong = @($editedSonglist.songs | Where-Object id -eq $songId)
if ($addedSong.Count -ne 1 -or $addedSong[0].set -ne $packId) { throw "Song-to-pack relationship is invalid." }
```

## Step 6: normalize audio and create the preview

Create one clean Vorbis file for gameplay:

```powershell
$audio = Join-Path $protected "base.ogg"
ffmpeg -hide_banner -y -fflags +genpts -i $audioSource.FullName `
  -map 0:a:0 -vn -sn -dn -map_metadata -1 `
  -af "aresample=async=1:first_pts=0,asetpts=N/SR/TB" `
  -c:a libvorbis -ar 44100 -ac 2 -q:a 4 $audio
if ($LASTEXITCODE -ne 0) { throw "Gameplay audio normalization failed." }
```

`-map 0:a:0` selects the first audio stream. The `-vn/-sn/-dn` flags remove
video, subtitles and data. The audio filter rebuilds timestamps from zero.
The final options produce stereo 44.1 kHz Vorbis.

Create a 20-second selector preview matching the example's 30–50 second
window:

```powershell
$preview = Join-Path $work "preview.ogg"
ffmpeg -hide_banner -y -ss 30 -t 20 -i $audio `
  -map 0:a:0 -vn -sn -dn -map_metadata -1 `
  -c:a libvorbis -ar 44100 -ac 2 -q:a 3 $preview
if ($LASTEXITCODE -ne 0) { throw "Preview generation failed." }

ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 $preview
```

If you choose a different preview window, update both `audioPreview` and
`audioPreviewEnd` in `songlist`. Listen to the output before continuing.

## Step 7: prepare jackets and selector folders

Choose a square jacket image. The verified 1080 layout uses `768 x 768` for the
large jacket and `384 x 384` for the `_256` variant. Use an image editor to
crop the source to a square before resizing; do not stretch a rectangular
image.

Place the files in both selector paths for compatibility:

```text
overlay/songs/my_fan_song/1080_base.jpg
overlay/songs/my_fan_song/1080_base_256.jpg
overlay/songs/my_fan_song/preview.ogg
overlay/songs/dl_my_fan_song/1080_base.jpg
overlay/songs/dl_my_fan_song/1080_base_256.jpg
overlay/songs/dl_my_fan_song/preview.ogg
```

Create the folders and copy the prepared assets:

```powershell
$jacketLarge = Get-Item (Read-Host "Full path to the prepared 768x768 JPEG")
$jacketSmall = Get-Item (Read-Host "Full path to the prepared 384x384 JPEG")
$selectorA = Join-Path $overlaySongs $songId
$selectorB = Join-Path $overlaySongs "dl_$songId"
New-Item -ItemType Directory -Force $selectorA, $selectorB | Out-Null

foreach ($folder in @($selectorA, $selectorB)) {
  Copy-Item $jacketLarge.FullName (Join-Path $folder "1080_base.jpg")
  Copy-Item $jacketSmall.FullName (Join-Path $folder "1080_base_256.jpg")
  Copy-Item $preview (Join-Path $folder "preview.ogg")
}

& $python -c "from PIL import Image; import sys; expected=[(768,768),(384,384)]; actual=[Image.open(p).size for p in sys.argv[1:]]; assert actual==expected,(actual,expected); print(actual)" $jacketLarge.FullName $jacketSmall.FullName
if ($LASTEXITCODE -ne 0) { throw "Jacket dimensions are invalid." }
```

If a difficulty uses `audioOverride: true`, also create the matching
`<ratingClass>_preview.ogg` in `songs/dl_<song_id>/`. It is separate from the
downloadable `<ratingClass>.ogg`.

## Step 8: encrypt each AFF with AKFC

Use the public key paired with the private key embedded by chapter 6. The
encryption tool never needs the private key.

```powershell
$affSource = Get-Item (Join-Path $source $chartFile)
$akfcPublicKey = Get-Item (Read-Host "Full path to the AKFC public key used by this client")
$encryptedAff = Join-Path $protected $chartFile
$akfcReceipt = Join-Path $receipts "$songId-$chartFile.json"

Set-Location $repoRoot
& $python scripts\encrypt_akfc_aff.py `
  --source $affSource.FullName `
  --public-key $akfcPublicKey.FullName `
  --song-id $songId `
  --file-name $chartFile `
  --output $encryptedAff `
  --receipt $akfcReceipt
if ($LASTEXITCODE -ne 0) { throw "AKFC encryption failed." }

$akfcReport = Get-Content $akfcReceipt -Raw | ConvertFrom-Json
if ($akfcReport.status -ne "verified" -or $akfcReport.container.magic -ne "AKFC") {
  throw "AKFC receipt is not verified."
}
$akfcReport
```

The container identity includes release ID, song ID, filename and key epoch.
The loader reconstructs the song ID and filename from the downloaded path, so
renaming either value after encryption makes decryption fail.

The receipt contains two different hashes:

- `source.md5` describes plaintext AFF and is used by `song_metadata.json`;
- `container.sha256` describes encrypted R2 bytes and proves upload identity.

Never upload the raw AFF as a fallback when the chart is intended to be
protected.

## Step 9: update metadata and the protected allowlist

Copy the current staging `song_metadata.json` and
`private/asset-manifest.json` into the work folder. Back up both before editing.

For the FTR example, add this member to `song_metadata.json`:

```json
"my_fan_song": {
  "files": [
    "2.aff",
    "base.ogg"
  ],
  "hashes": {
    "2.aff": "PLAINTEXT_AFF_MD5_FROM_AKFC_RECEIPT",
    "base.ogg": "NORMALIZED_AUDIO_MD5"
  }
}
```

Calculate the audio MD5:

```powershell
$audioMd5 = (Get-FileHash -Algorithm MD5 $audio).Hash.ToLowerInvariant()
$affMd5 = $akfcReport.source.md5
"AFF plaintext MD5: $affMd5"
"Audio MD5: $audioMd5"
```

The AFF value is the plaintext MD5, not the encrypted container hash. The
client validates the chart it will play after AKFC decryption.

Add this member to `asset-manifest.json`:

```json
"my_fan_song": [
  "2.aff",
  "base.ogg"
]
```

The Worker treats a song row as a complete allowlist. Every file listed in
metadata for a protected song must also be present in this row and in private
R2 storage.

Validate both JSON files:

```powershell
$metadataPath = Get-Item (Read-Host "Full path to the edited staging song_metadata.json")
$allowlistPath = Get-Item (Read-Host "Full path to the edited asset-manifest.json")
& $python -m json.tool $metadataPath.FullName > $null
if ($LASTEXITCODE -ne 0) { throw "song_metadata.json is invalid." }
& $python -m json.tool $allowlistPath.FullName > $null
if ($LASTEXITCODE -ne 0) { throw "asset-manifest.json is invalid." }
```

## Step 10: upload protected objects to staging R2

Use the short-lived `akaine-r2` profile from chapter 5. Upload objects first
and the allowlist last, so the Worker never authorizes a filename that is not
present yet.

```powershell
$bucket = Read-Host "Staging R2 bucket name"
$endpoint = Read-Host "R2 S3 endpoint"

aws s3 cp $encryptedAff "s3://$bucket/private/songs/$songId/$chartFile" `
  --endpoint-url $endpoint --profile akaine-r2 --no-progress
if ($LASTEXITCODE -ne 0) { throw "Encrypted AFF upload failed." }

aws s3 cp $audio "s3://$bucket/private/songs/$songId/base.ogg" `
  --endpoint-url $endpoint --profile akaine-r2 --no-progress
if ($LASTEXITCODE -ne 0) { throw "Audio upload failed." }

aws s3 cp $allowlistPath.FullName "s3://$bucket/private/asset-manifest.json" `
  --endpoint-url $endpoint --profile akaine-r2 --no-progress
if ($LASTEXITCODE -ne 0) { throw "Protected allowlist upload failed." }
```

The Worker refreshes its allowlist within 60 seconds. Direct private and
unsigned protected URLs must still return `403`; the staging server will create
the signed URLs used for the positive test.

## Step 11: configure the staging server for the pack

For a protected fan song, staging configuration needs:

```python
ASSET_SIGNING_ENABLED = True
ASSET_SIGNED_PREFIX = "https://assets.example.com/protected/songs/"
ASSET_SIGNING_PROTECT_ALL_SONGS = False
ASSET_SIGNING_SONG_IDS = ["my_fan_song"]

CUSTOM_PACK_UMBRELLA = "my_fan_pack"
CUSTOM_PACK_IDS = ["my_fan_pack"]
CLIENT_VISIBLE_CUSTOM_PACK_IDS = ["my_fan_pack"]
FREE_PACKS = ["my_fan_pack"]
CLIENT_PACK_LIMIT = 62
```

Preserve existing entries when the lists already contain other songs or packs.
`FREE_PACKS` is the simplest staging entitlement: every account receives the
pack without creating purchase rows.

The current 7.0.255 response also has an explicit 62-entry projection in
`server/server/user.py`. Locate `CLIENT_PACK_PROJECTION_7_0_255`, replace an
obsolete custom-pack slot with `my_fan_pack`, and keep the tuple at 62 entries.
Do not append a 63rd item and do not remove an official pack casually.

The server needs the same edited songlist used by the bundle at
`database/songs/songlist`. It also needs the edited
`database/song_metadata.json`. Back up both staging files, install the new
copies, preserve the service user's ownership, then restart only staging.

Static success means the service becomes active and its HTTP readiness check
passes. It does not yet prove the client can download the song.

## Step 12: add the chart constant

Open the staging administrator page:

```text
https://api.example.com/web/login
```

Sign in with the private web-admin credentials, open **Change song**, and add:

| Field | FTR-only example |
| --- | --- |
| Song ID | `my_fan_song` |
| English name | `My Fan Song` |
| PST constant | `-1` |
| PRS constant | `-1` |
| FTR constant | the real chart constant, for example `10.4` |
| BYD constant | `-1` |
| ETR constant | `-1` |

The displayed `rating: 10` from `songlist` and a rating constant such as `10.4`
are different values. The server stores `10.4` as integer `104`. Missing
difficulties stay `-1` so they cannot create ranked score records.

This row makes a real FTR score eligible for rating calculation. Total PTT
changes only when that score is strong enough to enter the player's B30 or
recent plays.

## Step 13: build and activate the full-root bundle

Use `$overlay` as the overlay input in chapter 7. The bundle must contain:

```text
songs/songlist
songs/packlist
songs/pack/1080_select_my_fan_pack.png
songs/my_fan_song/1080_base.jpg
songs/my_fan_song/1080_base_256.jpg
songs/my_fan_song/preview.ogg
songs/dl_my_fan_song/1080_base.jpg
songs/dl_my_fan_song/1080_base_256.jpg
songs/dl_my_fan_song/preview.ogg
```

The full `base.ogg` and encrypted `2.aff` are remote protected files and do not
belong in this public bundle. Build with a new content version and immutable
alias, verify every part through the CDN, then activate it only on staging.

## Step 14: verify the complete staging contract

Use a clean test account. If account entitlements changed, sign in again and
run **Cloud Sync → Download** before judging pack visibility.

Test in this order:

1. A cold client receives the new bundle once.
2. The new pack has the expected cover and opens with at least one card.
3. The song shows only the declared FTR difficulty.
4. Jacket and preview render without FMOD errors.
5. Download finishes and the icon disappears.
6. The DownloadList contains exactly `2.aff` and `base.ogg` with the expected
   plaintext MD5 values.
7. The signed URLs return the encrypted AFF and normalized OGG; a direct
   `/private/` request and an unsigned `/protected/` request still return `403`.
8. The chart reaches gameplay and audio remains synchronized.
9. A legitimate play creates a score row with positive play rating.
10. After force-stop and reopen, the account, pack, download state and gameplay
    still work without a second bundle or song download.

Pack visibility alone is not acceptance. Download, gameplay, score and restart
are separate gates.

## Common mistakes

| Symptom | Likely cause |
| --- | --- |
| Pack is absent | It is missing from the 62-entry client projection or entitlement configuration. |
| Pack opens with zero cards | Song `set` does not match pack ID, or the final bundle contains the wrong songlist. |
| Song shows fake difficulties | Empty or duplicated difficulty rows were added to songlist. |
| BYD tile is absent or unclickable | New class-3 ID is not accepted by the native registry. Use FTR/ETR or make a separately verified client patch. |
| Black jacket or silent preview | Selector files are missing from `songs/<id>` or `songs/dl_<id>`. |
| Download reports success but icon returns | Metadata, protected allowlist and actual object set disagree. |
| Protected request returns `403` after upload | Wait for the 60-second allowlist TTL, then check exact song ID and filename. |
| AKFC chart downloads but will not start | It was encrypted with another key, song ID or filename, or raw/ciphertext hashes were confused. |
| Gameplay crashes after a few seconds | Probe OGG timestamps and inspect unsupported AFF events or effect filenames. |
| Score saves with rating `0` | The selected class has no positive chart constant. |
| Positive play rating but total PTT stays unchanged | The play did not enter that player's B30/recent set. |

## Before production

- You have permission to host every supplied asset.
- Source hashes and author credits are recorded.
- Song and pack IDs are stable and unique.
- The pack entitlement payload remains at or below 62 entries.
- Only real difficulties are visible and ranked.
- AKFC receipt identity matches the final song ID and filename.
- Metadata plaintext hashes match the source AFF and normalized audio.
- Protected allowlist exactly covers the metadata file set.
- The staging bundle, server metadata and R2 objects use the same IDs.
- Cold download, gameplay, score and restart all pass.
- Production backups and a new immutable bundle alias are ready.

Promote the exact staging-tested files. Do not rebuild, re-encrypt or rename the
chart between staging and production; any of those actions creates a different
artifact that needs the gates again.
