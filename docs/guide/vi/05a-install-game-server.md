# Cài game server 7.3.1

[English](../05a-install-game-server.md) | Tiếng Việt

Chương này hướng dẫn chạy API Akaine 7.3.1 trên máy Linux. Hãy chuẩn bị [bundle và nội dung trên R2](05-cloudflare-content.md) trước khi cài. DB mới khởi tạo chưa có người chơi. Để chơi từ game, bạn cần APK Akaine 7.3.1 phù hợp hostname của server.

## 1. Chuẩn bị Linux instance

Các lệnh trong phần này chạy trong Lightsail SSH terminal. Đăng nhập bằng user `ubuntu`,
SSH key và static IP từ chương 2. Mỗi lần paste một block.

```bash
set -e
sudo apt update
sudo apt install -y git nginx python3-venv nano

if ! id akaine >/dev/null 2>&1; then
  sudo useradd --system --user-group --home-dir /srv/akaine --shell /usr/sbin/nologin akaine
fi
sudo install -d -o akaine -g akaine -m 0750 /srv/akaine
```

`akaine` là service account, tách khỏi SSH login của bạn. Server sẽ chạy bằng account
này và ghi vào project directory của nó. Nếu apt báo lỗi, hãy dừng và giải quyết trước
khi clone source.

## 2. Cài public source và Python package

Vẫn trong Linux terminal. `set -e` dừng block ngay khi một command lỗi:

```bash
set -e
sudo -u akaine git clone https://github.com/quanq026/akaine.git /srv/akaine/repo
sudo -u akaine python3 -m venv /srv/akaine/repo/.venv
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m pip install -r /srv/akaine/repo/server/requirements.txt
sudo install -d -o akaine -g akaine /srv/akaine/repo/server/log
sudo install -d -o akaine -g akaine /srv/akaine/repo/server/database/backup

sudo -u akaine /srv/akaine/repo/.venv/bin/python -c 'import flask, cryptography, waitress; print("Server packages ready")'
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m compileall -q /srv/akaine/repo/server
```

Project có thư mục `server/` bên trong Git checkout. Python virtual environment ở
`/srv/akaine/repo/.venv`; service template dùng interpreter đó. Package check in
`Server packages ready`; source compilation thành công thường không
in gì. Dependency file cũng chuẩn bị Discord bot tùy chọn ở chương
5b. Các lệnh dành cho `/srv/akaine/repo` mới và rỗng. Nếu đã có
repository ở đó, hãy kiểm tra nó thay vì clone đè.

## 3. Cung cấp content file đã xác minh

Public checkout không chứa playable songlist hoặc bundle byte. Từ private kit đã xác
minh, hãy tìm:

```text
server songlist              -> database/songs/songlist
server song metadata         -> database/song_metadata.json
individual song files        -> database/songs/<song-id>/<file>
matching native packlist      -> database/client_catalogs/7.3.1/packlist
7.3.1 full-root manifest      -> database/bundle/<alias>.json
bundle parts                  -> R2 bundle/<alias>_0.cb ...
```

Manifest và các part phải dùng cùng alias. Chương 5 upload part lên R2; server này chỉ
cần manifest. Nếu kit thiếu file hoặc verification không pass, dừng lại và lấy content
set khớp nhau.

Mở Windows PowerShell mới. Các lệnh hỏi vị trí file thật rồi upload chúng vào account
`ubuntu`:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the Lightsail SSH private key")
$serverIp = Read-Host "Lightsail static IPv4 address"
$songlist = Get-Item (Read-Host "Full path to the verified server songlist")
$songMetadata = Get-Item (Read-Host "Full path to the verified song_metadata.json")
$bundleManifest = Get-Item (Read-Host "Full path to the verified 7.3.1 bundle manifest")
$packlist = Get-Item (Read-Host "Full path to the matching native packlist")
$songFiles = Get-Item (Read-Host "Full path to the verified songs folder from your content kit")
if (-not $songFiles.PSIsContainer -or $songFiles.Name -ne "songs") { throw "Choose the songs folder containing the song ID folders." }

