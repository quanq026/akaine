# Cài trên máy thật và xác nhận chất lượng

Ngày 26/10/2026, đã cài APK V34 và bundle nguyên chất lượng `.25` qua USB lên
Lenovo TB710FU, Android16. Trước đó máy không còn package Akaine trong user hiện
tại nên đây là cài mới, không thể xác nhận giữ phiên đăng nhập cũ.

Hash APK, manifest `.25`, 20.903 tài nguyên đã giải nén và năm module native
đang nạp đều khớp bản đã duyệt. Catalog có 2.543 bài và 63 pack. Người dùng sau
đó xác nhận âm thanh và hình ảnh lần này không có vấn đề.

Không điền, gửi hoặc đóng màn đăng nhập của người dùng. CLI trên lần mở đầu
chưa đọc được trạng thái; nguyên nhân chưa được kết luận. Không coi lỗi quan
sát này là bằng chứng cài sai bundle.

Đây là cài cache local có checksum, chưa chứng minh downloader native xử lý tổng
bundle trên4GiB. Metadata/audio gốc tải riêng chưa được đưa online; không suy ra
mọi bài/codec đã đạt từ xác nhận nghe/nhìn của người dùng.

[Receipt nhẹ](20261026-physical-install.json). Source của công cụ USB được giữ ở
`operations/usb-bundle/`; media và dữ liệu tài khoản không đưa vào Git.

Lần tạo emu sạch sau đó phát hiện công cụ USB dùng umask mặc định đã tạo
`files/` với quyền 0777; guard CLI từ chối đúng. Công cụ đã sửa tạo mới 0700
và kiểm owner/quyền. Emu được sửa về 0771 rồi khởi động lại; máy thật không bị
khởi động lại hay sửa quyền khi người dùng đang thao tác đăng nhập.
