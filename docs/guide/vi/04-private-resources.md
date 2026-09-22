# Nhận và xác minh bộ tài nguyên riêng

[English](../04-private-resources.md) | Tiếng Việt

GitHub chứa mã nguồn và hướng dẫn này. Nội dung trò chơi và content bundle đến từ một bộ
tài nguyên riêng biệt. Chương 6 tải xuống XAPK upstream và build các công cụ trực
tiếp từ các nguồn đã xuất bản của họ.

## Nhận bộ tài nguyên

Nhận bộ tài nguyên riêng và SHA-256 dự kiến từ chủ dự án qua kênh riêng. Không yêu cầu
hoặc đăng tài nguyên này trong GitHub Issue, Discussion, kênh server công khai hay group
chat.

Tải file nén về một vị trí bên ngoài Git repository.

## Kiểm tra file nén đã tải

Nhà cung cấp sẽ gửi SHA-256 dự kiến. Chạy:

```powershell
$kitArchive = Get-Item (Read-Host "Full path to the downloaded kit archive")
Get-FileHash -Algorithm SHA256 $kitArchive.FullName
```

So sánh hash 64 ký tự hoàn chỉnh với giá trị mong đợi. Chữ hoa chữ thường không thành
vấn đề; mọi ký tự phải khớp nhau. Nếu nó khác, hãy xóa file và yêu cầu nhà cung cấp thay
thế đã được xác minh. Không giải nén hoặc chạy nó.

## Trích xuất và xác minh nội dung

Sau khi hash lưu trữ khớp, hãy chọn nơi giải nén nó:

```powershell
$kitRoot = Read-Host "Full path for the extracted kit"
$kitRoot = [IO.Path]::GetFullPath($kitRoot)

Expand-Archive `
  -LiteralPath $kitArchive.FullName `
  -DestinationPath $kitRoot

[Environment]::SetEnvironmentVariable("AKAINE_KIT_ROOT", $kitRoot, "User")
```

Bộ tài nguyên có manifest và script kiểm tra. Chạy command ghi trong `README.txt`. Kết
quả phải xác nhận mọi file được khai báo đều tồn tại, đúng kích thước và đúng SHA-256.

Không tiếp tục nếu quá trình xác minh báo cáo file bị thiếu hoặc không khớp.

## Định cấu hình Apktool

Đặt biến môi trường trỏ tới thư mục vừa giải nén:

```powershell
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$apktool = Join-Path $kitRoot "tools\apktool.jar"

[Environment]::SetEnvironmentVariable(
    "APKTOOL_JAR",
    $apktool,
    "User"
)
```

Đóng và mở lại PowerShell, sau đó chạy quy trình kiểm tra nghiêm ngặt của Android:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Set-Location $repoRoot
python scripts\doctor.py --android
```

Lệnh phải kết thúc bằng `Requested toolchain is ready.` Nếu nó báo thiếu công cụ, hãy
quay lại bước cài đặt phù hợp thay vì tiếp tục.

## Giữ bộ tài nguyên riêng tư

- Không commit bộ tài nguyên vào Git hoặc GitHub.
- Không upload nó lên public file server.
- Không phân phối lại nó trừ khi bạn được sự cho phép của mọi chủ sở hữu có liên quan.
- Không lưu trữ credentials sản xuất hoặc cơ sở dữ liệu người chơi trong cùng một
  thư mục.
- Có quyền truy cập bộ tài nguyên không đồng nghĩa với quyền phân phối lại nội dung.

## Kiểm tra công việc của bạn

- Hash lưu trữ khớp với giá trị mong đợi từ nhà cung cấp.
- Kiểm tra manifest sau giải nén đã pass.
- Bộ tài nguyên nằm ngoài Git repository.
- `AKAINE_KIT_ROOT` trỏ tới thư mục đã giải nén và xác minh.

Các chương sau sẽ chỉ rõ file nào trong bộ tài nguyên được sử dụng. Đừng tự đoán mục
đích hoặc chạy script chưa được hướng dẫn nhắc tới.
