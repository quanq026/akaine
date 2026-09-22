# Thêm fan chart và đặt nó vào một pack

[English](../09-add-fan-chart.md) | Tiếng Việt

Chương này đưa một fan chart từ source folder thành bài có thể tải, chơi và lưu score
trong Akaine 7.0.255. Chương cũng giải thích cách tạo một pack hiển thị được. Hãy thực
hiện lần import đầu tiên trên staging và chỉ dùng asset mà bạn có quyền host.

Hoàn thành chương 3 đến 7 trước. Bạn cần client 7.0.255 hoạt động, AKFC public key tương
ứng, verified full-root bundle source, quyền upload R2, staging server và test account.

## Việc thêm fan chart thay đổi những gì

Một fan chart được mô tả ở nhiều nơi. Mỗi nơi trả lời một câu hỏi khác nhau:

| Nơi | Câu hỏi nó trả lời |
| --- | --- |
| `packlist` | Pack nào tồn tại, tên gì và dùng selector image nào? |
| `songlist` | Bài nào tồn tại, thuộc pack nào và difficulty nào hiển thị? |
| Bundle selector asset | Jacket và preview nào Music Play dùng trước khi tải bài? |
| `song_metadata.json` | Client phải tải playable file nào và plaintext MD5 của chúng là gì? |
| Protected R2 allowlist | Worker được trả signed filename nào cho bài này? |
| R2 object | Audio thật và AFF đã mã hóa được lưu ở đâu? |
| Database row `chart` | Chart constant nào giúp submitted score đủ điều kiện tính rating và PTT? |
| Server pack entitlement | Người chơi có được thấy và tải bài thuộc pack này không? |

Flow hoàn chỉnh là:

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

Chỉ đổi `songlist` và `packlist` có thể làm card xuất hiện, nhưng không thể khiến chart
tải được, giải mã được hoặc được xếp hạng.

## Pack và difficulty độc lập với nhau

Một pack có thể chỉ chứa một bài. Một bài không cần có đủ năm difficulty.

Difficulty mapping là:

| Class | Tên | Chart filename |
| --- | --- | --- |
| `0` | Past | `0.aff` |
| `1` | Present | `1.aff` |
| `2` | Future | `2.aff` |
| `3` | Beyond | `3.aff` |
| `4` | Eternal | `4.aff` |

Nếu source chỉ có FTR, chỉ khai báo class `2` và cung cấp `2.aff`. Không tạo PST hoặc
PRS rỗng để bài trông đầy đủ. Difficulty bị thiếu không xuất hiện trong `songlist` và
dùng database constant `-1`.

Với custom chart đầu tiên, hãy ưu tiên FTR hoặc ETR. BYD ID mới cần thêm thay đổi ở
native active-state registry; chỉ thêm `3.aff` và class-3 row có thể tạo BYD tile bị
thiếu hoặc không bấm được.

## Quyết định có thật sự cần pack mới không

Client 7.0.255 đã release nhận tối đa 62 pack entitlement. Akaine hiện đã dùng hết safe
capacity này. Thêm entitlement hiển thị thứ 63 có thể làm account response lỗi dù
`packlist` chứa pack mới.

Cách đơn giản nhất là đặt chart mới vào pack `xd_fan_album` hiện có. Chỉ nên tạo pack
khác khi bạn chủ động cấp cho nó một trong 62 visible slot. Vì vậy pack mới cần đủ các
thay đổi sau:

1. thêm pack object vào `packlist` của bundle;
2. thêm selector cover của pack vào bundle;
3. gán ít nhất một bài cho pack;
4. thêm pack vào custom/free entitlement configuration của server;
5. đưa nó vào client pack projection 7.0.255, đồng thời bỏ hoặc ẩn một custom pack không
   còn cần visible slot;
6. xác nhận client pack payload cuối không dài quá 62 entry.

Không bỏ official pack chỉ để lấy chỗ. Với custom setup sạch, hãy thay một custom pack
cũ hoặc dùng lại `xd_fan_album`.

Ví dụ dưới đây dùng pack mới `my_fan_pack` và một bài FTR tên `my_fan_song`. Hãy thay
cả hai ID một cách thống nhất.

