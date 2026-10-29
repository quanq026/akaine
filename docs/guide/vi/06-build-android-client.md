# Build client Android V36

[English](../06-build-android-client.md) | Tiếng Việt

Chương này build Akaine V36 cho Arcaea `7.0.255` (`1209852`) từ APK
production V9 ngày 22/10/2026 đã xác minh. XAPK upstream, APK staging hay
bản đóng gói lại khác không thay thế được đầu vào này.

Public source chứa runtime native, thay đổi Android và công cụ build.
Bộ tài nguyên riêng cung cấp APK đúng, catalogue và đầu vào AKFC.
Bạn không cần disk identity của người phát triển, frozen source kit
hay local path map.

![Dây chuyền lắp ráp client Android chương 06](../../images/guides/06-android-client-assembly.svg)

## Bản build này gồm những gì

V36 giữ package `akai.arc.lmao`, label `AkaineXD`, application version
`7.0.255` và version code `1209852`. Bản này gồm semantic CLI, xử lý
hướng dẫn đầu game, sửa skill nhân vật, điều khiển anomaly replay,
category Mod, pack động, mười tin mới nhất và partial cache có guard
cho việc tải bundle.

Builder giữ nguyên media của APK đầu vào. Nó không resize jacket,
encode lại âm thanh hay tạo content bundle. Content `7.0.255.25` được
cài riêng qua server đã cấu hình. ANGLE, Vulkan và thử nghiệm
scene/loading chưa hoàn tất không nằm trong bản này.

Client đi kèm dùng các Akaine production host đã phát hành. Nó không
thay chúng bằng domain ở chương 2. API host khác cần native route
change được kiểm chứng riêng cho login, aggregate, content bundle và
encrypted shared API base. Kiểm server thành công ở chương 5a không
làm thay đổi route trong client.

## Bước 1: mở lại workstation đã chuẩn bị

Giữ cùng một cửa sổ PowerShell cho các bước còn lại:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
Set-Location $repoRoot
Get-Item $python, $kitRoot
& $python scripts\build_v36_client.py --help
if ($LASTEXITCODE -ne 0) { throw "V36 builder help failed." }
```

Các đường dẫn đã được lưu ở chương 3 và 4. Help phải liệt kê các đầu
vào tường minh dùng bên dưới. Nếu thiếu folder hay công cụ, hoàn tất
setup trước. Các lệnh build này không deploy server hoặc publish content.

## Bước 2: xác minh APK đầu vào

Nhận đúng đầu vào qua kênh riêng được mô tả ở
[chương 4](04-private-resources.md), rồi kiểm hash toàn bộ file:

```powershell
$baseApk = Get-Item (Read-Host "Full path to the production V9 APK")
$expectedBaseHash = "f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545"
$baseHash = (Get-FileHash -Algorithm SHA256 $baseApk.FullName).Hash.ToLowerInvariant()
if ($baseHash -ne $expectedBaseHash) { throw "Wrong base APK. Stop here." }
$baseApk | Select-Object Name, Length
$baseHash
```

Hash phải khớp hoàn toàn. Đây là APK đầu vào, chưa phải output V36.
Không sửa expected hash để APK khác vượt kiểm tra.

## Bước 3: chọn toolchain

Dùng Android NDK `28.2.13676358` cho Windows và Java 17. Folder Java
phải có cả `javac.exe` và `keytool.exe`. Chọn đúng jadx all-in-one JAR
và Android Build-Tools `d8.jar` ghi trong hướng dẫn của kit đã xác minh:

```powershell
$ndk = Get-Item (Read-Host "Full path to Android NDK 28.2.13676358")
$java = Get-Item (Read-Host "Full path to Java 17 java.exe")
$jadx = Get-Item (Read-Host "Full path to the matching jadx all-in-one JAR")
$d8 = Get-Item (Read-Host "Full path to Android Build-Tools d8.jar")
$javac = Join-Path $java.DirectoryName "javac.exe"
$llvm = Join-Path $ndk.FullName "toolchains\llvm\prebuilt\windows-x86_64\bin"
Get-Item $javac, (Join-Path $llvm "clang++.exe"), (Join-Path $llvm "llvm-objcopy.exe")
& $java.FullName -version
if ($LASTEXITCODE -ne 0) { throw "Java failed." }
```

Folder NDK chứa `toolchains`; đó không phải SDK root hay riêng file
compiler. `d8.jar` thường nằm trong folder `lib` của Build-Tools.
Không đổi tên JAR khác. Có thể giữ công cụ tại vị trí phù hợp trên máy.

## Bước 4: chọn catalogue và đầu vào AKFC

Dùng native `songlist` JSON khớp catalogue content của bạn. Nó cung
cấp catalogue cho CLI; APK đầu vào không có file này. Server metadata
không thay thế được nó.

Với chart Akaine hiện có, dùng matching key header từ bộ tài nguyên
riêng đã xác minh. **Không tạo AKFC key mới cho chart hiện có.**
Chọn static BoringSSL archive arm64 có symbol prefix `akfc_`:

```powershell
$songlist = Get-Item (Read-Host "Full path to the verified native songlist JSON")
$keyHeader = Get-Item (Read-Host "Full path to the matching private AKFC key header")
$crypto = Get-Item (Read-Host "Full path to the arm64 symbol-prefixed BoringSSL static archive")
Get-Item $songlist.FullName, $keyHeader.FullName, $crypto.FullName | Select-Object Name, Length
```

Các lệnh này chỉ hiện tên file và độ dài, không hiện nội dung key.
Giữ header ngoài Git. Builder truyền nó cho compiler mà không hiển
thị nội dung. `libcrypto.so` dùng chung toàn process không thay thế
được static archive này.

### Chỉ dành cho server mới: tạo chart key

Bỏ qua mục này với catalogue hiện có. Server mới có thể tạo một cặp
RSA-3072, mã hóa chart bằng public key và build client bằng private
header tương ứng:

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
$keyHeader = Get-Item $newKeyHeader
```

