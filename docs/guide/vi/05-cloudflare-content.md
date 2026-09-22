# Lưu và phân phối bundle, bài hát và protected chart

[English](../05-cloudflare-content.md) | Tiếng Việt

Chương này đặt R2 bucket sau `assets.your-domain`, upload bộ tài nguyên đã xác minh và
dùng Worker để bảo vệ private chart. Cache Rule giữ các bundle và bài hát được tải lặp
lại tại Cloudflare edge.

Sau khi hoàn tất việc kiểm tra:

- public bundle và asset bài hát tải từ `assets.your-domain`;
- lượt tải lặp lại được phục vụ từ Cloudflare cache;
- yêu cầu trực tiếp đến thư mục R2 riêng tư trả về `403`;
- các file được bảo vệ yêu cầu chữ ký ngắn hạn từ game server của bạn.

## Thời gian và chi phí

Dành 45 đến 90 phút, chưa tính thời gian upload. Cloudflare Workers, Cache Rules và
Smart Tiered Cache nằm trong Free plan khi dùng ở quy mô nhỏ. Giữ Argo Smart Routing và
Cache Reserve ở trạng thái tắt vì đây là tính năng trả phí và không cần cho setup này.

R2 Standard bao gồm 10 GB dung lượng lưu trữ mỗi tháng, một triệu thao tác ghi và mười
triệu thao tác đọc mỗi tháng. Chi phí lưu trữ bổ sung là 0,015 USD mỗi GB-tháng. Chỉ giữ
lại các release mà bạn vẫn cần để các gói trùng lặp cũ không âm thầm tăng hóa đơn.

## Bạn cần

- tên miền và tài khoản Cloudflare từ chương 2;
- bộ tài nguyên đã được xác minh từ chương 4;
- chủ sở hữu tài khoản Cloudflare hoặc tài khoản có quyền R2, Worker, DNS và Cache
  Rules;
- giá trị `MY_DOMAIN` và tên bucket ngắn chỉ gồm chữ thường, số và dấu gạch nối.

Các lệnh sử dụng các ví dụ sau:

```text
MY_DOMAIN=example.com
ASSET_HOST=assets.example.com
R2_BUCKET=akaine-assets-example
```

## Cách làm theo chương này

Các bước dashboard được thực hiện trong Cloudflare. Code block được chạy trong Windows
PowerShell. Giữ một cửa sổ PowerShell trong lúc upload vì các biến như `$bucket` và
`$endpoint` chỉ tồn tại trong cửa sổ đó. Secret chỉ được nhập vào `aws configure`, ô
Worker secret được mã hóa hoặc private secret file; không paste nó vào command trong
guide.

Có ba access path khác nhau:

| Path | Quyền truy cập mong đợi |
| --- | --- |
| `/bundle/` và `/songs/` | Public và cache được |
| `/private/` | Luôn bị chặn khỏi public HTTP |
| `/protected/songs/` | Worker route; request không có chữ ký bị chặn, request có chữ ký hợp lệ từ server được phép |

Không tiếp tục nếu private test bất ngờ trả `200`.

## Bước 1: cài đặt công cụ tải lên

Mở PowerShell với tư cách người dùng Windows bình thường của bạn:

```powershell
winget install --exact --id Amazon.AWSCLI
if ($LASTEXITCODE -ne 0) { throw "AWS CLI installation failed." }
```

Đóng và mở lại PowerShell, sau đó xác minh:

```powershell
aws --version
if ($LASTEXITCODE -ne 0) { throw "AWS CLI is not available after reopening PowerShell." }
```

Lệnh phải in phiên bản AWS CLI thay vì "không được nhận dạng". AWS CLI cũng hoạt động
với R2 vì R2 cung cấp API tải lên tương thích với S3.

## Bước 2: tạo R2 bucket

1. Mở bảng điều khiển Cloudflare.
2. Trong menu bên trái, mở **R2 Object Storage**.
3. Nếu Cloudflare yêu cầu bạn bật thanh toán R2, hãy thêm phương thức thanh toán. Mức
   trợ cấp miễn phí hàng tháng vẫn được áp dụng tự động.
4. Chọn **Create bucket**.
5. Nhập tên bucket duy nhất, chẳng hạn `akaine-assets-example`.
6. Chọn **Tiêu chuẩn** làm lớp lưu trữ.
7. Chọn **Create bucket**.

Không kích hoạt URL phát triển `r2.dev`. Hướng dẫn sử dụng R2 Custom Domain, hỗ trợ
Cloudflare cache thông thường và tránh rate limit của development endpoint.

## Bước 3: tạo credentials tải lên tạm thời

