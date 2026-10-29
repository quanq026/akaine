# Akaine 7.0.255

[English](README.md) | Tiếng Việt

![Akaine](docs/images/akaine-hero.png)

<p align="center">
  <a href="https://github.com/quanq026/akaine/releases/latest"><img alt="Bản phát hành mới nhất" src="https://img.shields.io/github/v/release/quanq026/akaine?style=flat&amp;label=Release&amp;color=A63B52"></a>
  <a href="docs/guide/vi/06-build-android-client.md"><img alt="Arcaea 7.0.255" src="https://img.shields.io/badge/Arcaea-7.0.255-547EA8?style=flat"></a>
  <a href="https://github.com/quanq026/akaine/releases/latest"><img alt="Android arm64" src="https://img.shields.io/badge/Android-arm64-3DDC84?style=flat&amp;logo=android&amp;logoColor=white"></a>
  <a href="https://github.com/quanq026/akaine/search?l=python"><img alt="Python và C++" src="https://img.shields.io/badge/Code-Python%20%2B%20C%2B%2B-3776AB?style=flat"></a>
  <br>
  <a href="README.md"><img alt="Hướng dẫn tiếng Anh và tiếng Việt" src="https://img.shields.io/badge/Docs-EN%20%2F%20VI-547EA8?style=flat"></a>
  <a href="https://discord.gg/9BBXhX7DkN"><img alt="Tham gia Discord" src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&amp;logo=discord&amp;logoColor=white"></a>
  <a href="https://github.com/quanq026/akaine/stargazers"><img alt="Số sao GitHub" src="https://img.shields.io/github/stars/quanq026/akaine?style=flat&amp;color=D5A64E&amp;logo=github"></a>
  <a href="LICENSE"><img alt="Giấy phép MIT" src="https://img.shields.io/github/license/quanq026/akaine?style=flat&amp;color=6B7280"></a>
</p>

<p align="center">
  <strong><a href="https://github.com/quanq026/akaine/releases/latest">Tải APK</a></strong> ·
  <a href="docs/guide/vi/README.md">Bắt đầu hướng dẫn</a> ·
  <a href="https://discord.gg/9BBXhX7DkN">Discord</a>
</p>

Akaine là bộ mã nguồn công khai kèm hướng dẫn dựng server và client Android
dựa trên Arcaea 7.0.255. Hướng dẫn bắt đầu từ một máy Windows sạch và một tài
khoản cloud mới. Bạn không cần biết trước về Linux, Cloudflare hay quy trình
build Android.

Toàn bộ hướng dẫn và patch client công khai chỉ dành cho phiên bản `7.0.255`,
version code `1209852`. Các phiên bản Arcaea cũ hơn hoặc mới hơn có file và
native offset khác, vì vậy không thể dùng chung các bước trong repository này.

Repository chứa hướng dẫn, mã nguồn server và công cụ build. Tải client gốc
từ APKPure; content và đầu vào chart key tương ứng được cung cấp riêng khi cần.

## Client hiện tại: V36

[Chương 6](docs/guide/vi/06-build-android-client.md) bắt đầu từ XAPK arm64
7.0.255 gốc của APKPure. Sau khi thiết lập công cụ/key một lần, một lệnh sẽ
merge, patch, build và ký V36. Không cần APK Akaine đã patch hoặc path map
của người phát triển. Media gốc được giữ nguyên; content `7.0.255.25` được
phân phối riêng. APK, key và game content nằm ngoài Git.

Native patch 7.0.255 đi kèm dùng các Akaine API host đã phát hành. Client dùng domain
khác còn cần native route change được kiểm chứng; public repository hiện chưa có command
đổi host tổng quát. Chương server có bước kiểm tra HTTP độc lập cho domain của bạn.

## Bạn sẽ dựng được gì

Sau khi hoàn thành các chương, bạn sẽ có:

- một Linux server chạy trên Amazon Lightsail
- một tên miền được Cloudflare bảo vệ
- private-server API truy cập qua HTTPS
- kho riêng để lưu bundle và file bài hát
- client Android V36 được build từ gói APKPure gốc
- Discord bot để quản lý tài khoản và công cụ score
- quy trình sao lưu và khôi phục