Guard tái sử dụng cặp đầy đủ hiện có và dừng khi thiếu một nửa cặp.
Đổi key của catalogue hiện có đòi hỏi mã hóa lại các chart liên quan.
AKFC key được nhúng trong APK nên không bí mật vĩnh viễn trước người
quyết tâm giải ngược.

### Nếu chưa có static crypto archive

Cài CMake và Ninja qua Android Studio SDK Tools rồi build archive
tại revision đã pin và có symbol prefix bằng helper hiện có:

```powershell
$env:ANDROID_NDK_ROOT = $ndk.FullName
$cryptoWork = [IO.Path]::GetFullPath((Read-Host "Private working directory for the crypto build"))
$cryptoOutput = Join-Path $cryptoWork "libakfc-crypto.a"
& $python scripts\build_boringssl_android.py --work $cryptoWork --output $cryptoOutput
if ($LASTEXITCODE -ne 0) { throw "BoringSSL build failed." }
$crypto = Get-Item $cryptoOutput
```

Bước này tải và biên dịch BoringSSL. Dừng nếu build thất bại; có
archive tạm không đủ chứng minh thành công. Bước này không thay chart key.

## Bước 5: biên dịch và lắp ráp

Chọn output directory mới ngoài public repository, trên ổ phù hợp
bất kỳ. Không chọn folder đang chứa APK hay private key đầu vào:

```powershell
$buildOutput = [IO.Path]::GetFullPath((Read-Host "New output directory for the V36 build"))
if (Test-Path $buildOutput) { throw "Choose a new output directory." }
$arguments = @(
    "--base-apk", $baseApk.FullName,
    "--songlist", $songlist.FullName,
    "--ndk", $ndk.FullName,
    "--java", $java.FullName,
    "--jadx", $jadx.FullName,
    "--d8", $d8.FullName,
    "--crypto", $crypto.FullName,
    "--key-header", $keyHeader.FullName,
    "--output", $buildOutput
)
& $python scripts\build_v36_client.py @arguments
if ($LASTEXITCODE -ne 0) { throw "V36 source build failed. Do not sign its output." }
$unsignedApk = Join-Path $buildOutput "unsigned.apk"
$buildReceipt = Join-Path $buildOutput "BUILD_RECEIPT.json"
Get-Item $unsignedApk, $buildReceipt | Select-Object Name, Length
Get-Content $buildReceipt -Raw | ConvertFrom-Json | Format-List
& $python -m zipfile -t $unsignedApk
if ($LASTEXITCODE -ne 0) { throw "Unsigned APK archive check failed." }
```

