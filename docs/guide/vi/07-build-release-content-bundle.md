# Build và phát hành content bundle 7.0.255

[English](../07-build-release-content-bundle.md) | Tiếng Việt

Chương này bắt đầu từ một full-root bundle đã được xác minh, áp dụng một lớp
content overlay nhỏ, build release bất biến mới rồi đưa chính bộ byte đó từ staging
lên production. Quy trình dùng `scripts/build_content_bundle.py`; các công cụ 6.14
cũ trong `server/tools` không tạo đúng định dạng release 7.0.255.

Hãy hoàn thành chương 1 đến chương 6 trước. Bạn cũng cần một staging server dùng cùng
source và cấu trúc cấu hình với production.

## Phân biệt ba loại tên

Application version là `7.0.255`. Nó xác định Android client và không đổi khi bạn phát
hành content mới.

Content version có dạng `7.0.255.9`. Số cuối phải tăng sau mỗi release được chấp nhận
để server và client có thể so sánh phiên bản.

Alias là tiền tố tên file của manifest và mọi part `.cb`, ví dụ
`7.0.255-fan-album-r1`. Alias là bất biến: sau khi upload, không được đặt byte khác
vào cùng R2 key.

Mỗi release có một manifest `<alias>.json` cùng số file
`<alias>_<index>.cb` được khai báo trong `totalPartitions`. Baseline Akaine 7.0.255
đã kiểm chứng có bảy partition. Builder đọc số này từ source manifest thay vì tự
đoán.

## Chuẩn bị source đã biết là tốt

Dùng full-root source trong bộ tài nguyên riêng đã xác minh. Full root có
`previousVersionNumber: null`, nên một client sạch có thể cài nó mà không cần chuỗi
update cũ.

Thư mục source phải có cấu trúc:

```text
bundle-source/
  manifest.json
  source_0.cb
  source_1.cb
  ... one source_N.cb for every declared partition
```

Chọn đường dẫn cho release trong PowerShell. Đặt source, overlay và output ngoài Git
repository vì chúng chứa dữ liệu game riêng.
Content-detail key là file key nhị phân thô trong bộ tài nguyên riêng; không chuyển nó
sang dạng văn bản hexadecimal hoặc Base64.

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

Kiểm tra source manifest trước khi sửa bất cứ thứ gì:

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

Đừng dùng một bundle chỉ vì client từng tải được nó. Hãy giữ SHA-256 dự kiến của
manifest trong bộ tài nguyên riêng và so sánh trước mỗi lần build.

## Tạo overlay

Overlay sử dụng đường dẫn tương đối so với bundle root. File trùng đường dẫn sẽ thay
thế file nguồn; đường dẫn mới được nối vào partition cuối.

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

Copy `songlist` và `packlist` có thể chỉnh sửa đi kèm đúng source bundle vào
`overlay/songs/`, rồi chỉ sửa phần cần thiết. Không lấy catalogue của bundle version
khác làm điểm bắt đầu.

Mỗi `id` bài hát phải là duy nhất. Trường `set` phải bằng `single` hoặc bằng `id` của
một pack đang tồn tại. Mỗi `pack_parent` cũng phải trỏ tới pack tồn tại. Nếu thiếu
pack cha, client có thể tải và check tới 100% rồi crash trước start screen ở mọi lần
mở sau đó.

Để selector hiển thị đúng, hãy thêm jacket và preview mà catalogue sử dụng. Bài dùng
remote download thường để chart và audio chơi được trong protected R2, nhưng bundle
vẫn cần jacket và preview cho selector. Khi một độ khó có `audioOverride: true`, hãy
thêm đúng `<ratingClass>_preview.ogg` vào `songs/dl_<song_id>/`.

Không đưa chart và full audio vào public bundle nếu server phải cấp chúng bằng signed
URL. `song_metadata.json`, private R2 allowlist và object riêng thực tế phải khớp nhau
trước khi release.

## Build full-root candidate

Chạy builder trong repository:

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

Builder thực hiện các việc sau:

- xác minh từng span nguồn bằng hash trong manifest;
- từ chối đường dẫn trùng, khoảng trống, span chồng nhau và source part bị thiếu;
- kiểm tra `songlist`, `packlist`, song set và pack cha;
- giữ số partition của source và giới hạn mỗi part ở 480 MiB;
- tính lại SHA-256 cho mọi entry cùng HMAC detail cho catalogue bảo vệ đã thay đổi;
- build vào thư mục tạm và chỉ công bố output sau lượt xác minh đầy đủ thứ hai.

Output chỉ đủ điều kiện release khi có `ready-manifest.json`, file đó ghi
`"status": "ready"`, và không có `failure.json`.

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

Không gộp partition hoặc chuyển kết quả thành delta một part. Client 7.0.255 từng từ
chối delta và layout một part chưa được kiểm chứng với lỗi `-1013`.

## Upload object bất biến lên staging

Tạo R2 token ngắn hạn mới, chỉ có quyền trên asset bucket, rồi cấu hình lại AWS CLI
profile `akaine-r2` từ chương 5. Xác nhận chưa có target key nào tồn tại. Nếu key đã
tồn tại, hãy chọn alias mới thay vì ghi đè.

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

Upload lỗi không có nghĩa là phải build lại. Hãy kiểm tra object lỗi rồi tiếp tục đúng
lượt upload đó. Nếu API trả `429`, chờ hết khoảng retry rồi tiếp tục bước kiểm tra bị
gián đoạn, không đổi candidate.

## Xác minh byte qua CDN

Tải manifest và từng part qua asset hostname công khai. Bước này kiểm tra R2, custom
domain và Cloudflare, thay vì chỉ kiểm tra file local.

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

Gửi Range request hai lần và xác nhận response là `206`, có đúng tổng kích thước và
cuối cùng trở thành Cloudflare cache `HIT`:

```powershell
$firstPart = ($publishFiles | Where-Object Name -Like "*.cb" | Select-Object -First 1).Name
curl.exe -sS -D bundle-range-1.txt -o NUL --range 0-31 "https://$assetHost/bundle/$firstPart"
curl.exe -sS -D bundle-range-2.txt -o NUL --range 0-31 "https://$assetHost/bundle/$firstPart"
Select-String -Path bundle-range-1.txt,bundle-range-2.txt -Pattern "HTTP/","Content-Range","CF-Cache-Status"
```

## Kích hoạt trên staging

Sao lưu thư mục bundle và cấu hình của staging. Chỉ đặt manifest mới vào thư mục
bundle đang hoạt động; các file `.cb` vẫn nằm trên R2. Đặt
`BUNDLE_DOWNLOAD_LINK_PREFIX` thành `https://<asset-host>/bundle/`, restart staging
service và giữ lại đường dẫn backup mà shell đã in ra.

Trong `config.py` của staging, dùng public asset prefix mới và cho phép content
version 7.0.255 cũ tiến lên full root mới nhất:

```python
BUNDLE_DOWNLOAD_LINK_PREFIX = "https://assets.example.com/bundle/"
BUNDLE_STRICT_MODE = False
FRESH_INSTALL_ONLY_BUNDLE_VERSION = ""
```

Upload manifest, sao lưu thư mục đang hoạt động rồi kích hoạt candidate. Các lệnh sẽ
hỏi đường dẫn remote thay vì giả định vị trí cài server:

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

Server đang chạy phải parse `<alias>.json`, vì vậy tên file này phải khớp với các file
`<alias>_<index>.cb` đã upload. Không được chỉ đổi tên manifest.

Kiểm tra API bằng content version rỗng và target version:

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

Response của content-bundle API phải có `Cache-Control: private, no-store`, còn
Cloudflare phải báo nó là dynamic. Không áp dụng bundle asset cache rule cho API
hostname.

## Kiểm thử bằng client thật

Hash tĩnh chỉ chứng minh byte giống nhau, chưa chứng minh client tương thích. Dùng tài
khoản test sạch và client trỏ tới staging.