1. Trong **Bộ lưu trữ đối tượng R2**, chọn **Quản lý mã thông báo API R2**.
2. Chọn **Tạo mã thông báo API**.
3. Đặt tên nó là `akaine-initial-upload`.
4. Chọn **Đọc & ghi đối tượng**.
5. Giới hạn token trong bucket vừa tạo.
6. Tạo mã thông báo.
7. Lưu Access Key ID, Secret Access Key và S3 endpoint trong password manager.
   Cloudflare chỉ hiển thị secret một lần.

Định cấu hình cấu hình AWS CLI chuyên dụng:

```powershell
aws configure --profile akaine-r2
```

Nhập ID khóa truy cập R2 và Khóa truy cập bí mật. Đối với vùng mặc định, hãy nhập
`auto`; đối với định dạng đầu ra, hãy nhập `json`.

Bốn prompt lần lượt là Access Key ID, Secret Access Key, region và output format.
Profile name tách bucket credential này khỏi AWS profile thông thường. Command lưu
secret trong Windows user profile, vì vậy credential chỉ là tạm thời và sẽ bị thu hồi ở
bước 16.

Không dán secret vào GitHub Issue, tin nhắn Discord, screenshot hoặc
lệnh sẽ được lưu trong lịch sử shell.

## Bước 4: kiểm tra bố cục tài nguyên trước khi tải lên

Bộ công cụ đã được xác minh chứa thư mục `r2` có hình dạng sau:

```text
r2/
  bundle/                  public, versioned bundle files
  songs/                   public song resources
  private/
    asset-manifest.json    song-to-file allowlist
    songs/                 protected chart/audio files
```

File kê khai là một đối tượng JSON có khóa là ID bài hát và giá trị của nó là tên file duy
nhất mà Worker có thể trả về cho bài hát đó. Không tải lên file riêng tư không có trong
file kê khai và không thêm tên file vào file kê khai trừ khi đối tượng tương ứng tồn tại.

## Bước 5: tải lên bộ tài nguyên

Sao chép endpoint từ trang token của Cloudflare. Giá trị có dạng:

```text
https://ACCOUNT_ID.r2.cloudflarestorage.com
```

Trong PowerShell, nhập bucket và endpoint khi được hỏi:

```powershell
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$kit = Join-Path $kitRoot "r2"
$bucket = Read-Host "R2 bucket name"
$endpoint = Read-Host "R2 S3 endpoint beginning with https://"

Get-Item (Join-Path $kit "bundle"), (Join-Path $kit "songs"), (Join-Path $kit "private")
if ($endpoint -notmatch '^https://[0-9a-f]+\.r2\.cloudflarestorage\.com/?$') {
  throw "The value is not an R2 S3 endpoint. Copy it from the token page."
}

aws s3 sync $kit "s3://$bucket" `
  --endpoint-url $endpoint `
  --profile akaine-r2
if ($LASTEXITCODE -ne 0) { throw "R2 upload failed." }
```

`Get-Item` chứng minh ba source folder tồn tại trước upload. `aws s3 sync` copy file mới
và file thay đổi nhưng không xóa remote object vì command không dùng `--delete`.
Endpoint là địa chỉ S3 API trong token page, không phải `assets.your-domain` và không
phải URL `r2.dev`.

Liệt kê các đối tượng cấp cao nhất đã tải lên:

```powershell
aws s3 ls "s3://$bucket" `
  --endpoint-url $endpoint `
  --profile akaine-r2
if ($LASTEXITCODE -ne 0) { throw "R2 listing failed after upload." }
```

Bạn sẽ thấy `bundle/`, `songs/` và `private/`. Nếu upload thất bại, đừng chuyển bucket
sang public để né lỗi. Hãy kiểm tra lại endpoint, bucket name và phạm vi token.

## Bước 6: kết nối R2 Custom Domain

1. Mở **R2 Object Storage** và chọn bucket.
2. Mở **Cài đặt**.
3. Trong **Public access**, tìm **Custom Domains** rồi chọn **Connect Domain**.
4. Nhập `assets.your-domain`.
5. Xác nhận domain và chờ trạng thái **Active**.
6. Xác nhận rằng URL phát triển `r2.dev` vẫn bị tắt.

Cloudflare tạo kết nối DNS cần thiết. Không tạo CNAME theo cách thủ công từ tên server
nội dung của bạn thành tên server `r2.dev`.

## Bước 7: tạo một signing secret

Worker và game server phải dùng cùng một random signing secret. Tạo secret trong
PowerShell:

```powershell
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$assetSecret = [Convert]::ToBase64String($bytes)

$secretFile = Read-Host "Full path for the signing-secret file"
$secretFile = [IO.Path]::GetFullPath($secretFile)
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$repoPrefix = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
if ($secretFile.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Store the signing secret outside the Git repository."
}
$secretFolder = Split-Path -Parent $secretFile
New-Item -ItemType Directory -Force $secretFolder | Out-Null
Set-Content `
  -LiteralPath $secretFile `
  -Value $assetSecret `
  -NoNewline