## Bước 1: tạo import folder cô lập

Mở Windows PowerShell:

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

`$source` giữ input chưa chỉnh sửa. `$overlay` phản chiếu bundle-relative path.
`$protected` nhận file dành cho private R2. `$receipts` ghi hash và encryption identity.
Giữ work này ngoài Git giúp tránh commit nhầm asset.

Copy source archive hoặc folder vào `$source`. Không sửa bản duy nhất do chart author
cung cấp.

## Bước 2: kiểm kê source

Input tối thiểu để chơi một FTR chart là:

```text
2.aff
base.ogg
a square jacket image
```

`preview.ogg` do source cung cấp là tốt nhất nhưng cũng có thể tạo. Liệt kê mọi input và
ghi hash:

```powershell
Get-ChildItem -LiteralPath $source -Recurse -File |
  Sort-Object FullName |
  Select-Object FullName, Length

Get-ChildItem -LiteralPath $source -Recurse -File |
  Get-FileHash -Algorithm SHA256 |
  Format-Table Path, Hash -AutoSize
```

Mở AFF trong text editor. Nó phải có dòng `AudioOffset:`, một dòng chứa `-`, timing data
và chart event thật. Placeholder rất nhỏ hoặc metadata file bị đổi tên thành `.aff`
không phải playable chart.

Cài FFmpeg một lần nếu `ffprobe` chưa có:

```powershell
ffprobe -version
if ($LASTEXITCODE -ne 0) {
  winget install --exact --id Gyan.FFmpeg
  if ($LASTEXITCODE -ne 0) { throw "FFmpeg installation failed." }
  throw "Close and reopen PowerShell, reload the variables from step 1, then continue."
}
```

Kiểm tra audio thay vì tin file extension:

```powershell
$audioSource = Get-Item (Join-Path $source "base.ogg")
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,duration `
  -of default=noprint_wrappers=1 $audioSource.FullName
if ($LASTEXITCODE -ne 0) { throw "The source audio could not be decoded." }
```

Codec nên là Vorbis và duration phải dương. MP3 byte bị đổi đuôi thành `.ogg`, attached
video hoặc timestamp hỏng cần được normalize ở bước sau.

## Bước 3: chọn ID ổn định và index chưa dùng

ID chỉ dùng chữ ASCII thường, số và dấu gạch dưới. Không đổi song ID sau khi người chơi
đã có score vì database dùng nó làm score identity.

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

Ví dụ bắt đầu từ `2000` để tránh current official range và XD fan range. Số cao chỉ là
quy ước local, không bảo đảm vĩnh viễn; vòng lặp vẫn kiểm tra active catalogue để tránh
collision.

Copy hai editable catalogue vào overlay:

```powershell
$overlaySongs = Join-Path $overlay "songs"
New-Item -ItemType Directory -Force $overlaySongs | Out-Null
Copy-Item $songlistPath (Join-Path $overlaySongs "songlist")
Copy-Item $packlistPath (Join-Path $overlaySongs "packlist")
```

## Bước 4: thêm pack vào `packlist`

Mở bản copy trong overlay:

```powershell
notepad (Join-Path $overlaySongs "packlist")
```

Thêm object này vào trong array `packs`, đồng thời thêm dấu phẩy cần thiết trước nó nếu
phía trước còn object khác:

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

`id` là relationship key nội bộ. `name_localized` và `description_localized` được hiển
thị cho người chơi. `custom_banner` yêu cầu selector dùng custom pack image.
`section: variety` đặt pack cùng nhóm variety/collaboration mà verified fan pack đang
dùng.

Xác minh JSON đã chỉnh ngay lập tức:

```powershell
& $python -m json.tool (Join-Path $overlaySongs "packlist") > $null
if ($LASTEXITCODE -ne 0) { throw "packlist JSON is invalid." }
```

Chuẩn bị PNG RGB kích thước `374 x 750` và đặt tại:

```powershell
$packCover = Get-Item (Read-Host "Full path to the prepared 374x750 pack cover PNG")
$packAssetFolder = Join-Path $overlaySongs "pack"
New-Item -ItemType Directory -Force $packAssetFolder | Out-Null
Copy-Item $packCover.FullName (Join-Path $packAssetFolder "1080_select_my_fan_pack.png")