1. Bắt đầu khi chưa tải content và ghi lại content version hiện tại của thiết bị.
2. Tải candidate và để quá trình checking chạy tới 100%.
3. Vào được title screen và menu chính.
4. Mở Music Play, pack đã thay đổi và vài bài đã thay đổi.
5. Kiểm tra jacket, preview, mọi độ khó đã khai báo và remote download.
6. Chơi ít nhất một chart đã thay đổi và gửi score.
7. Tắt hẳn ứng dụng, mở lại rồi xác nhận không tải lần hai, không logout, không crash
   lúc bootstrap và không lặp loading.

Hãy thu server log và Android logcat trong lúc kiểm thử. Chỉ tải thành công chưa đủ để
được coi là pass.

## Đưa đúng bộ byte đó lên production

Không build lại sau khi staging đã pass. Ghi lại các giá trị SHA-256 trong
`build-report.json`, sao lưu cấu hình production cùng thư mục bundle đang hoạt động,
rồi kích hoạt đúng manifest và R2 object đã thử trên staging.

Lặp lại ma trận API trên production trước khi công bố release. Sau đó chạy một lượt
cold download và restart qua production domain. Thu hồi R2 token tạm và xóa profile
AWS local sau khi xác minh xong.

Giữ backup production cũ cho tới khi release mới đã qua cold install, restart và tải
bài bình thường.

## Rollback an toàn

Nếu API check lỗi trước khi client nào tải bundle, khôi phục thư mục bundle và cấu
hình đã backup, restart service rồi chạy lại ma trận API. Giữ nguyên object bất biến
trên R2 cho tới khi hiểu được sự cố.

Sau khi client đã cài content version cao hơn, khôi phục server không hạ version trên
client đó. Hãy sửa candidate bằng content version cao hơn và alias mới. Dùng lại alias
lỗi có thể khiến các Cloudflare cache trên thế giới giữ những bộ byte khác nhau.

## Tra lỗi nhanh

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| `-1013` khi tải hoặc checking | Hash span trong manifest, tên part, số part, Range support và việc có dùng tool delta/một part cũ hay không |
| Checking tới 100%, sau đó mọi lần mở đều crash | Thiếu pack mà `song.set` trỏ tới, `pack_parent` hỏng, catalogue JSON sai hoặc thiếu startup/selector resource trong full root |
| Bundle tải lại sau mỗi lần mở | API ở target version chưa trả rỗng, API bị cache, server manifest cũ hoặc content version không khớp |
| Thiếu pack hoặc bài | `songlist`, `packlist`, đường dẫn selector asset và purchase/unlock data trên server không mô tả cùng một ID |
| Icon download không biến mất | `remote_dl`, `song_metadata.json`, protected allowlist và object R2 thực tế không khớp |
| Jacket đen hoặc preview im lặng | Thiếu đường dẫn jacket/preview cho selector; `audioOverride` có thể cần preview riêng theo độ khó |
| CDN chạy trong trình duyệt nhưng client timeout | Kiểm thử client tải đầy đủ và đồng thời; Range probe nhỏ không chứng minh được tốc độ truyền kéo dài |
| API trả `429` | Chờ hết khoảng retry rồi tiếp tục request bị gián đoạn; không build lại hoặc đổi tên release |

## Checklist release

- Source là full root 7.0.255 đã xác minh.
- Content version đã tăng và alias chưa từng được dùng.
- Catalogue qua kiểm tra song-pack và pack-parent.
- `ready-manifest.json` xác nhận artifact đã được xác minh.
- Mọi R2 object đều chưa tồn tại trước upload.
- Bản tải đầy đủ qua CDN có SHA-256 khớp file local.
- API check với version rỗng và target version đều pass, không bị cache.
- Client staging sạch tải được, vào menu, chơi content đã thay đổi và restart mà không
  tải lại hoặc crash.
- Production dùng đúng bộ byte đã kiểm thử trên staging.
- Đã ghi lại đường dẫn backup và rollback production.
- Đã thu hồi R2 credential tạm.
