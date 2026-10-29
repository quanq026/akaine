# Checkpoint production: client V36 và base25 chất lượng gốc

[English](production-checkpoint.md) | Tiếng Việt

Trang này xác định checkpoint production của lần cập nhật source công khai.
Mốc tham chiếu là bản đã triển khai ngày 27/10/2026 và các bài kiểm tra emu đã
được ghi nhận. Cập nhật GitHub không triển khai lại server, phát hành bundle
mới, đổi dữ liệu người chơi hay bổ sung kết quả runtime mới.

## Nhận diện bản phát hành

| Thành phần | Checkpoint |
| --- | --- |
| Client build | V36, app `7.0.255`, version code `1209852` |
| Android package | `akai.arc.lmao` |
| APK đã phát hành | `AkaineXD-7.0.255-prod-v36-20261027.apk` |
| APK SHA-256 | `a8b243c59adc527e8fa1ada27a0394979234d345b2063da40fcc2fbcc2ffc5fd` |
| Content production thông thường | `7.0.255.25` |
| Bundle alias production | `7.0.255-prod-original-base25-20261027` |
| Dạng bundle | Full base độc lập, 10 phần CB, tổng tải 4.538.288.896 byte |
| Catalogue lúc triển khai | 2.543 bài và 63 pack |

Base giữ chất lượng tài nguyên gốc và cách Download từng bài. Full base nghĩa
là có thể cài độc lập, không có nghĩa chứa sẵn toàn bộ audio/chart gameplay.
Game media, chart, APK, signing key và build input riêng được cung cấp bên
ngoài Git. Giấy phép source công khai không cấp quyền phân phối những nội dung
đó.

Xem [hồ sơ client đã ký](rebase/RELEASE_PRODUCTION_V36.md),
[hồ sơ triển khai server/content production](../operations/production25-20261027/README.md)
và [kết quả runtime production có giới hạn](performance/20261028-production-v36-runtime.md).
Các checkpoint thử nghiệm sau đó không thuộc bản phát hành này.

## Build client hiện tại

Dùng [production source profile V36](rebase/BUILD_PRODUCTION_V36.md). Core, DEX
và archive đầu vào là APK production V9 thật, phát hành ngày 22/10/2026:

```text
SHA-256 f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545
```

[Chương XAPK cũ](guide/vi/06-build-android-client.md) dùng baseline và patch khác.
Nội dung đó vẫn dành cho bản lịch sử, nhưng không phải công thức V36. Không
thay đầu vào V9 bằng APK staging hay baseline gộp từ XAPK upstream trước đây.

Trước khi build V36, nhận và xác minh đúng bộ source-build input riêng,
toolchain, tham chiếu loader key opaque và local path map qua kênh riêng được
cho phép. Giữ toàn bộ ngoài repository. Profile production mô tả bước tạo
candidate, review, chốt source control, clean rebuild năm payload và kiểm tra
APK đã ký. Binary kết quả dự kiến chỉ dùng làm hash control, không được dùng
làm compiler input. APK ký bằng key của bạn sẽ khác APK đã phát hành và không
thể thay signing identity để cài đè bản đó.

Profile đi kèm giữ các host production Akaine đã phát hành. Nếu dùng server
khác, vẫn cần native route change riêng đã kiểm chứng cho login, aggregate,
content bundle và encrypted shared API base. Chỉ sửa DNS hoặc config server
không thay các route nhúng trong client.

## Điều khiển client production bằng lệnh

V36 có semantic bridge cục bộ. Dùng host client production:

```powershell
adb devices -l
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> status
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> ui list
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> bundle status
python scripts/akaine_cli/akaine_prod.py --serial <adb-serial> account status
```

Thay `<adb-serial>` bằng serial thiết bị ADB trả về. Bốn lệnh này chỉ đọc trạng
thái. Host production từ chối bridge staging; `akaine_stag.py` là host staging
riêng. Dùng `--help` để xem lệnh tìm catalogue, chọn bài/độ khó, pack, nhân vật,
filter, settings, Cloud Sync Download, hướng dẫn đã hỗ trợ và pause gameplay.
Action gọi callback native đã xác minh, không click theo tọa độ hay tạo note,
điểm số tự động.