& $python -c "from PIL import Image; import sys; im=Image.open(sys.argv[1]); assert im.size==(374,750), im.size; assert im.mode in ('RGB','RGBA'), im.mode; print(im.size, im.mode)" (Join-Path $packAssetFolder "1080_select_my_fan_pack.png")
if ($LASTEXITCODE -ne 0) { throw "Pack cover dimensions or color mode are invalid." }
```

Nếu muốn styled pack text, chữ hiển thị được vẽ trực tiếp vào image. JSON name vẫn cần
cho label và accessibility.

## Bước 5: thêm bài vào `songlist`

Mở songlist trong overlay:

```powershell
notepad (Join-Path $overlaySongs "songlist")
```

Thêm song object vào trong array `songs`. Ví dụ chỉ có FTR này không bịa thêm bốn
difficulty còn lại:

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

Thay `idx` bằng `$songIndex`, rồi thay displayed metadata bằng credit thật. Các quan hệ
quan trọng là:

- `set` khớp `packlist.id` mới;
- `purchase` khớp server entitlement của pack;
- `remote_dl: true` giữ playable AFF/OGG ngoài public bundle;
- `ratingClass: 2` ánh xạ tới `2.aff`;
- `rating` và `ratingPlus` điều khiển difficulty label hiển thị, không phải rating
  constant chính xác dùng cho PTT;
- `date` là UTC Unix timestamp được in dưới tên `$songDate` ở bước 3;
- giá trị `audioPreview` là vị trí mili giây trong full song.

Kiểm tra uniqueness và reference:

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

## Bước 6: normalize audio và tạo preview

Tạo một Vorbis file sạch cho gameplay:

```powershell
$audio = Join-Path $protected "base.ogg"
ffmpeg -hide_banner -y -fflags +genpts -i $audioSource.FullName `
  -map 0:a:0 -vn -sn -dn -map_metadata -1 `
  -af "aresample=async=1:first_pts=0,asetpts=N/SR/TB" `
  -c:a libvorbis -ar 44100 -ac 2 -q:a 4 $audio
if ($LASTEXITCODE -ne 0) { throw "Gameplay audio normalization failed." }
```

`-map 0:a:0` chọn audio stream đầu tiên. Các flag `-vn/-sn/-dn` bỏ video, subtitle và
data. Audio filter tạo lại timestamp từ zero. Các option cuối tạo stereo Vorbis 44,1
kHz.

Tạo selector preview dài 20 giây khớp window 30–50 giây trong ví dụ:

```powershell
$preview = Join-Path $work "preview.ogg"
ffmpeg -hide_banner -y -ss 30 -t 20 -i $audio `
  -map 0:a:0 -vn -sn -dn -map_metadata -1 `
  -c:a libvorbis -ar 44100 -ac 2 -q:a 3 $preview
if ($LASTEXITCODE -ne 0) { throw "Preview generation failed." }

ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 $preview
```

Nếu chọn preview window khác, hãy cập nhật cả `audioPreview` và `audioPreviewEnd` trong
`songlist`. Nghe output trước khi tiếp tục.

## Bước 7: chuẩn bị jacket và selector folder

Chọn một jacket image vuông. Verified 1080 layout dùng `768 x 768` cho jacket lớn và
`384 x 384` cho variant `_256`. Dùng image editor crop source thành hình vuông trước
khi resize; không kéo giãn hình chữ nhật.

Đặt file trong cả hai selector path để tương thích:

```text
overlay/songs/my_fan_song/1080_base.jpg
overlay/songs/my_fan_song/1080_base_256.jpg
overlay/songs/my_fan_song/preview.ogg
overlay/songs/dl_my_fan_song/1080_base.jpg
overlay/songs/dl_my_fan_song/1080_base_256.jpg
overlay/songs/dl_my_fan_song/preview.ogg
```

Tạo folder và copy asset đã chuẩn bị:

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

Nếu difficulty dùng `audioOverride: true`, hãy tạo thêm
`<ratingClass>_preview.ogg` tương ứng trong `songs/dl_<song_id>/`. Nó tách biệt với
downloadable `<ratingClass>.ogg`.