Builder kiểm base và catalogue, biên dịch payload native/managed V36
cùng AKFC loader rồi lắp ráp `unsigned.apk`. `BUILD_RECEIPT.json`
ghi đầu vào và kết quả. Đọc receipt trước khi ký. Kiểm ZIP xác minh
cấu trúc archive, không chứng minh gameplay hay kết nối server.

APK chưa ký chưa sẵn sàng cài đặt. Khi có lỗi, giữ lỗi đầu tiên và
build directory để kiểm tra. Dùng directory mới cho lần thử khác.

## Bước 6: align APK

Chọn Android SDK Build-Tools đã cài và kiểm các file bắt buộc:

```powershell
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable("ANDROID_HOME", "User") }
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $buildTools) { throw "Install Android SDK Build-Tools first." }
$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"
Get-Item $zipalign, $apksigner, $aapt
$alignedApk = Join-Path $buildOutput "Akaine-v36-aligned.apk"
$signedApk = Join-Path $buildOutput "Akaine-v36.apk"
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK alignment failed." }
& $zipalign -c -P 16 -v 4 $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK alignment verification failed." }
```

Phiên bản được sắp xếp theo số. `-P 16` áp dụng page alignment cho
native library; `4` áp dụng ZIP alignment thông thường. Lệnh thứ hai
kiểm riêng kết quả. Dừng nếu một trong hai lần gọi thất bại.

## Bước 7: ký và xác minh

Tái sử dụng keystore của bản cài hiện có. Chỉ tạo khi bạn thiết lập
signing identity của mình lần đầu:

```powershell
$keystore = [IO.Path]::GetFullPath((Read-Host "Full path to your private Android keystore"))
$keyAlias = Read-Host "Signing-key alias"
$keytool = Join-Path $java.DirectoryName "keytool.exe"
Get-Item $keytool
if (-not (Test-Path $keystore)) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $keystore) | Out-Null
    & $keytool -genkeypair -keystore $keystore -alias $keyAlias -keyalg RSA -keysize 4096 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw "Signing-key generation failed." }
}
& $apksigner sign --ks $keystore --ks-key-alias $keyAlias --v4-signing-enabled false --out $signedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK signing failed." }
& $apksigner verify --verbose --print-certs $signedApk
if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed." }
& $aapt dump badging $signedApk | Select-String "package:|application-label:|launchable-activity:"
Get-FileHash -Algorithm SHA256 $signedApk
```

Mật khẩu được hỏi tương tác. Giữ keystore và mật khẩu ngoài Git,
resource kit và shell arguments. Android signing key độc lập với
AKFC chart key.

Kiểm chữ ký phải thành công và báo APK Signature Scheme v2 đã xác minh.
Ghi lại signer certificate digest để so sánh khi cài đè sau này.
Badging phải hiện `akai.arc.lmao`, `AkaineXD`, `7.0.255`, `1209852`
và activity `low.moe.AppActivity`.

APK do bạn ký khác APK được operator khác ký. So sánh package và signer
cho bản cài của bạn; APK đã ký không cần có signed hash giống hệt
release đã phát hành.

## Bước 8: chọn thiết bị và cài đặt

Kết nối đúng điện thoại Android hoặc emulator rồi chọn serial chính xác:

```powershell
adb devices -l
$serial = Read-Host "Exact device serial shown above"
$package = "akai.arc.lmao"
adb -s $serial shell pm path $package
```

Chỉ tiếp tục khi thiết bị có trạng thái `device`. `unauthorized`
cần chấp nhận USB debugging trên thiết bị đã mở khóa; `offline` cần
sửa kết nối trước. Kết quả `package:` nghĩa là Akaine đã được cài.

