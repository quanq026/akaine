# Build V36 từ gói APKPure gốc

[English](../06-build-android-client.md) | Tiếng Việt

Chuẩn bị đầu vào một lần, rồi chạy một lệnh build. Lệnh sẽ xác minh và merge
gói APKPure gốc, áp dụng thay đổi V36 hiện hành, biên dịch runtime, căn chỉnh
và ký APK của bạn. Không dùng APK Akaine đã patch làm đầu vào.

Chương này chỉ hỗ trợ Arcaea **7.0.255 (`1209852`), arm64-v8a**.
Không thay bằng phiên bản khác hoặc bản tải armeabi-v7a.

![Quy trình build client Android trong chương 06](../../images/guides/06-android-client-assembly.svg)

V36 gồm semantic CLI, xử lý hướng dẫn đầu game, sửa skill nhân vật,
điều khiển anomaly replay, Mod, dynamic pack, mười news mới nhất và cache
bundle dở có kiểm soát. Nhạc và ảnh bài hát gốc được giữ nguyên. Content bundle
vẫn tách khỏi APK; lệnh này không đăng hoặc kích hoạt bundle.

Route đi kèm vẫn dùng các Akaine production host đã phát hành. Domain riêng
cần native route change được kiểm chứng riêng; bước kiểm server ở chương 5a
không thay route client. ANGLE, Vulkan và thử nghiệm loading chưa hoàn thành
không thuộc bản build này.

## 1. Mở máy đã chuẩn bị