Get-Item $secretFile | Select-Object FullName, Length
```

Random-number generator tạo 32 byte không đoán được, còn Base64 chuyển chúng thành text
mà Worker và server configuration đều nhận. Path check giữ file ngoài Git. Output cuối
phải hiện file không rỗng mà không in nội dung của nó.

Lưu trữ bản sao thứ hai trong trình quản lý mật khẩu của bạn. Không in biến hoặc đưa file
vào Git. Chương server sau này sẽ tải cùng giá trị này vào môi trường server.

## Bước 8: tạo Worker bảo vệ asset

1. Trong Cloudflare, mở **Workers & Pages**.
2. Chọn **Tạo** → **Worker**.
3. Đặt tên là `akaine-protected-assets` và triển khai Worker khởi động.
4. Mở Worker mới và chọn **Chỉnh sửa mã**.
5. Trên máy tính, sao chép nguồn Worker công khai vào clipboard:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Get-Content `
  -LiteralPath (Join-Path $repoRoot "cloudflare\protected-assets\worker.mjs") `
  -Raw | Set-Clipboard

if (-not (Get-Clipboard -Raw)) {
  throw "Worker source was not copied to the clipboard."
}
```

6. Thay thế mã khởi động bằng nội dung bảng nhớ tạm và chọn **Triển khai**.

Worker source công khai không chứa signing secret hoặc game asset manifest.

## Bước 9: thêm các Worker binding

Mở Worker → **Cài đặt** → **Bindings** và thêm:

| Loại ràng buộc | Tên biến | Giá trị |
| --- | --- | --- |
| R2 bucket | `AKAINE_ASSETS` | bucket tạo ở Bước 2 |
| Biến văn bản | `ASSET_MANIFEST_KEY` | `private/asset-manifest.json` |

Sau đó mở **Variables and Secrets**, thêm encrypted secret tên
`ASSET_SIGNING_SECRET`, rồi dán giá trị từ file tạo ở Bước 7.

Lưu và triển khai cài đặt Worker.

## Bước 10: đính kèm các protected route

Mở Worker → **Cài đặt** → **Miền & route** → **Thêm** → **Route đường**. Chọn vùng
Cloudflare của bạn và thêm cả hai route:

```text
assets.your-domain/private/*
assets.your-domain/protected/songs/*
```

Route đầu tiên ngăn truy cập trực tiếp vào tiền tố R2 riêng. Route thứ hai chỉ chấp nhận
các URL được game server của bạn ký, kiểm tra danh sách cho phép, sau đó đọc đối tượng
được phê duyệt từ R2.

Để đảm bảo hiệu suất, Worker có thể giữ một file được bảo vệ hoàn chỉnh có dung lượng lên
tối đa 32 MB trong cache trong một ngày. Worker vẫn kiểm tra chữ ký trước mỗi cache
lookup. Range request và file lớn hơn được đọc trực tiếp từ R2. Protected allowlist
được tải lại từ R2 sau tối đa 60 giây, vì vậy fan-chart row mới không cần redeploy
Worker.

## Bước 11: kiểm tra private boundary

Thay thế tên miền và sử dụng bất kỳ tên bài hát/file nào:

```powershell
$assetHost = Read-Host "Asset hostname without https://"
$privateStatus = curl.exe -sS -o NUL -w "%{http_code}" "https://$assetHost/private/songs/test/2.aff"
$protectedStatus = curl.exe -sS -o NUL -w "%{http_code}" "https://$assetHost/protected/songs/test/2.aff"

if ($privateStatus -ne "403" -or $protectedStatus -ne "403") {
  throw "Private boundary failed: private=$privateStatus protected=$protectedStatus"
}

"Private boundary passed: private=$privateStatus protected=$protectedStatus"
```

Cả hai yêu cầu đều phải trả về `403`. Cái đầu tiên bị chặn vì đường dẫn lưu trữ riêng tư
trực tiếp bị vô hiệu hóa. Cái thứ hai bị chặn vì nó không có chữ ký server. Phản hồi
`200` có nghĩa là private boundary không hoạt động. Gỡ public access rồi kiểm tra lại
Worker route trước khi tiếp tục.

## Bước 12: tạo Cache Rule cho bundle

Mở miền Cloudflare của bạn → **Quy tắc** → **Cache Rule** → **Tạo quy tắc**.

Đặt tên cho quy tắc là `Akaine immutable bundles`. Chọn **Chỉnh sửa biểu thức** và dán,
thay thế tên server:

```text
(http.host eq "assets.example.com" and starts_with(http.request.uri.path, "/bundle/"))
```

Cấu hình:

