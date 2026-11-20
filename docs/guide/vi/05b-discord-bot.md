# Chạy Discord bot

[English](../05b-discord-bot.md) | Tiếng Việt

Bot là thành phần tùy chọn. Nó tạo và liên kết game account, hiển thị recent score,
render B30 và liệt kê toàn bộ player theo bảng xếp hạng phân trang. Hãy hoàn thành cài
game server ở chương 5a trước; bot đọc cùng SQLite database.

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

Các path setting được hỗ trợ là `LYGUS_SERVER_ROOT`, `LYGUS_GAME_DB`,
`LYGUS_MAPPING_DB` và `LYGUS_LOG_PATH`. `LYGUS_B30_GENERATOR` là tùy chọn, mặc
định trỏ tới `tools/b30_generator.py` dưới server root. Bot hiện không dùng
`LYGUS_CREATE_CLI`; hãy bỏ setting cũ đó khỏi private environment file nếu còn.
Không cần subprocess tạo account hay truyền password qua tham số dòng lệnh.

Nếu đang chuyển một DB cũ dùng WAL, bot sẽ từ chối tạo tài khoản qua Discord. Dùng lệnh tạo acc ở chương 5a hoặc liên hệ quản trị viên để kiểm DB trước khi đổi chế độ ghi. Một lần cài mới theo chương 5a không cần bước đổi này.

## Khởi động và kiểm tra

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/lygus-bot.service /etc/systemd/system/lygus-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lygus-bot.service
sudo systemctl is-active lygus-bot.service
```

Service phải báo `active`. Mở Discord và xác nhận bot online. Nếu chưa thấy lệnh, đợi bot đồng bộ rồi thử `/help`.

### Tạo tài khoản đầu tiên

1. Hoàn thành [bước nạp nội dung ở chương 5a](05a-install-game-server.md#3-cung-cấp-content-file-đã-xác-minh). Bot cấp quyền dựa trên danh mục đã nạp vào server của bạn. Với hướng dẫn hiện tại, chọn bộ nội dung 7.1.0. Source 7.3.1 trong repo là bản tham khảo port.
2. Trong Discord, gõ `/create` và nhập tên, mật khẩu trong hộp thoại riêng. Lưu thông tin bot trả về và thử `/profile` để xem acc vừa tạo.
3. Đăng nhập trong game, chọn **Cloud Sync → Download**, rồi kiểm một pack và một nhân vật có trong bộ nội dung của bạn. Nếu thiếu nội dung, quay lại bước nạp dữ liệu ở chương 5a. Phần [kiểm quyền của tài khoản](05a-install-game-server.md#tạo-tài-khoản-và-kiểm-quyền) có lệnh xem thử cho admin.

Dùng `/link` nếu đã có tài khoản. `/profile` và `/recent` nhận tên Akaine hoặc mục `discord_profile`. `/ranking` hiển thị năm người mỗi trang.

Nếu service không active, chỉ kiểm tra status và log gần đây:

```bash
sudo systemctl status lygus-bot.service --no-pager
sudo journalctl -u lygus-bot.service -n 60 --no-pager
```

Không paste token hoặc account log chưa che thông tin lên public issue.

Tiếp theo: [Sao lưu và khôi phục server](05c-backup-recovery.md).