Dùng cửa sổ PowerShell có thể tương tác và giữ nó mở suốt chương này:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
Set-Location $repoRoot
Get-Item $python, $kitRoot
& $python scripts\build_android_client.py --help
if ($LASTEXITCODE -ne 0) { throw "Client builder is unavailable." }
```

Các đường dẫn được lưu ở chương 3 và 4. Lệnh help phải hiển thị những đầu vào
dùng phía dưới. Nếu thiếu công cụ bắt buộc, dừng và hoàn tất setup máy trước.

## 2. Tải và xác minh gói gốc

Tải **XAPK arm64-v8a** từ
[trang APKPure 7.0.255](https://apkpure.net/arcaea/moe.low.arc/download/7.0.255).
XAPK là gói đầy đủ: base, arcassets, arm64, tiếng Anh và mdpi.
Không giải nén rồi chỉ đưa `moe.low.arc.apk` vào builder; base APK đó chưa đủ.

```powershell
$source = Get-Item -LiteralPath (Read-Host "Full path to the original APKPure 7.0.255 arm64 XAPK")
$expectedSourceHash = "459bb01f8357dde82b13a817d4dd5dbf81e7a70d0805cc0d5f1aebde36fa2b7a"
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source.FullName).Hash.ToLowerInvariant()
if ($source.Length -ne 1219427332 -or $sourceHash -ne $expectedSourceHash) {
    throw "Wrong APKPure package. Stop here; do not change the expected hash."
}
$source | Select-Object Name, Length
$sourceHash
```

Cả kích thước và SHA-256 phải khớp. Builder kiểm lại chúng rồi tự merge các
module. APK merge đã xác minh có 1.206.740.473 byte, SHA-256
`746dd90c2efac21fc88ffd032e5a71c78c0955766477382c7f48ece87e23026e`.
Đây là APK trung gian do builder tạo ra trước khi áp dụng V36.

## 3. Chọn công cụ, key content và danh tính ký

Dùng Java 17 và NDK Windows `28.2.13676358`. Tải
[APKEditor 1.4.9](https://github.com/REAndroid/APKEditor/releases/tag/V1.4.9),
chọn đúng jadx all-in-one JAR đã xác minh và Android Build-Tools theo hướng
dẫn workstation/kit:

```powershell
$ndk = Get-Item -LiteralPath (Read-Host "Full path to Android NDK 28.2.13676358")
$java = Get-Item -LiteralPath (Read-Host "Full path to Java 17 java.exe")
$apkeditor = Get-Item -LiteralPath (Read-Host "Full path to APKEditor-1.4.9.jar")
$jadx = Get-Item -LiteralPath (Read-Host "Full path to the matching jadx all-in-one JAR")
$d8 = Get-Item -LiteralPath (Read-Host "Full path to Android Build-Tools d8.jar")
$buildTools = Get-Item -LiteralPath (Read-Host "Full path to Android SDK Build-Tools")
$javac = Join-Path $java.DirectoryName "javac.exe"
$keytool = Join-Path $java.DirectoryName "keytool.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"
Get-Item $javac, $keytool, $apksigner, $aapt, (Join-Path $buildTools.FullName "zipalign.exe")
$editorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $apkeditor.FullName).Hash.ToLowerInvariant()
if ($apkeditor.Length -ne 7733037 -or $editorHash -ne "a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67") {
    throw "APKEditor does not match the verified 1.4.9 release."
}
& $java.FullName -version
if ($LASTEXITCODE -ne 0) { throw "Java failed." }
```

Folder NDK chứa `toolchains`; folder Build-Tools chứa `zipalign.exe`,
`apksigner.bat` và `aapt.exe`. `d8.jar` thường nằm trong folder `lib` của nó.
Folder Java còn phải có `javac.exe` và `keytool.exe`.
Không đổi tên một JAR khác để giả làm công cụ được yêu cầu.

Chọn catalogue và file AKFC đã xác minh ở [chương 4](04-private-resources.md):

```powershell
$songlist = Get-Item -LiteralPath (Read-Host "Full path to the verified native songlist JSON")
$keyHeader = Get-Item -LiteralPath (Read-Host "Full path to the matching private embedded_key.h")
$crypto = Get-Item -LiteralPath (Read-Host "Full path to the arm64 prefixed BoringSSL static archive")
Get-Item $songlist.FullName, $keyHeader.FullName, $crypto.FullName | Select-Object Name, Length
```

Native `songlist` cung cấp catalogue cho CLI; server metadata không thay
thế được. Header AKFC phải khớp các chart đã mã hóa hiện có. **Không tạo
chart key mới cho catalogue đang dùng.** Giữ header ngoài Git; compiler dùng
nó mà không in nội dung.

### Chỉ khi tạo chart key cho server mới

Bỏ qua block này nếu dùng chart Akaine hiện có. Server mới có thể tạo một
cặp RSA-3072 rồi mã hóa chart bằng public key tương ứng:

```powershell
$keyFolder = [IO.Path]::GetFullPath((Read-Host "Private folder for a new server's AKFC keys"))
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$newKeyHeader = Join-Path $keyFolder "embedded_key.h"
if (-not (Test-Path $privateKey) -and -not (Test-Path $publicKey)) {
    & $python scripts\generate_akfc_keypair.py --private-key $privateKey --public-key $publicKey
    if ($LASTEXITCODE -ne 0) { throw "AKFC key generation failed." }
} elseif (-not (Test-Path $privateKey) -or -not (Test-Path $publicKey)) {
    throw "Only half of the AKFC pair exists. Restore its matching partner."
}
& $python scripts\generate_akfc_key_header.py --private-key $privateKey --output $newKeyHeader
if ($LASTEXITCODE -ne 0) { throw "AKFC header generation failed." }
$keyHeader = Get-Item -LiteralPath $newKeyHeader
```

Block tái sử dụng cặp đầy đủ và dừng nếu chỉ có một nửa. Nó không thay key
của những chart đã được mã hóa.

### Chỉ khi thiếu static crypto archive

Cài CMake và Ninja trong Android Studio SDK Tools, rồi dùng helper:

```powershell
$env:ANDROID_NDK_ROOT = $ndk.FullName
$cryptoWork = [IO.Path]::GetFullPath((Read-Host "New private working directory for the crypto build"))
$cryptoOutput = Join-Path $cryptoWork "libakfc-crypto.a"
& $python scripts\build_boringssl_android.py --work $cryptoWork --output $cryptoOutput
if ($LASTEXITCODE -ne 0) { throw "BoringSSL build failed." }
$crypto = Get-Item -LiteralPath $cryptoOutput
```

Lệnh tải và biên dịch BoringSSL với symbol prefix `akfc_`. Archive tạm được
tạo bởi lệnh thất bại chưa phải đầu vào có thể dùng.

### Chọn Android signing key

Android keystore xác nhận ai ký ứng dụng. Nó tách biệt với chart key AKFC.
Dùng lại keystore và alias hiện có khi cập nhật một bản cài.
Chỉ tạo key khi thiết lập danh tính ký mới:

```powershell
$keystore = [IO.Path]::GetFullPath((Read-Host "Full path to your private Android keystore"))
$keyAlias = Read-Host "Signing-key alias"
if (-not (Test-Path $keystore)) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $keystore) | Out-Null
    & $keytool -genkeypair -keystore $keystore -alias $keyAlias -keyalg RSA -keysize 4096 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw "Signing-key generation failed." }
}
Get-Item -LiteralPath $keystore
```

Keytool hỏi mật khẩu riêng. Giữ keystore cùng bản backup ngoài Git.
Mất key này sẽ không cập nhật đè được các bản cài đã ký bằng nó.

## 4. Build và ký bằng một lệnh

Chọn output directory mới nằm ngoài repository. Build có thể mất vài phút.
Giữ cửa sổ PowerShell mở, trả lời các prompt mật khẩu riêng khi bắt đầu ký,
và dừng ngay khi có lỗi đầu tiên:

```powershell
$buildOutput = [IO.Path]::GetFullPath((Read-Host "New output directory outside the repository"))
if (Test-Path $buildOutput) { throw "Choose a new output directory." }
$arguments = @(
    "--source", $source.FullName,
    "--songlist", $songlist.FullName,
    "--ndk", $ndk.FullName,
    "--java", $java.FullName,
    "--apkeditor", $apkeditor.FullName,
    "--jadx", $jadx.FullName,
    "--d8", $d8.FullName,
    "--crypto", $crypto.FullName,
    "--key-header", $keyHeader.FullName,
    "--output", $buildOutput,
    "--keystore", $keystore,
    "--key-alias", $keyAlias,
    "--build-tools", $buildTools.FullName
)
& $python scripts\build_android_client.py @arguments
if ($LASTEXITCODE -ne 0) { throw "V36 build failed. Keep the first error; do not install its output." }
$signedApk = Join-Path $buildOutput "Akaine-V36.apk"
$receipt = Get-Content (Join-Path $buildOutput "BUILD_RECEIPT.json") -Raw | ConvertFrom-Json
if ($receipt.status -ne "APKPURE_TO_V36_SOURCE_BUILD_VERIFIED" -or $receipt.signed -ne $true) {
    throw "The build did not complete and sign successfully."
}
Get-Item -LiteralPath $signedApk | Select-Object Name, Length
```

Lệnh tạo `Akaine-V36.apk` và `BUILD_RECEIPT.json`. Nó kiểm đầu vào gốc và
byte trước patch, biên dịch native/Android code hiện hành, giữ nguyên các file
APK ngoài phạm vi thay đổi, rồi căn chỉnh và ký bằng key của bạn. Bạn không
cần chạy riêng từng script native, DEX hoặc checkpoint.

Mật khẩu được hỏi riêng, không truyền trong command argument. Không ghi
chúng vào script hoặc build log.

Nếu build dừng, giữ directory và lỗi đầu tiên để kiểm tra. Lần thử tiếp theo
phải dùng output directory mới để không trộn file dở.

Kiểm độc lập bản đã ký:

```powershell
& $apksigner verify --verbose --print-certs $signedApk
if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed." }
& $aapt dump badging $signedApk | Select-String "package:|application-label:|launchable-activity:"
if ($LASTEXITCODE -ne 0) { throw "APK package inspection failed." }
Get-FileHash -Algorithm SHA256 -LiteralPath $signedApk
```

Kiểm chữ ký phải đạt, gồm APK Signature Scheme v2. Badging phải hiển thị
package `akai.arc.lmao`, label `AkaineXD`, version `7.0.255`, code `1209852`
và activity `low.moe.AppActivity`. Lưu signer certificate digest cho lần cập
nhật sau. Signer riêng của bạn tạo ra final APK hash khác.

## 5. Cài và kiểm ứng dụng

Kết nối đúng thiết bị hoặc emulator và đọc serial chính xác:

```powershell
adb devices -l
$serial = Read-Host "Exact device serial shown above"
adb -s $serial shell pm path "akai.arc.lmao"
```

Chỉ tiếp tục khi ADB hiển thị trạng thái `device`. Xử lý `unauthorized` hoặc
`offline` trước. Kết quả `package:` nghĩa là Akaine đã được cài.

Với bản cài mới:

```powershell
adb -s $serial install $signedApk
if ($LASTEXITCODE -ne 0) { throw "Fresh installation failed." }
```

Với bản cập nhật dùng cùng signing certificate:

```powershell
adb -s $serial install -r $signedApk
if ($LASTEXITCODE -ne 0) { throw "Install-over failed. Check the signer before doing anything else." }
```

Không tự động uninstall sau lỗi `INSTALL_FAILED_UPDATE_INCOMPATIBLE`.
Uninstall sẽ xóa local data. Hãy tìm đúng signer hoặc chủ động backup
và chọn cài mới.

Mở ứng dụng và đọc semantic state:

```powershell
adb -s $serial shell am start -n "akai.arc.lmao/low.moe.AppActivity"
if ($LASTEXITCODE -ne 0) { throw "Android launch request failed." }
& $python scripts\akaine_cli\akaine.py --serial $serial status
if ($LASTEXITCODE -ne 0) { throw "Client bridge is not ready. Inspect the app and logs." }
& $python scripts\akaine_cli\akaine.py --serial $serial ui list
if ($LASTEXITCODE -ne 0) { throw "Client UI state read failed." }
```

CLI dùng callback của game, không dùng tọa độ màn hình hay scan ảnh.
Yêu cầu launch chưa chứng minh ứng dụng vẫn đang chạy. Kiểm ứng dụng và log
nếu bridge chưa sẵn sàng. [Tham chiếu CLI](../06a-semantic-cli.md) giải thích
các hướng dẫn đầu game được hỗ trợ, điều khiển bài/nhân vật và kết quả chưa rõ.

Trước khi phân phối APK, kiểm bằng tài khoản riêng cho test và content tương ứng:

1. Đến title, tải bundle được cấu hình mà không crash hoặc lặp tải.
2. Đăng nhập, Cloud Sync Download, mở lại; xác nhận giữ đăng nhập và bài đã tải.
3. Hoàn tất guide được nhận diện; chọn pack, bài, filter và nhân vật.
4. Kiểm vị trí Mod, thanh máu skill đặc trưng và replay tắt/bật.
5. Chơi một bài official và một native fan chart; kiểm nhạc, ảnh và kết quả đã lưu.

Kiểm build/chữ ký chưa xác nhận gameplay compatibility hoặc hiệu năng trên
mọi thiết bị. Các lệnh trên không deploy server hoặc đăng bundle.

Tiếp: [Build, xác minh và phát hành content bundle](07-build-release-content-bundle.md).