## Bước 8: mã hóa từng AFF bằng AKFC

Dùng public key ghép cặp với private key đã nhúng ở chương 6. Encryption tool không bao
giờ cần private key.

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

Container identity gồm release ID, song ID, filename và key epoch. Loader dựng lại song
ID cùng filename từ downloaded path, nên đổi một trong hai sau khi encrypt sẽ làm
decrypt lỗi.

Receipt có hai hash khác nhau:

- `source.md5` mô tả plaintext AFF và được dùng trong `song_metadata.json`;
- `container.sha256` mô tả encrypted R2 byte và chứng minh upload identity.

Không upload raw AFF làm fallback khi chart cần được bảo vệ.

## Bước 9: cập nhật metadata và protected allowlist

Copy `song_metadata.json` hiện tại của staging cùng `private/asset-manifest.json` vào
work folder. Sao lưu cả hai trước khi sửa.

Với ví dụ FTR, thêm member này vào `song_metadata.json`:

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

Tính audio MD5:

```powershell
$audioMd5 = (Get-FileHash -Algorithm MD5 $audio).Hash.ToLowerInvariant()
$affMd5 = $akfcReport.source.md5
"AFF plaintext MD5: $affMd5"
"Audio MD5: $audioMd5"
```

Giá trị AFF là plaintext MD5, không phải encrypted container hash. Client kiểm tra chart
nó sẽ chơi sau khi AKFC decrypt.

Thêm member này vào `asset-manifest.json`:

```json
"my_fan_song": [
  "2.aff",
  "base.ogg"
]
```

Worker coi mỗi song row là allowlist đầy đủ. Mọi file trong metadata của protected song
cũng phải có trong row này và trong private R2 storage.

Xác minh cả hai JSON file:

```powershell
$metadataPath = Get-Item (Read-Host "Full path to the edited staging song_metadata.json")
$allowlistPath = Get-Item (Read-Host "Full path to the edited asset-manifest.json")
& $python -m json.tool $metadataPath.FullName > $null
if ($LASTEXITCODE -ne 0) { throw "song_metadata.json is invalid." }
& $python -m json.tool $allowlistPath.FullName > $null
if ($LASTEXITCODE -ne 0) { throw "asset-manifest.json is invalid." }
```

## Bước 10: upload protected object lên staging R2

Dùng profile `akaine-r2` ngắn hạn từ chương 5. Upload object trước và allowlist sau cùng
để Worker không bao giờ cấp quyền cho filename chưa tồn tại.

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

Worker refresh allowlist trong vòng 60 giây. Direct private URL và unsigned protected
URL vẫn phải trả `403`; staging server sẽ tạo signed URL cho positive test.

## Bước 11: cấu hình staging server cho pack

Protected fan song cần cấu hình staging như sau:

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

Giữ các entry hiện có nếu list đã chứa song hoặc pack khác. `FREE_PACKS` là entitlement
staging đơn giản nhất: mọi account nhận pack mà không cần tạo purchase row.

Response 7.0.255 hiện tại còn có projection 62 entry rõ ràng trong
`server/server/user.py`. Tìm `CLIENT_PACK_PROJECTION_7_0_255`, thay một custom-pack slot
cũ bằng `my_fan_pack`, và giữ tuple ở 62 entry. Không append item thứ 63 và không tùy
tiện bỏ official pack.

Server cần đúng edited songlist mà bundle sử dụng tại `database/songs/songlist`. Nó cũng
cần edited `database/song_metadata.json`. Sao lưu hai staging file, cài bản mới, giữ
ownership của service user rồi chỉ restart staging.

Static success là service active và HTTP readiness check pass. Nó chưa chứng minh client
tải được bài.

## Bước 12: thêm chart constant

Mở trang administrator của staging:

```text
https://api.example.com/web/login
```

Đăng nhập bằng private web-admin credential, mở **Change song** rồi thêm:

| Field | Ví dụ chỉ có FTR |
| --- | --- |
| Song ID | `my_fan_song` |
| English name | `My Fan Song` |
| PST constant | `-1` |
| PRS constant | `-1` |
| FTR constant | chart constant thật, ví dụ `10.4` |
| BYD constant | `-1` |
| ETR constant | `-1` |