Nếu cài lần đầu:

```powershell
adb -s $serial install $signedApk
if ($LASTEXITCODE -ne 0) { throw "Fresh installation failed." }
```

Nếu đã có bản cài dùng cùng signing certificate:

```powershell
adb -s $serial install -r $signedApk
if ($LASTEXITCODE -ne 0) { throw "Install-over failed. Check the signer before doing anything else." }
```

Không tự gỡ app khi gặp `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Gỡ app
xóa dữ liệu local. Dùng đúng signer hoặc chủ động quyết định backup
rồi cài mới.

## Bước 9: đọc trạng thái client qua CLI

Mở đúng activity rồi đọc semantic state:

```powershell
adb -s $serial shell am start -n "akai.arc.lmao/low.moe.AppActivity"
if ($LASTEXITCODE -ne 0) { throw "Android launch request failed." }
& $python scripts\akaine_cli\akaine.py --serial $serial status
if ($LASTEXITCODE -ne 0) { throw "Client bridge status failed. Inspect the app and logs." }
& $python scripts\akaine_cli\akaine.py --serial $serial ui list
if ($LASTEXITCODE -ne 0) { throw "Client UI state read failed." }
& $python scripts\akaine_cli\akaine.py --serial $serial --help
```

CLI gọi semantic bridge của thiết bị mà không dùng tọa độ hoặc scan ảnh.
`status` và `ui list` đọc trạng thái hiện tại. Launch request không
đủ chứng minh app tiếp tục chạy. Nếu bridge chưa sẵn sàng, xem app
và log trước khi thử lại.

Dùng `--help` cho search catalogue, bài/độ khó, nhân vật, filter,
settings, Cloud Sync và hướng dẫn đầu game đã nhận diện. Đọc `ui list`
mới trước khi dùng action token vì token thuộc scene hiện tại.
Modal ẩn hoặc Android permission prompt có thể chặn action.
Không đặt credentials trong shell arguments hoặc log công khai.

[Tham chiếu CLI đầu game](../06a-semantic-cli.md) giải thích chi tiết
bước hướng dẫn đã nhận diện, xác nhận Note Speed và xử lý kết quả chưa rõ.

## Bước 10: kiểm client và content cùng nhau

Kiểm source, archive và chữ ký không thay thế runtime check. Dùng tài khoản
test riêng cùng catalogue tương ứng trên server đích trước khi phân phối APK:

1. Tới title screen mà không crash hoặc bundle loop.
2. Tải standalone bundle đã cấu hình rồi mở lại.
3. Đăng nhập, dùng Cloud Sync Download, mở lại và kiểm login còn giữ.
4. Đọc scene/overlay bằng CLI và hoàn tất hướng dẫn đã nhận diện.
5. Mở pack/bài, search/filter và chọn nhân vật.
6. Kiểm vị trí Mod và Fan Charts khớp catalogue.
7. Kiểm gauge skill đặc trưng của nhân vật trong gameplay thật.
8. Kiểm anomaly replay tắt/bật, gồm những lần mở lại cần thiết.
9. Chơi một chart official và một native fan chart có AKFC file
   tương ứng; kiểm âm thanh, jacket và kết quả đã lưu.
10. Mở lại rồi kiểm content đã tải vẫn có.

Lưu log khi một bước kiểm tra thất bại:

```powershell
$logFile = Join-Path $buildOutput "client-logcat.txt"
adb -s $serial logcat -d | Set-Content -Encoding utf8 $logFile
Select-String -Path $logFile -Pattern "Fatal signal","FATAL EXCEPTION","JNI DETECTED ERROR","ClassNotFoundException","FMOD"
```

Che credentials, device identifier và dữ liệu tài khoản cá nhân trước
khi chia sẻ log. Kiểm trên emu không chứng minh hiệu năng máy thật,
tương thích mọi chart hay cải thiện FPS tổng quát.

Tiếp: [Build, xác minh và phát hành content bundle](07-build-release-content-bundle.md).