- Tính đủ điều kiện của cache: **Đủ điều kiện để có cache**.
- Edge TTL: **Ignore cache-control header and use this TTL** → 1 năm.
- Trình duyệt TTL: **Ghi đè nguồn gốc** → 1 năm.

Lưu và deploy rule. Bundle filename phải có version mới khi nội dung thay đổi. Không ghi
đè bundle đã được cache bằng byte khác.

## Bước 13: tạo Cache Rule bài hát công khai

Tạo Cache Rule thứ hai có tên `Akaine public songs` với:

```text
(http.host eq "assets.example.com" and starts_with(http.request.uri.path, "/songs/"))
```

Cấu hình:

- Tính đủ điều kiện của cache: **Đủ điều kiện để có cache**.
- Edge TTL: **Ignore cache-control header and use this TTL** → 1 tháng.
- Trình duyệt TTL: **Ghi đè nguồn gốc** → 1 ngày.

Quy tắc này không khớp với `/private/` hoặc `/protected/`.

## Bước 14: bật Smart Tiered Cache

Mở zone → **Cache** → **Tiered Cache** rồi bật **Smart Tiered Topology**. Khi edge gần
người chơi bị miss, Cloudflare có thể hỏi tier trung gian trước khi đọc lại từ R2.

Tắt các sản phẩm trả phí tùy chọn này:

- Cache Reserve;
- Argo Smart Routing.

## Bước 15: xác minh cache công khai

Tìm tên bundle manifest trong `README.txt` của bộ tài nguyên, sau đó gửi cùng request
hai lần:

```powershell
$url = "https://assets.example.com/bundle/MANIFEST-FILENAME.json"

curl.exe -sS -D headers-1.txt -o NUL --range 0-31 $url
curl.exe -sS -D headers-2.txt -o NUL --range 0-31 $url

Select-String -Path headers-1.txt,headers-2.txt -Pattern `
  "HTTP/","CF-Cache-Status","Content-Range","Cache-Control"
```

Phản hồi phải là `206 Partial Content`, bao gồm `Content-Range` và cuối cùng hiển thị
`CF-Cache-Status: HIT`. Yêu cầu đầu tiên có thể hiển thị `MISS` trong khi Cloudflare lấp
cache warm-up. Nếu request thứ hai chưa phải `HIT`, chờ một lát rồi thử lại trước khi
thay đổi quy tắc.

## Yêu cầu API không được sử dụng các Cache Rule này

Tên server `api.your-domain` rất linh hoạt: phản hồi đăng nhập, tài khoản và điểm số
không được cache. Không tạo “Cache Everything” rule cho server API.
Chương server sẽ cấu hình `Cache-Control: private, no-store`; sau khi server chạy, phản
hồi API sẽ hiển thị `CF-Cache-Status: DYNAMIC`.

## Cập nhật release sau

- Publish bundle mới dưới filename có version mới.
- Không ghi đè filename đang được cache một năm.
- Nếu một đối tượng bài hát công khai phải được thay thế tại cùng một URL, hãy mở
  **Cache** → **Cấu hình** → **Purge Cache** → **Custom Purge** và chỉ lọc URL đã thay
  đổi.
- Cập nhật `private/asset-manifest.json` cùng với các đối tượng riêng tư. File không được
  khai báo trong file kê khai vẫn không thể truy cập được.

## Bước 16: thu hồi thông tin tải lên tạm thời

Sau khi test upload và cache ban đầu đã pass:

1. Mở **Bộ lưu trữ đối tượng R2** → **Quản lý mã thông báo API R2**.
2. Thu hồi `akaine-initial-upload`.
3. Mở `%USERPROFILE%\.aws\credentials` trong Notepad.
4. Chỉ xóa phần `[akaine-r2]` và hai dòng chính của nó. Không xóa hồ sơ khác mà bạn sử
   dụng cho công việc AWS không liên quan.

Tạo token ngắn hạn mới, chỉ có quyền trên bucket, khi bạn chủ động publish update. Thu
hồi token ngay nếu nó xuất hiện trong screenshot, terminal log hoặc repository.

## Kiểm tra công việc của bạn

- R2 bucket chứa `bundle/`, `songs/` và `private/`.
- `assets.your-domain` là R2 Custom Domain đang `Active`.
- Development URL `r2.dev` đã tắt.
- Direct private request và unsigned protected request trả `403`.
- Worker có R2 binding, manifest-key variable và signing secret.
- Bundle request hỗ trợ `Range` và trở thành cache `HIT`.
- Smart Tiered Cache đã bật.
- Cache Reserve và Argo bị tắt.
- Temporary upload token và local profile `akaine-r2` đã bị xóa.

Chương tiếp theo cài game server và cấu hình cùng asset signing secret để server tạo
được protected download URL hợp lệ.
