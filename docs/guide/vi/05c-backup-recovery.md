# Sao lưu và khôi phục game server

[English](../05c-backup-recovery.md) | Tiếng Việt

Dùng chương này sau khi game server đã chạy. Nó bảo vệ player data và cấu hình cần để
khởi động lại cùng release. Command dùng layout `/srv/akaine/repo/server` từ chương 5a.

## Backup chứa gì

Archive chứa thư mục `database/` của server, private `config.py`, environment file
chứa signing secret và bot environment file nếu có. Nó không chứa Git source, APK hoặc
R2 object. Ghi Git commit cùng bundle alias bên cạnh archive. Giữ một bản R2 content
hoặc private resource kit đã xác minh để khôi phục CDN object.
Đặt `/srv/akaine/backups` trên private storage và theo dõi dung lượng; mỗi archive chứa
đầy đủ database và catalogue file.

## Tạo local archive nhất quán

Trong Linux SSH terminal, dừng process ghi dữ liệu khi copy SQLite database:

```bash
set -e
sudo systemctl stop lygus-bot.service 2>/dev/null || true
sudo systemctl stop arcaea-server.service

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/srv/akaine/backups/server-$stamp.tar.gz"
sudo install -d -o root -g root -m 0700 /srv/akaine/backups
cd /srv/akaine/repo/server
files='database config.py .asset-signing.env'
if [ -f .lygus.env ]; then files="$files .lygus.env"; fi
sudo tar -czf "$backup" $files
sudo chmod 0600 "$backup"
sudo tar -tzf "$backup" >/dev/null
sudo sha256sum "$backup"
git -C /srv/akaine/repo rev-parse HEAD

sudo systemctl start arcaea-server.service
if [ -f .lygus.env ]; then sudo systemctl start lygus-bot.service; fi
curl --fail --silent --show-error http://127.0.0.1:18080/
printf 'Backup: %s\n' "$backup"
```

HTTP check cuối phải trả `Hello World!`. Ghi archive path, SHA-256 và Git commit. Nếu
`tar` lỗi, giữ service ở trạng thái dừng cho tới khi hiểu database file còn nguyên hay
không; không gọi partial archive là backup.

Copy archive ra khỏi server. Bản copy tạm sau chỉ SSH user của bạn đọc được:

```bash
sudo install -d -o ubuntu -g ubuntu -m 0700 /home/ubuntu/akaine-intake
sudo install -o ubuntu -g ubuntu -m 0600 "$backup" "/home/ubuntu/akaine-intake/$(basename "$backup")"
```

Trong Windows PowerShell, dùng private folder đã chọn ở chương 3:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the Lightsail SSH private key")
$serverIp = Read-Host "Lightsail static IPv4 address"
$privateRoot = [Environment]::GetEnvironmentVariable("AKAINE_PRIVATE_ROOT", "User")
$backupName = Read-Host "Backup filename printed by the server"
$localBackup = Join-Path $privateRoot $backupName

scp -i $sshKey.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$backupName" $localBackup
if ($LASTEXITCODE -ne 0) { throw "Off-server backup transfer failed." }
Get-FileHash -Algorithm SHA256 $localBackup
```

So sánh đầy đủ hash với output Linux. Giữ archive trên private disk hoặc dịch vụ backup
được mã hóa. Nó chứa player data và secret.

## Khôi phục sau thay đổi lỗi

Restore thay database và private configuration hiện tại. Dùng backup do chính bạn tạo,
kiểm tra SHA-256 và giữ bản copy riêng của trạng thái hiện tại trước khi restore. Trong
Linux terminal, đặt đúng archive path đã xác minh:

```bash
read -r -p 'Full path to the verified backup archive: ' backup
test -f "$backup"
sudo /srv/akaine/repo/.venv/bin/python - "$backup" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], 'r:gz') as archive:
    names = set()
    for entry in archive:
        path = PurePosixPath(entry.name)
        if (entry.name.startswith('/') or '..' in path.parts or
                not (entry.isfile() or entry.isdir()) or
                (path.parts[0] != 'database' and entry.name not in
                 {'config.py', '.asset-signing.env', '.lygus.env'})):
            raise SystemExit(f'Unexpected archive entry: {entry.name}')
        names.add(entry.name)
    if not {'database', 'config.py', '.asset-signing.env'} <= names:
        raise SystemExit('Backup is missing a required entry')
print('Backup entries verified')
PY
```

Chỉ tiếp tục nếu thấy `Backup entries verified`. Lệnh kiểm tra mọi entry, kể cả loại
file và path, trước khi ghi đè dữ liệu. Sau đó dừng hai service và restore:

```bash
set -e
sudo systemctl stop lygus-bot.service 2>/dev/null || true
sudo systemctl stop arcaea-server.service
sudo tar --no-same-owner --no-same-permissions -C /srv/akaine/repo/server -xzf "$backup"
sudo chown -R akaine:akaine /srv/akaine/repo/server/database
sudo chown akaine:akaine /srv/akaine/repo/server/config.py /srv/akaine/repo/server/.asset-signing.env
sudo chmod 0600 /srv/akaine/repo/server/config.py /srv/akaine/repo/server/.asset-signing.env
if [ -f /srv/akaine/repo/server/.lygus.env ]; then
  sudo chown akaine:akaine /srv/akaine/repo/server/.lygus.env
  sudo chmod 0600 /srv/akaine/repo/server/.lygus.env
fi

sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
for path in sorted(root.glob('*.db')):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', path
    print(path.name, 'ok')
PY

sudo systemctl start arcaea-server.service
if [ -f /srv/akaine/repo/server/.lygus.env ]; then sudo systemctl start lygus-bot.service; fi
curl --fail --silent --show-error http://127.0.0.1:18080/
```

SQLite check phải báo `ok`, HTTP check trả `Hello World!`. Archive không thể sửa R2
object bị thiếu. Hãy khôi phục chúng từ resource kit đã xác minh hoặc bucket backup
khác, rồi lặp lại CDN check ở chương 5.

Tiếp theo: [Build client Android](06-build-android-client.md).
