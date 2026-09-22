# Thiết lập Akaine 7.0.255 từ đầu

[English](../README.md) | Tiếng Việt

Bộ hướng dẫn này giúp bạn build server Akaine và client Android cho Arcaea `7.0.255`
(`1209852`) từ đầu. Các chương dùng chung một bộ tên ví dụ và phải được làm theo thứ tự,
vì mỗi chương sau dựa trên kết quả kiểm tra của chương trước. Không dùng hash hoặc APK
patch trong hướng dẫn cho phiên bản client khác.

## Ví dụ được sử dụng trong hướng dẫn

Thay thế các ví dụ này bằng các giá trị của riêng bạn khi được hướng dẫn:

| Mục | Ví dụ |
| --- | --- |
| Tên miền | `example.com` |
| API trò chơi | `api.example.com` |
| Link Play host | `link.example.com` |
| Asset host | `assets.example.com` |
| Lightsail instance | `akaine-server` |
| Lightsail region | Singapore (`ap-southeast-1`) |

Đừng đăng ký `example.com`; tên này được dành riêng cho tài liệu ví dụ.

## Cách dùng guide nếu bạn là người mới

Hãy giữ trang này mở và hoàn thành từng chương theo thứ tự. Không copy toàn bộ command
trong guide vào một terminal cùng lúc. Mỗi command thuộc một trong ba nơi:

- **PowerShell** là cửa sổ Windows PowerShell trên máy của bạn;
- **server shell** là Linux terminal sau khi kết nối SSH tới Lightsail;
- **Cloudflare/AWS dashboard** là thao tác trên các control được gọi tên trong trình
  duyệt, không phải nhập các nhãn đó vào terminal.

Khi command đặt câu hỏi, chỉ nhập giá trị được yêu cầu. Những chuỗi như `example.com`,
`ACCOUNT_ID` và `MANIFEST-FILENAME` là placeholder cho tới khi bước đó yêu cầu thay.
Giữ cùng một cửa sổ PowerShell trong khi chương còn dùng các biến bắt đầu bằng `$`. Nếu
đóng cửa sổ, file vẫn còn trên ổ đĩa nhưng bạn phải chạy lại block đặt biến của chương.

Mỗi bước xác minh là một stop gate. Nếu giá trị hiển thị khác, command trả exit code
khác không hoặc thiếu file bắt buộc, hãy dừng ở bước đó. Lưu lỗi đầu tiên trước khi thử
lại. File được tạo bởi command thất bại không chứng minh bước đó đã thành công.

## Phần 1: nền tảng

1. [Hiểu cách hoạt động của Akaine](01-architecture.md).
2. [Tạo AWS, Lightsail, Cloudflare và DNS](02-cloud-domain.md).
3. [Chuẩn bị máy tính Windows](03-workstation.md).
4. [Nhận và xác minh bộ tài nguyên riêng](04-private-resources.md).
5. [Cấu hình R2, protected download và cache](05-cloudflare-content.md).

Kết thúc phần 1, bạn sẽ có các tài khoản cloud đã được bảo vệ, server Lightsail với IP
cố định, DNS Cloudflare và đủ công cụ cần thiết trên Windows.

## Phần 2: Client Android

6. [Build, ký và kiểm tra client Android](06-build-android-client.md).

Chương 6 build và kiểm thử client Android từ XAPK upstream đã xác minh cùng source patch
trong repository này.

## Phần 3: phát hành content

7. [Build, xác minh và phát hành content bundle](07-build-release-content-bundle.md).

Chương 7 bắt đầu từ full-root bundle 7.0.255 đã xác minh, áp dụng overlay có kiểm soát,
kiểm thử trên staging rồi đưa đúng bộ byte bất biến đó lên production.

## Phần 4: kinh nghiệm vận hành

8. [Kinh nghiệm và lỗi đã gặp khi xây dựng Akaine 7.0.255](08-lessons-and-failures.md).

Chương 8 giải thích những sự cố đã tạo nên các bước kiểm tra trong guide: API đi sai
route, bundle boot loop, selector gate, download contract, false positive từ emulator,
chẩn đoán CDN và rollback release.

## Phần 5: mở rộng catalogue

9. [Thêm fan chart và đặt nó vào một pack](09-add-fan-chart.md).

Chương 9 giải thích cách một fan chart đi qua pack/song catalogue, selector asset, AKFC
encryption, protected R2 delivery, server metadata, chart constant, staging và runtime
check cuối.