Với action được cung cấp, đọc lại `ui list` rồi kích hoạt đúng token hiện tại.
Scene đổi, modal chưa biết hoặc listener vô hình chặn input có thể khiến action
bị chặn. Sau timeout, đọc trạng thái mới trước khi thử lại vì chưa chắc thao
tác trước đã thất bại. [Tài liệu hướng dẫn lần đầu](guide/07-staging-semantic-cli.md)
dùng ví dụ staging; trên production đổi sang `akaine_prod.py`. Việc đồng ý
điều khoản là bước tương tác do người dùng xác nhận; quyền Android là lựa chọn
OS riêng. Không đưa credential vào tham số shell, issue công khai hoặc log.

## Server, bot và content là các thành phần riêng

Cây `server/` công khai bắt đầu từ 12 source sibling trong
[archive overlay production25](../operations/production25-20261027/README.md),
với hai ngoại lệ để tích hợp. `tools/create_user_cli.py` giữ helper atomic
`provision_account` đã được chấp nhận và đang được bot công khai sử dụng. Trong
`core/config_manager.py`, năm giá trị identity/secret mặc định được để trống:
`USERNAME`, `PASSWORD`, `SECRET_KEY`, `LINKPLAY_AUTHENTICATION` và
`LINKPLAY_TCP_SECRET_KEY`. Hãy cấp private config của bạn. Archive lịch sử giữ
nguyên byte gốc và hồ sơ redaction hai literal của nó; cây server chính không
khẳng định cả 12 file đều giống từng byte.

Đây là bản xuất source, không phải bản sao deployment hay config đang chạy.
Control pack động và assetset profile trong config mẫu vẫn tắt cho tới khi bạn
cấu hình, kiểm chứng catalogue và client tương ứng. Metadata production,
database và hồ sơ người chơi không được đưa vào repo.

Lần triển khai production đã mang theo xử lý pack động có legacy fallback,
grant nonconsumable cộng thêm, projection tương thích, route Download gốc và
API content bundle không cache. Catalogue, metadata, chart constant, ownership
policy, Worker signing và tài nguyên bot cần input khớp riêng; cài V36 không
cập nhật chúng. Các bản sửa bot công khai hiện tại vẫn có sẵn độc lập với hồ sơ
triển khai server lịch sử.

Nếu cài mới, bắt đầu với [bộ hướng dẫn setup](guide/vi/README.md), rồi dùng trang
này cho client hiện tại và phạm vi source production. [Chương phát hành
content](guide/vi/07-build-release-content-bundle.md) mô tả nguyên tắc build và
kiểm tra full base bất biến. Version và số phần minh họa trong chương là ví dụ;
base25 ở trên có 10 phần. Không ghi đè bundle alias cũ hay xem receipt triển
khai lịch sử là lệnh để chạy lại trên production.

## Giới hạn kiểm chứng

[Hồ sơ kiểm tra bản xuất source](production-source-export.json) đối chiếu 114
đường dẫn source do dự án viết, giữ nguyên byte, và 1.063 input role đã kiểm
local. Có 241 test đạt; một fixture guide native được bỏ qua vì cần compiler
C++ trên host. Lần cập nhật source này không build APK hay kiểm runtime lại
trên thiết bị.

Hồ sơ production đã kiểm login và Cloud Sync Download, điều hướng pack, một số
lượt gameplay official/fan chart, gauge skill nhân vật và giữ login/cache sau
khởi động lại trên emu. Hồ sơ không khẳng định mọi chart đều tương thích, đã
kiểm lại máy thật, hoàn tất bài để kiểm score/PTT hay tăng FPS tổng thể. Ba vùng
lag scene/loading chưa xong vẫn được để lại. Worker loading, preload, ANGLE và
Vulkan thử nghiệm không nằm trong V36.