ssh -i $sshKey.FullName "ubuntu@$serverIp" "install -d -m 700 /home/ubuntu/akaine-intake"
if ($LASTEXITCODE -ne 0) { throw "Could not create the private intake folder." }

scp -i $sshKey.FullName $songlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/songlist"
if ($LASTEXITCODE -ne 0) { throw "Songlist upload failed." }
scp -i $sshKey.FullName $songMetadata.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/song_metadata.json"
if ($LASTEXITCODE -ne 0) { throw "Song metadata upload failed." }
scp -i $sshKey.FullName $bundleManifest.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$($bundleManifest.Name)"
if ($LASTEXITCODE -ne 0) { throw "Bundle manifest upload failed." }

scp -i $sshKey.FullName $packlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/packlist"
if ($LASTEXITCODE -ne 0) { throw "Packlist upload failed." }
scp -r -i $sshKey.FullName $songFiles.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/"
if ($LASTEXITCODE -ne 0) { throw "Song file upload failed." }

"Bundle manifest name: $($bundleManifest.Name)"
"Packlist SHA256: $((Get-FileHash -Algorithm SHA256 $packlist.FullName).Hash.ToLowerInvariant())"
```

Quay lại Linux SSH terminal và nhập manifest filename mà PowerShell vừa in:

```bash
set -e
read -r -p 'Bundle manifest filename: ' manifest_name
case "$manifest_name" in
  *[!A-Za-z0-9._-]*|'') echo 'Invalid filename' >&2; false ;;
esac
test -f "/home/ubuntu/akaine-intake/$manifest_name"