Displayed `rating: 10` trong `songlist` và rating constant như `10.4` là hai giá trị
khác nhau. Server lưu `10.4` dưới dạng integer `104`. Difficulty bị thiếu giữ `-1` để
không tạo ranked score record.

Row này giúp FTR score thật đủ điều kiện tính rating. Total PTT chỉ đổi khi score đủ
mạnh để vào B30 hoặc recent play của người chơi.

## Bước 13: build và kích hoạt full-root bundle

Dùng `$overlay` làm overlay input trong chương 7. Bundle phải chứa:

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

Full `base.ogg` và encrypted `2.aff` là remote protected file, không thuộc public bundle
này. Build với content version và immutable alias mới, xác minh mọi part qua CDN rồi chỉ
kích hoạt trên staging.

## Bước 14: xác minh toàn bộ staging contract

Dùng test account sạch. Nếu account entitlement thay đổi, đăng nhập lại rồi chạy
**Cloud Sync → Download** trước khi đánh giá pack visibility.

Test theo thứ tự:

1. Client lạnh nhận bundle mới đúng một lần.
2. Pack mới có cover dự kiến và mở ra với ít nhất một card.
3. Bài chỉ hiện FTR difficulty đã khai báo.
4. Jacket và preview render mà không có FMOD error.
5. Download hoàn thành và icon biến mất.
6. DownloadList chứa chính xác `2.aff` và `base.ogg` với plaintext MD5 dự kiến.
7. Signed URL trả encrypted AFF cùng normalized OGG; direct `/private/` request và
   unsigned `/protected/` request vẫn trả `403`.
8. Chart vào gameplay và audio giữ đồng bộ.
9. Play hợp lệ tạo score row có play rating dương.
10. Sau force-stop và mở lại, account, pack, download state và gameplay vẫn hoạt động mà
    không tải lại bundle hoặc song.

Pack visibility chưa phải acceptance. Download, gameplay, score và restart là các gate
riêng.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| Pack không xuất hiện | Nó thiếu trong client projection 62 entry hoặc entitlement configuration. |
| Pack mở nhưng không có card | Song `set` không khớp pack ID, hoặc bundle cuối chứa sai songlist. |
| Bài hiện difficulty giả | Difficulty row rỗng hoặc trùng đã bị thêm vào songlist. |
| BYD tile thiếu hoặc không bấm được | Class-3 ID mới chưa được native registry chấp nhận. Dùng FTR/ETR hoặc tạo client patch được xác minh riêng. |
| Jacket đen hoặc preview im lặng | Selector file thiếu trong `songs/<id>` hoặc `songs/dl_<id>`. |
| Download báo thành công nhưng icon quay lại | Metadata, protected allowlist và object set thật không khớp. |
| Protected request trả `403` sau upload | Chờ TTL allowlist 60 giây rồi kiểm tra chính xác song ID và filename. |
| AKFC chart tải được nhưng không start | Chart được encrypt bằng key, song ID hoặc filename khác, hoặc raw/ciphertext hash bị nhầm. |
| Gameplay crash sau vài giây | Kiểm tra OGG timestamp cùng AFF event hoặc effect filename không được hỗ trợ. |
| Score lưu với rating `0` | Class đã chọn không có chart constant dương. |
| Play rating dương nhưng total PTT không đổi | Play không vào B30/recent set của người đó. |

## Trước production

- Bạn có quyền host mọi asset được cung cấp.
- Source hash và author credit đã được ghi lại.
- Song và pack ID ổn định, không trùng.
- Pack entitlement payload còn tối đa 62 entry.
- Chỉ difficulty thật được hiển thị và xếp hạng.
- AKFC receipt identity khớp song ID và filename cuối.
- Metadata plaintext hash khớp source AFF và normalized audio.
- Protected allowlist bao phủ chính xác metadata file set.
- Staging bundle, server metadata và R2 object dùng cùng ID.
- Cold download, gameplay, score và restart đều pass.
- Production backup và immutable bundle alias mới đã sẵn sàng.

Promote đúng file đã test trên staging. Không rebuild, re-encrypt hoặc rename chart giữa
staging và production; mỗi hành động đó tạo artifact khác và phải chạy lại các gate.
