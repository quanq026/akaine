# Chuẩn bị máy tính Windows của bạn

[English](../03-workstation.md) | Tiếng Việt

Cài đặt các công cụ bên dưới trên Windows 10 hoặc Windows 11. Các lệnh cuối cùng sẽ kiểm
tra quá trình cài đặt trước khi bạn tiếp tục.

## Thời gian, lưu trữ và quyền

- Thời gian: 30 đến 60 phút, chủ yếu là tải xuống.
- Dung lượng đĩa trống: ít nhất 30 GB; 60 GB thoải mái hơn khi rebuild APK và giữ
  Android Emulator.
- Quyền: cần tài khoản Windows có quyền administrator để chạy installer.

## Bước 1: chọn nơi lưu file

Chọn hai thư mục trên bất kỳ ổ đĩa nào có đủ dung lượng trống: một cho Git repository
công khai và một thư mục khác cho các tài nguyên riêng tư. Chúng không được lồng vào
nhau.

Mở PowerShell và dán đường dẫn đầy đủ khi được nhắc:

```powershell
$repoRoot = Read-Host "Full path for the Akaine source folder"
$privateRoot = Read-Host "Full path for the private resource folder"

$repoRoot = [IO.Path]::GetFullPath($repoRoot)
$privateRoot = [IO.Path]::GetFullPath($privateRoot)

New-Item -ItemType Directory -Force $privateRoot | Out-Null
[Environment]::SetEnvironmentVariable("AKAINE_REPO_ROOT", $repoRoot, "User")
[Environment]::SetEnvironmentVariable("AKAINE_PRIVATE_ROOT", $privateRoot, "User")
```

Các biến này cho phép các chương sau sử dụng vị trí bạn đã chọn mà không cần nhập ký tự
ổ đĩa hoặc tên thư mục. Việc tách biệt các thư mục sẽ ngăn chặn một commit Git vô tình
bao gồm các file riêng tư.

## Bước 2: cài đặt Git, Python và Java

Windows bao gồm `winget` trên các bản cài đặt Windows 10/11 hiện tại. Chạy các lệnh này
trong PowerShell:

```powershell
winget install --exact --id Git.Git
winget install --exact --id Python.Python.3.12
winget install --exact --id EclipseAdoptium.Temurin.17.JDK
```

Đóng hoàn toàn PowerShell và mở lại để tải các mục PATH mới.

Kiểm tra các cài đặt:

```powershell
git --version
python --version
java -version
```

Mỗi lệnh phải in một phiên bản thay vì “không được nhận dạng”. Python phải bắt đầu bằng
`3.12` và Java sẽ báo cáo phiên bản `17`.

Nếu `python` mở Microsoft Store, hãy mở **Cài đặt** → **Ứng dụng** → **Cài đặt ứng dụng
nâng cao** → **Bí danh thực thi ứng dụng**, sau đó tắt bí danh Store cho `python.exe` và
`python3.exe`. Mở lại PowerShell và thử lại.

## Bước 3: cài đặt công cụ Android Studio và SDK

1. Tải xuống và cài đặt Android Studio từ trang web chính thức của nhà phát triển
   Android. Giữ các tùy chọn cài đặt tiêu chuẩn.
2. Khởi động Android Studio.
3. Trên màn hình chào mừng, chọn **Tác vụ khác** → **Trình quản lý SDK**. Nếu một dự án
   đang mở, hãy sử dụng **Công cụ** → **Trình quản lý SDK**.
4. Trên **Nền tảng SDK**, hãy cài đặt ít nhất một nền tảng Android ổn định.
5. Trong **SDK Tools**, bật:
   - Android SDK Build-Tools
   - Android SDK Platform-Tools
   - Android SDK Command-line Tools (latest)
   - Android Emulator nếu không dùng điện thoại thật
6. Chọn **Áp dụng**, chấp nhận giấy phép và chờ cài đặt.
7. Sao chép **Vị trí SDK Android** hiển thị ở trên cùng.

Đặt các biến môi trường bằng đường dẫn đó. Lệnh sau yêu cầu điều đó thay vì giả sử
Android Studio đã cài đặt SDK ở đâu:

```powershell
$sdk = Read-Host "Android SDK Location shown by Android Studio"
$sdk = [IO.Path]::GetFullPath($sdk)
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $sdk, "User")
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";$sdk\platform-tools;$sdk\emulator",
    "User"
)
```

Đóng và mở lại PowerShell, sau đó chạy:

```powershell
adb version
```

## Bước 4: clone source Akaine

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
git clone https://github.com/quanq026/akaine.git $repoRoot
Set-Location $repoRoot
```

Bây giờ bạn sẽ thấy `README.md`, `server`, `scripts` và `docs`:

```powershell
Get-ChildItem
```

## Bước 5: xác nhận các thư mục riêng biệt

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$privateRoot = [Environment]::GetEnvironmentVariable("AKAINE_PRIVATE_ROOT", "User")
Get-Item $repoRoot, $privateRoot
```

Cả hai con đường phải tồn tại và phải khác nhau. Thư mục riêng không được nằm trong kho
lưu trữ.

## Bước 6: chạy kiểm tra môi trường cơ bản

Đóng và mở lại PowerShell, sau đó chạy:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Set-Location $repoRoot
python scripts\doctor.py
```

Máy trạm lõi đã được chuẩn bị sẵn in `OK` cho `git` và `python`. Lệnh này cũng báo cáo
các công cụ Android tùy chọn tìm thấy trên máy. Apktool sẽ chưa có ở lần kiểm tra
đến chương tài nguyên riêng tư.

Danh sách công cụ Android hoàn chỉnh là:

```text
git
python
node
npm
java
adb
zipalign
apksigner
apktool
```

Nếu thiếu `zipalign` hoặc `apksigner`, hãy quay lại Trình quản lý SDK của Android Studio
và cài đặt Công cụ build SDK Android. Chương tiếp theo bổ sung Apktool và chạy kiểm
tra nghiêm ngặt.

## Bước 7: chuẩn bị môi trường Python

Từ thư mục repository:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Set-Location $repoRoot
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Xác minh việc kiểm tra nguồn công khai:

```powershell
.\.venv\Scripts\python scripts\ci_public_repo_check.py
.\.venv\Scripts\python -m compileall -q server scripts
```

Lệnh đầu tiên sẽ kết thúc bằng `Public repository check passed`. Lệnh thứ hai thường
không in gì khi quá trình biên dịch thành công.

## Kiểm tra công việc của bạn

- Các thư mục nguồn và tài nguyên riêng tồn tại ở vị trí bạn đã chọn.
- Thư mục tài nguyên riêng nằm ngoài kho Git.
- `doctor.py` báo cáo chính xác tất cả các công cụ có sẵn.
- Phiên bản in Git, Python 3.12, Java 17 và adb.
- Môi trường Python cài đặt thành công.
- Kiểm tra nguồn công khai và biên dịch Python.

## Xóa thiết lập cục bộ

1. Xóa `.venv` trong repository nếu muốn gỡ Python environment của dự án.
2. Xóa repository nếu không muốn giữ source.
3. Giữ hoặc xóa thư mục tài nguyên riêng theo quyền lưu trữ mà bạn được cấp.
4. Nếu không còn cần, gỡ Android Studio, Git, Python hoặc Java trong Windows Settings.

Tiếp theo: [Nhận và xác minh bộ tài nguyên riêng](04-private-resources.md).