sudo install -d -o akaine -g akaine /srv/akaine/repo/server/database/client_catalogs/7.3.1
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/packlist /srv/akaine/repo/server/database/client_catalogs/7.3.1/packlist
sudo install -d -o akaine -g akaine /srv/akaine/repo/server/database/songs
sudo cp -R /home/ubuntu/akaine-intake/songs/. /srv/akaine/repo/server/database/songs/
sudo chown -R akaine:akaine /srv/akaine/repo/server/database/songs
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/songlist /srv/akaine/repo/server/database/songs/songlist
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/song_metadata.json /srv/akaine/repo/server/database/song_metadata.json
sudo install -o akaine -g akaine -m 0644 "/home/ubuntu/akaine-intake/$manifest_name" "/srv/akaine/repo/server/database/bundle/$manifest_name"
sudo -u akaine /srv/akaine/repo/.venv/bin/python - "$manifest_name" <<'PY'
import json, sys
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
manifest = root / 'bundle' / sys.argv[1]
data = json.loads(manifest.read_text())
assert data['applicationVersionNumber'] == '7.3.1'
assert data['previousVersionNumber'] is None
assert data['totalPartitions'] > 0
json.loads((root / 'songs/songlist').read_text(encoding='utf-8-sig'))
json.loads((root / 'song_metadata.json').read_text())
assert json.loads((root / 'client_catalogs/7.3.1/packlist').read_text())['packs']
print('7.3.1 content files ready')
PY
```

Server đọc songlist để quyết định unlock và download, metadata để lấy download filename
và checksum, manifest để lấy bundle version và part URL. Chỉ cài manifest sẽ không làm
song download hoạt động.
Lệnh cuối phải in `7.3.1 content files ready`.

## 4. Cấu hình server 7.3.1

Sao chép cấu hình mẫu rồi nhập thông tin trong file `config.py` riêng của bạn.

```bash
sudo -u akaine cp /srv/akaine/repo/server/config.7.3.1.example.py /srv/akaine/repo/server/config.py
sudo chmod 0600 /srv/akaine/repo/server/config.py
sudo -u akaine nano /srv/akaine/repo/server/config.py
```

Điền tên admin, mật khẩu và khóa bí mật riêng. Đặt URL R2 cho bundle và URL HTTPS của server cho đường tải từng bài. Mẫu dùng cổng nội bộ 18080. Đổi `7.3.1.1` thành `versionNumber` trong manifest của bạn, ở cả mục target và epoch. Tính SHA-256 cho bốn file rồi chép từng hash vào đúng dòng trong cấu hình.

```bash
cd /srv/akaine/repo/server
sha256sum database/songs/songlist database/song_metadata.json database/client_catalogs/7.3.1/packlist database/bundle/*.json
```

Cấu hình mẫu dùng thư mục nhạc trên server cho tải từng bài. Nếu dùng Worker cho nhạc, xem [Cấu hình Cloudflare và R2](05-cloudflare-content.md). Xác minh cấu hình trước khi khởi động.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m tools.check_content
```

Lệnh phải in `7.3.1 content ready` cùng số pack và số file nhạc cục bộ. Nếu có file thiếu, bổ sung ở `database/songs/<song-id>/` rồi kiểm lại trước khi bật service. Sau khi cài client tương thích, thử tải và chơi một bài có nút Download.

## 5. Khởi động service và kiểm tra HTTP local

Trong Linux terminal:

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/arcaea-server.service /etc/systemd/system/arcaea-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now arcaea-server.service
sudo systemctl is-active arcaea-server.service
curl --fail --silent --show-error http://127.0.0.1:18080/
```

Service phải báo `active` và lệnh cuối trả `Hello World!`. Nếu không, kiểm tra
`sudo journalctl -u arcaea-server.service -n 80 --no-pager`. Hãy sửa content thiếu,
JSON lỗi, credential trống hoặc permission tại nguồn. Service phải khỏe ở local trước
khi cấu hình nginx.

## 6. Đặt nginx và HTTPS trước service

Giữ `api` DNS record ở chế độ **DNS only** cho tới khi certificate hoạt động. Trong
Linux terminal, chỉ nhập domain đã đăng ký, không kèm `api.` hay `https://`:

```bash
set -e
read -r -p 'Registered domain: ' domain
case "$domain" in
  *[!A-Za-z0-9.-]*|'') echo 'Invalid domain' >&2; false ;;
esac

sudo install -o root -g root -m 0644 /srv/akaine/repo/server/nginx/akaine.conf.example /etc/nginx/sites-available/akaine
sudo sed -i "s/api.example.com/api.$domain/" /etc/nginx/sites-available/akaine
if [ ! -e /etc/nginx/sites-enabled/akaine ]; then
  sudo ln -s /etc/nginx/sites-available/akaine /etc/nginx/sites-enabled/akaine
fi
sudo nginx -t
sudo systemctl reload nginx
curl --fail --silent --show-error -H "Host: api.$domain" http://127.0.0.1/
```

Lệnh cuối phải trả `Hello World!`. Lấy và cài certificate bằng Certbot khi DNS vẫn trỏ
thẳng tới server:

```bash
set -e
sudo apt install -y snapd
sudo snap install --classic certbot
sudo /snap/bin/certbot --nginx -d "api.$domain"
sudo /snap/bin/certbot renew --dry-run
curl --fail --silent --show-error "https://api.$domain/"
```

Trả lời các prompt email và điều khoản của Certbot. Lệnh cuối phải trả `Hello World!`
qua HTTPS. Trong Cloudflare, đổi `api` DNS record thành **Proxied** và chọn
**SSL/TLS → Overview → Full (strict)** chỉ sau khi certificate hoạt động. Giữ `link` ở
DNS only.

[Điều kiện Full (strict) của Cloudflare](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
yêu cầu certificate hợp lệ tại origin. [Hướng dẫn nginx của
Certbot](https://certbot.eff.org/instructions?os=snap&ws=nginx) mô tả lệnh cài
certificate và kiểm tra gia hạn.

## 8. Xác minh bundle API qua public hostname

Trong Windows PowerShell, đặt `$apiHost` là hostname của bạn:

```powershell
$apiHost = Read-Host "Game API hostname without https://"
$bundleUrl = "https://$apiHost/game/content_bundle"
$response = Invoke-WebRequest -Uri $bundleUrl -Headers @{
  AppVersion = '7.3.1'
  ContentBundle = '0.0.0'
  DeviceId = 'guide-server-check'
}
$body = $response.Content | ConvertFrom-Json

if ($response.StatusCode -ne 200 -or -not $body.success) {
  throw "The content-bundle API did not respond successfully."
}
if ($response.Headers['Cache-Control'] -notmatch 'no-store') {
  throw "The content-bundle decision is missing no-store."
}
if (@($body.value.orderedResults).Count -ne 1) {
  throw "A fresh 7.3.1 client did not receive one bundle."
}

$body.value.orderedResults | Select-Object contentBundleVersion, appVersion, bundleSize

$targetVersion = $body.value.orderedResults[0].contentBundleVersion
$currentResponse = Invoke-RestMethod -Uri $bundleUrl -Headers @{
  AppVersion = '7.3.1'
  ContentBundle = $targetVersion
  DeviceId = 'guide-server-check'
}
if (@($currentResponse.value.orderedResults).Count -ne 0) {
  throw "A client already on the target bundle received another update."
}
"Current-version bundle check passed: $targetVersion"
```

Request thứ hai chứng minh client ở target version không tải lại. API hostname không
được có Cloudflare cache `HIT` cho route này. Bundle part và
song object còn cần kiểm tra R2/CDN cùng client riêng ở chương 5, 7 và 9.

## Tạo tài khoản và kiểm quyền

Nếu dùng Discord, qua [chương bot](05b-discord-bot.md) rồi gõ `/create`. Nếu cài server không kèm bot, tạo acc thử trên terminal Linux. Mật khẩu nhập khi chương trình hỏi.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python tools/create_user_cli.py TestPlayer
```

Acc mới nhận pack, bài lẻ, nhân vật và các quyền mở khóa có trong DB của bạn. Sau khi đăng nhập, chọn **Cloud Sync → Download** trong game. Nếu cần kiểm các acc đã có sau khi thêm nội dung, chạy lệnh này để xem trước.

```bash
sudo -u akaine /srv/akaine/repo/.venv/bin/python tools/create_user_cli.py --repair-existing all --dry-run
```

Xem `expected_content` để biết số quyền mà DB của bạn có. `inserted`, `raised_null_or_zero_to_one` và `full_characters_added` là số mục còn thiếu trước khi bù. Sao lưu DB theo [chương 5c](05c-backup-recovery.md) rồi bỏ `--dry-run` nếu muốn áp dụng. Có thể thay `all` bằng `user_id` để kiểm một acc.

## Cập nhật PTT trên server đã có người chơi

Bỏ qua bước này nếu cài mới. Server tính PTT theo Best 50, trong đó 10 bài đầu được tính hai lần. Lệnh đầu xem trước thay đổi. Lệnh sau sao lưu SQLite vào file riêng trước khi ghi.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m tools.recompute_ptt database/arcaea_database.db
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m tools.recompute_ptt database/arcaea_database.db --backup /srv/akaine/pre-b50.db
```

Script in số tài khoản được cập nhật. Nếu chạy lại sau khi có điểm mới, hãy dùng tên file sao lưu mới.

## Kết nối client

Để đăng nhập từ game, APK Akaine 7.3.1 phải được build cho đúng hostname của server bạn. Nếu chưa có APK phù hợp, dùng các lệnh HTTP ở trên để kiểm server.

Tiếp theo: [Chạy Discord bot tùy chọn](05b-discord-bot.md), rồi
[sao lưu server](05c-backup-recovery.md).
