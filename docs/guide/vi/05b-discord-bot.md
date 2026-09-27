# Chạy Discord bot

[English](../05b-discord-bot.md) | Tiếng Việt

Bot là thành phần tùy chọn. Nó tạo và liên kết game account, hiển thị recent score và
render B30. Hãy hoàn thành cài game server ở chương 5a trước; bot đọc cùng SQLite
database.

## Tạo Discord application

1. Mở [Discord Developer Portal](https://discord.com/developers/applications) và tạo
   application cho server của bạn.
2. Mở phần **Bot** rồi tạo hoặc reset bot token. Lưu token trong password manager;
   Discord có thể chỉ hiển thị nó một lần.
3. Trong phần cài đặt installation của application, cho phép cài vào server của bạn với
   scope `bot` và `applications.commands`. Chỉ cấp quyền xem channel, gửi message và
   embed link mà bot cần.
4. Dùng installation link để thêm bot vào Discord server test.

[Tài liệu application command của Discord](https://docs.discord.com/developers/docs/interactions/slash-commands)
giải thích lý do cần scope `applications.commands`. Token là password của bot, không
phải application ID công khai.

## Cấu hình bot trên Lightsail

Trong Linux SSH terminal, copy environment example:

```bash
sudo install -o akaine -g akaine -m 0600 /srv/akaine/repo/server/.env.example /srv/akaine/repo/server/.lygus.env
sudo -u akaine nano /srv/akaine/repo/server/.lygus.env
```

Đặt bot token sau `LYGUS_BOT_TOKEN=`. Kiểm tra mọi path bắt đầu bằng
`/srv/akaine/repo/server`; example đã dùng layout này. Thay `api.example.com` bằng API
hostname của bạn. Lưu và đóng editor.

Kiểm tra token field có giá trị mà không hiển thị nó:

```bash
sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('/srv/akaine/repo/server/.lygus.env')
rows = dict(line.split('=', 1) for line in path.read_text().splitlines()
            if line and not line.startswith('#') and '=' in line)
assert rows.get('LYGUS_BOT_TOKEN'), 'Bot token is empty'
assert Path(rows['LYGUS_GAME_DB']).is_file(), 'Game database is missing'
print('Discord bot environment ready')
PY
```

Game server phải khởi động ít nhất một lần để database tồn tại.

## Khởi động và kiểm tra

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/lygus-bot.service /etc/systemd/system/lygus-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lygus-bot.service
sudo systemctl is-active lygus-bot.service
```

Service phải báo `active`. Mở Discord và xác nhận bot online. Slash command được sync
khi bot khởi động; có thể cần chờ để chúng xuất hiện. Test `/help`, sau đó tạo hoặc
liên kết test account rồi chạy `/profile`. Với account mới, làm theo ghi chú của bot:
dùng **Cloud Sync → Download** trong game.

Nếu service không active, chỉ kiểm tra status và log gần đây:

```bash
sudo systemctl status lygus-bot.service --no-pager
sudo journalctl -u lygus-bot.service -n 60 --no-pager
```

Không paste token hoặc account log chưa che thông tin lên public issue.

Tiếp theo: [Sao lưu và khôi phục server](05c-backup-recovery.md).
