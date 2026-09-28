# Cài game server 7.0.255

[English](../05a-install-game-server.md) | Tiếng Việt

Chương này biến Lightsail instance còn rỗng từ chương 2 thành game API đang chạy.
Nó dùng public server source và content file đã xác minh ở chương 4. Hãy hoàn thành
thiết lập R2 và Worker trong chương 5 trước. Database mới bắt đầu khi chưa có game
account. Chương 5b giải thích cách tạo account bằng Discord bot tùy chọn; game cũng có
registration endpoint thông thường.

Android patch công khai ở chương 6 chứa các API host cố định của bản release. Nếu dùng
domain khác, các native route cũng phải được patch và kiểm chứng cho host đó. Chạy chương
này ở `api.example.com` chứng minh server hoạt động; việc đó chưa làm APK AkaineXD đã
phát hành kết nối tới `api.example.com`.

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
7.0.255 full-root manifest   -> database/bundle/<alias>.json
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
$bundleManifest = Get-Item (Read-Host "Full path to the verified 7.0.255 bundle manifest")

ssh -i $sshKey.FullName "ubuntu@$serverIp" "install -d -m 700 /home/ubuntu/akaine-intake"
if ($LASTEXITCODE -ne 0) { throw "Could not create the private intake folder." }

scp -i $sshKey.FullName $songlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/songlist"
if ($LASTEXITCODE -ne 0) { throw "Songlist upload failed." }
scp -i $sshKey.FullName $songMetadata.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/song_metadata.json"
if ($LASTEXITCODE -ne 0) { throw "Song metadata upload failed." }
scp -i $sshKey.FullName $bundleManifest.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$($bundleManifest.Name)"
if ($LASTEXITCODE -ne 0) { throw "Bundle manifest upload failed." }

"Bundle manifest name: $($bundleManifest.Name)"
```

Quay lại Linux SSH terminal và nhập manifest filename mà PowerShell vừa in:

```bash
set -e
read -r -p 'Bundle manifest filename: ' manifest_name
case "$manifest_name" in
  *[!A-Za-z0-9._-]*|'') echo 'Invalid filename' >&2; false ;;
esac
test -f "/home/ubuntu/akaine-intake/$manifest_name"

sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/songlist /srv/akaine/repo/server/database/songs/songlist
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/song_metadata.json /srv/akaine/repo/server/database/song_metadata.json
sudo install -o akaine -g akaine -m 0644 "/home/ubuntu/akaine-intake/$manifest_name" "/srv/akaine/repo/server/database/bundle/$manifest_name"
sudo -u akaine /srv/akaine/repo/.venv/bin/python - "$manifest_name" <<'PY'
import json, sys
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
manifest = root / 'bundle' / sys.argv[1]
data = json.loads(manifest.read_text())
assert data['applicationVersionNumber'] == '7.0.255'
assert data['previousVersionNumber'] is None
assert data['totalPartitions'] > 0
json.loads((root / 'songs/songlist').read_text(encoding='utf-8-sig'))
json.loads((root / 'song_metadata.json').read_text())
print('7.0.255 content files ready')
PY
```

Server đọc songlist để quyết định unlock và download, metadata để lấy download filename
và checksum, manifest để lấy bundle version và part URL. Chỉ cài manifest sẽ không làm
song download hoạt động.
Lệnh cuối phải in `7.0.255 content files ready`.

## 4. Cấu hình server 7.0.255

Copy example dành riêng cho phiên bản này. Credential nằm trong `config.py` được Git
ignore, bên trong `class Config`:

```bash
sudo -u akaine cp /srv/akaine/repo/server/config.7.0.255.example.py /srv/akaine/repo/server/config.py
sudo chmod 0600 /srv/akaine/repo/server/config.py
sudo -u akaine nano /srv/akaine/repo/server/config.py
```

Tạo ba giá trị khác nhau trong password manager rồi đặt `USERNAME`, `PASSWORD` và
`SECRET_KEY` trong editor. Lệnh `chmod` chỉ cho chủ file đọc cấu hình trước khi bạn
nhập credential. Thay mọi URL `assets.example.com` bằng R2 custom domain thật.
Với protected song, lấy đúng song ID từ private R2 `asset-manifest.json` và thêm vào
`ASSET_SIGNING_SONG_IDS`; giữ các ID hiện có khi sửa list. Template tắt Link Play cho
lần kiểm tra server đầu tiên.

Template đặt `GAME_API_PREFIX = '/'`, khớp root path của release hiện tại như
`/auth/login` và `/game/content_bundle`. Nó chỉ nhận `7.0.255`, lắng nghe
`127.0.0.1:18080` sau nginx và chọn full-root bundle mới nhất cho client cũ. File
`config.example.py` cũ là upstream reference cho client version khác; đừng copy nó cho
setup này.

Kiểm tra file đã sửa mà không in secret:

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
from config import Config
assert Config.GAME_API_PREFIX == '/'
assert Config.ALLOW_APPVERSION == ['7.0.255']
assert Config.USERNAME and Config.PASSWORD and Config.SECRET_KEY
assert 'example.com' not in Config.BUNDLE_DOWNLOAD_LINK_PREFIX
assert 'example.com' not in Config.ASSET_SIGNED_PREFIX
print('7.0.255 server configuration ready')
PY
```