![Tổng quan nền tảng Akaine 7.0.255](docs/images/akaine-platform-overview.svg)

## Trước khi bắt đầu

Bạn nên dành trọn một buổi cho lần setup đầu tiên. Cần chuẩn bị:

- máy Windows 10 hoặc Windows 11 còn trống ít nhất 30 GB
- điện thoại Android hoặc máy tính đủ khả năng chạy Android Emulator
- thẻ thanh toán được AWS và nhà đăng ký tên miền chấp nhận
- email do bạn quản lý và có thể bảo vệ bằng xác thực hai lớp
- bộ tài nguyên riêng của Akaine cùng mã SHA-256 để kiểm tra file

Khách hàng AWS mới có thể nhận tối đa 200 USD credit trong sáu tháng. Khoản
này đủ để chạy Lightsail trong giai đoạn setup ban đầu. Công dân Việt Nam từ
18 đến 23 tuổi cũng có thể đủ điều kiện đăng ký miễn phí một tên miền `.id.vn`
trong hai năm qua các nhà đăng ký `.vn` tham gia chương trình như iNET. Tên
miền khuyến mãi có thể bắt đầu ở khoảng 40.000 VND, nhưng hãy kiểm tra cả phí
gia hạn trước khi mua.

Cloudflare DNS, CDN và SSL dùng gói Free. R2 miễn phí 10 GB Standard storage
mỗi tháng; dung lượng vượt mức hiện có giá 0,015 USD cho mỗi GB-tháng. Một hệ
thống nhỏ thường tốn dưới 1 USD mỗi tháng cho R2, trừ khi bạn giữ nhiều bản
release trùng nhau hoặc phục vụ lượng tải lớn.

Khi AWS credit hết hạn, bạn có thể tiếp tục trả phí cho Lightsail hoặc chuyển
hệ thống sang nhà cung cấp VPS khác.

## Bắt đầu hướng dẫn

1. [Tìm hiểu hệ thống hoạt động như thế nào](docs/guide/vi/01-architecture.md).
2. [Tạo cloud server và kết nối tên miền](docs/guide/vi/02-cloud-domain.md).
3. [Chuẩn bị máy Windows](docs/guide/vi/03-workstation.md).
4. [Nhận và kiểm tra bộ tài nguyên riêng](docs/guide/vi/04-private-resources.md).
5. [Cấu hình R2](docs/guide/vi/05-cloudflare-content.md), [cài game server](docs/guide/vi/05a-install-game-server.md), [chạy Discord bot tùy chọn](docs/guide/vi/05b-discord-bot.md) và [thiết lập backup](docs/guide/vi/05c-backup-recovery.md).
6. [Build, ký và kiểm thử client Android](docs/guide/vi/06-build-android-client.md).
7. [Build, xác minh và phát hành content bundle 7.0.255](docs/guide/vi/07-build-release-content-bundle.md).
8. [Đọc kinh nghiệm và lỗi đã gặp khi xây dựng Akaine](docs/guide/vi/08-lessons-and-failures.md).
9. [Thêm fan chart và đặt nó vào một pack](docs/guide/vi/09-add-fan-chart.md).

Hãy đọc từ chương một và làm theo đúng thứ tự. Mỗi chương phía sau giả định
rằng bạn đã hoàn thành các bước kiểm tra của chương trước.

## Tài nguyên riêng

Tải client chưa sửa từ link APKPure trong chương 6. Nhận content catalogue,
đầu vào AKFC và game content tương ứng qua kênh riêng từ chủ dự án hoặc một
nguồn được ủy quyền. Bộ tài nguyên riêng có manifest để kiểm tra từng file
trước khi sử dụng.

## Ghi công

Akaine ghi công
[Lost-MSth/Arcaea-server](https://github.com/Lost-MSth/Arcaea-server) như một
nguồn tham khảo upstream cho phần server.

## Giấy phép và quyền sở hữu

Những phần mã nguồn thuộc Akaine được phát hành theo giấy phép MIT. Mã nguồn
của bên thứ ba tiếp tục sử dụng giấy phép gốc của nó. Giấy phép MIT không cấp
quyền phân phối lại game client thương mại, âm nhạc, chart, artwork hoặc tài
sản khác thuộc sở hữu của bên thứ ba.
