# Akaine hoạt động như thế nào

[English](../01-architecture.md) | Tiếng Việt

Akaine gồm client Android, server Python, cơ sở dữ liệu và kho nội dung. Chương này giải
thích vai trò của từng phần và cách chúng liên lạc với nhau. Các chương sau tiếp tục dùng
những tên gọi này.

## Năm phần chính

### 1. Client Android

Đây là game cài trên điện thoại hoặc emulator. Hướng dẫn sử dụng bản arm64 Arcaea
`7.0.255` (`1209852`). Client hiển thị menu, phát nhạc và chart, đồng thời gửi request
đăng nhập hoặc score tới server của bạn. APK phải được cấu hình để dùng domain của bạn.

### 2. Game server

Game server là ứng dụng Python chạy trên một máy Linux cloud. Nó xử lý tài khoản, đăng
nhập, quyền sở hữu bài hát, partner, save, score, World Mode và URL tải nội dung.

Hướng dẫn dùng Amazon Lightsail làm máy Linux tính phí theo tháng. Bạn quản trị server
từ xa qua SSH.

### 3. Cơ sở dữ liệu

Server lưu tài khoản, score và tiến trình người chơi trong các file SQLite trên cùng
máy. Bạn không cần cài thêm một dịch vụ database riêng.

Cơ sở dữ liệu là riêng tư. Nó không bao giờ được tải lên GitHub hoặc chia sẻ với bộ tài
nguyên vì nó có thể chứa thông tin người chơi.

### 4. Cloudflare và R2

Cloudflare cung cấp hai dịch vụ tại đây:

- **DNS** kết nối các tên như `api.example.com` với địa chỉ IP server của bạn.
- **R2 object storage** giữ các file lớn như bundle và asset bài hát mà không cần đưa
  chúng vào Git.

Cloudflare cũng proxy HTTPS và cache file công khai tại edge gần người chơi.

### 5. Discord bot

Lygus Bot là thành phần tùy chọn. Bot tạo hoặc liên kết tài khoản, hiển thị profile,
recent play và ảnh B30. Nó chạy trên server và đọc cùng cơ sở dữ liệu game.

## Điều gì xảy ra khi người chơi đăng nhập

1. Client Android gửi yêu cầu HTTPS tới `api.example.com`.
2. DNS cho client biết địa chỉ Cloudflare cần kết nối.
3. Cloudflare chuyển tiếp yêu cầu đến địa chỉ IP cố định của server Lightsail của bạn.
4. nginx nhận được yêu cầu web được mã hóa và chuyển nó đến game server Python chạy
   riêng tư trên cùng một máy.
5. Server Python kiểm tra cơ sở dữ liệu SQLite và gửi phản hồi.
6. Cloudflare trả về phản hồi đó cho client Android.

```text
Android client
      |
      | HTTPS request to api.example.com
      v
Cloudflare DNS and HTTPS proxy
      |
      v
Lightsail fixed IP
      |
      v
nginx -> Python game server -> SQLite database
```

## Điều gì xảy ra khi một bài hát được tải xuống

Với file lớn, game server trả URL tải thay vì tự truyền toàn bộ dữ liệu. Client tải file
từ asset host nối với R2. Protected chart dùng signed URL sống trong thời gian ngắn, vì
vậy người chưa xác thực không thể liệt kê hoặc tải nội dung private.

```text
Client asks game server for a song
      |
Game server checks the account and creates download URLs
      |
Client downloads approved files from assets.example.com / R2
```

## Link Play thì khác

API thông thường dùng HTTPS. Link Play dùng kết nối TCP và UDP trực tiếp cho room thời
gian thực. HTTP proxy miễn phí của Cloudflare không chuyển tiếp các game port này, nên
`link.example.com` phải trỏ thẳng tới Lightsail static IP ở chế độ **DNS only**.

## Các tập tin đến từ đâu

GitHub chứa server, Discord bot, công cụ build và tài liệu. Bộ tài nguyên riêng giữ các
file không thể đưa lên public source repository.

Bạn tự tạo credentials AWS, Cloudflare và Discord trong quá trình setup. Hãy giữ chúng,
database người chơi, log và signing key trên hệ thống mình kiểm soát. Không đưa chúng
lên GitHub hoặc vào bộ tài nguyên dùng chung.

## Trước khi tiếp tục

SQLite database trên Lightsail lưu dữ liệu người chơi. Cloudflare nối domain với server,
R2 giữ bundle và file bài hát, còn Link Play kết nối thẳng tới Lightsail qua TCP/UDP.

Tiếp theo: [Tạo server đám mây và kết nối miền](02-cloud-domain.md).