Nếu có traceback, sửa `config.py` rồi kiểm tra lại. Server chưa chạy nên chưa cần restart.

## 5. Dùng cùng Worker signing secret

Dùng secret file đã tạo ở chương 5. Trong Windows PowerShell, chuyển giá trị qua SSH
standard input; lệnh không hiển thị nội dung:

```powershell
$secretFile = Get-Item (Read-Host "Full path to the signing-secret file from chapter 5")
$secretValue = (Get-Content -LiteralPath $secretFile.FullName -Raw).Trim()
if ([Convert]::FromBase64String($secretValue).Length -ne 32) {
  throw "The signing secret is not 32 bytes."
}

("ASSET_SIGNING_SECRET=" + $secretValue) |
  ssh -i $sshKey.FullName "ubuntu@$serverIp" "umask 077; cat > /home/ubuntu/akaine-intake/asset-signing.env"
if ($LASTEXITCODE -ne 0) { throw "Signing-secret transfer failed." }
```

Trong Linux terminal:

```bash
set -e
sudo install -o akaine -g akaine -m 0600 /home/ubuntu/akaine-intake/asset-signing.env /srv/akaine/repo/server/.asset-signing.env
sudo stat -c '%a %U %G %n' /srv/akaine/repo/server/.asset-signing.env
```

Kết quả phải bắt đầu bằng `600 akaine akaine`. Systemd service đọc environment file
này; public `config.py` template không chứa signing secret. Không in environment file.

## 6. Khởi động service và kiểm tra HTTP local

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

## 7. Đặt nginx và HTTPS trước service

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
  AppVersion = '7.0.255'
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
  throw "A fresh 7.0.255 client did not receive one bundle."
}

$body.value.orderedResults | Select-Object contentBundleVersion, appVersion, bundleSize

$targetVersion = $body.value.orderedResults[0].contentBundleVersion
$currentResponse = Invoke-RestMethod -Uri $bundleUrl -Headers @{
  AppVersion = '7.0.255'
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

## Điểm dừng về client host

Native plan trong public repository này nhúng sẵn các Akaine API host đã phát hành.
Server trên hostname riêng có thể pass toàn bộ HTTP test ở trên, nhưng APK đó vẫn gọi
host đã nhúng. Trước khi test client với server của bạn, hãy kiểm tra native route đích
và build một route patch có guard theo phiên bản cho hostname riêng, gồm encrypted
shared API base. Chương 6 giải thích vì sao login thành công chưa chứng minh mọi route
đã đổi. Repository hiện chưa có command tổng quát để thay host; dừng tại mức xác minh
server cho tới khi patch đó được build và test.

Tiếp theo: [Chạy Discord bot tùy chọn](05b-discord-bot.md), rồi
[sao lưu server](05c-backup-recovery.md).
