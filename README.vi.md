# Akaine 7.0.255

[English](README.md) | Tiếng Việt

Akaine là bộ mã nguồn công khai kèm hướng dẫn dựng server và client Android
dựa trên Arcaea 7.0.255. Hướng dẫn bắt đầu từ một máy Windows sạch và một tài
khoản cloud mới. Bạn không cần biết trước về Linux, Cloudflare hay quy trình
build Android.

Toàn bộ hướng dẫn và patch client công khai chỉ dành cho phiên bản `7.0.255`,
version code `1209852`. Các phiên bản Arcaea cũ hơn hoặc mới hơn có file và
native offset khác, vì vậy không thể dùng chung các bước trong repository này.

Repository chứa hướng dẫn, mã nguồn server và công cụ build. APK đầu vào cùng
game content sẽ được cung cấp riêng khi hướng dẫn cần đến chúng.

## Bạn sẽ dựng được gì

Sau khi hoàn thành các chương, bạn sẽ có:

- một Linux server chạy trên Amazon Lightsail
- một tên miền được Cloudflare bảo vệ
- private-server API truy cập qua HTTPS
- kho riêng để lưu bundle và file bài hát
- client Android kết nối tới tên miền của bạn
- Discord bot để quản lý tài khoản và công cụ score
- quy trình sao lưu và khôi phục

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
5. [Cấu hình R2, protected download và cache](docs/guide/vi/05-cloudflare-content.md).
6. [Build, ký và kiểm thử client Android](docs/guide/vi/06-build-android-client.md).
7. [Build, xác minh và phát hành content bundle 7.0.255](docs/guide/vi/07-build-release-content-bundle.md).
8. [Đọc kinh nghiệm và lỗi đã gặp khi xây dựng Akaine](docs/guide/vi/08-lessons-and-failures.md).
9. [Thêm fan chart và đặt nó vào một pack](docs/guide/vi/09-add-fan-chart.md).

Hãy đọc từ chương một và làm theo đúng thứ tự. Mỗi chương phía sau giả định
rằng bạn đã hoàn thành các bước kiểm tra của chương trước.

## Tài nguyên riêng

APK đầu vào, game asset và content bundle được phân phối riêng. Hãy nhận chúng
qua kênh riêng từ chủ dự án hoặc một nguồn được ủy quyền. Bộ tài nguyên có
manifest để bạn kiểm tra từng file trước khi sử dụng.

## Ghi công

Akaine ghi công
[Lost-MSth/Arcaea-server](https://github.com/Lost-MSth/Arcaea-server) như một
nguồn tham khảo upstream cho phần server.

## Giấy phép và quyền sở hữu

Những phần mã nguồn thuộc Akaine được phát hành theo giấy phép MIT. Mã nguồn
của bên thứ ba tiếp tục sử dụng giấy phép gốc của nó. Giấy phép MIT không cấp
quyền phân phối lại game client thương mại, âm nhạc, chart, artwork hoặc tài
sản khác thuộc sở hữu của bên thứ ba. Thông tin ghi công cho các thành phần
bên thứ ba nằm trong [Third-party notices](THIRD_PARTY_NOTICES.md).
