# Chuẩn bị client Arcaea 7.3.1

[English](../06-build-android-client.md) | Tiếng Việt

1. [Tải XAPK ARM64 từ APKPure](https://d.apkpure.net/b/XAPK/moe.low.arc?versionCode=1210500&nc=arm64-v8a&sv=24). Chọn bản **7.3.1 (1210500)**.
2. Chuẩn bị Python, Java 17 và APKEditor 1.4.9 theo [chương công cụ](03-workstation.md).
3. Mở PowerShell ở thư mục repo rồi chạy lệnh dưới đây. Dán đường dẫn file khi lệnh hỏi.

```powershell
$source = Read-Host "Path to the downloaded ARM64 XAPK"
$editor = Read-Host "Path to APKEditor-1.4.9.jar"
$java = (Get-Command java.exe).Source
$output = Join-Path $env:USERPROFILE ("Akaine-7.3.1-input-" + (Get-Date -Format yyyyMMdd-HHmmss))
python -m akaine_build.android --source $source --java $java --apkeditor $editor --output $output
```

Khi thấy `Verified original APK`, thư mục đầu ra đã có `merged.apk` đúng SHA-256. Đây là APK gốc đã gộp. Repo hiện cung cấp [mã patch Android, native và CLI](../../../patches/arcaea-7.3.1-arm64/); bước áp patch và ký APK Akaine từ source chưa có lệnh public hoàn chỉnh. Nếu bạn đã có client Akaine 7.3.1 phù hợp, xem [cách cài server](05a-install-game-server.md).
