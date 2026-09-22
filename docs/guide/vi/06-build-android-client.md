# Build client Android Arcaea 7.0.255

[English](../06-build-android-client.md) | Tiếng Việt

Chương này build một client Akaine có thể cài đặt từ XAPK Arcaea 7.0.255 đã được xác
minh. Quy trình gồm kiểm tra đầu vào, gộp các split, patch managed code và native code,
align, ký APK, cài đặt rồi thu log kiểm thử.

Bạn phải tự tải ứng dụng gốc. Repository không chứa APK thương mại hay signing key.
GitHub chỉ chứa quy trình build, mã kiểm tra và patch native/Smali dành riêng cho
7.0.255.

## "Khớp với release" nghĩa là gì

Client tham chiếu 7.0.255 có các tiêu chí sau:

- app label: `AkaineXD`;
- package: `akai.arc.lmao`;
- version name: `7.0.255`;
- version code: `1209852`;
- production API routes, không phải staging routes;
- sửa hiển thị và preview Divine;
- sửa lựa chọn Final Verdict và Axium Crisis BYD;
- đầy đủ AKFC runtime cho protected chart;
- null guard cho Aether Crest ETR;
- không có hook hoặc tag chỉ dùng để chẩn đoán;
- mục tiêu content bundle `7.0.255.8`.

APK tham chiếu SHA-256 là
`18fb7f69aa4677ee3a04235e02658c3f2b56cc92fb3a4eee78172a292271b042`. Hash đó xác định
artifact đã phát hành; đây không phải hash mà client ký bằng khóa riêng của bạn phải
có. Chỉ cần signing key khác thì byte của APK cũng khác.

Hai bản build có thể hoạt động giống nhau mà không cần có cùng hash APK:

- cùng đầu vào, patch và cấu hình có thể tái tạo cùng hành vi;
- install-over yêu cầu đúng signing identity đã dùng cho bản đang cài;
- muốn APK giống hệt từng byte thì thứ tự file, timestamp và người ký cũng phải giống.

Không bao giờ sao chép signing key của operator khác. Tạo và bảo vệ của riêng bạn.

## Tải xuống XAPK upstream chính xác

Mục tiêu là Arcaea `7.0.255` (`1209852`), package `moe.low.arc`, Android `arm64-v8a`.
APKPure phân phối phiên bản này dưới dạng XAPK chứa năm mô-đun APK. Chọn biến thể arm64,
không phải biến thể armeabi-v7a.

Tại thời điểm quy trình này được xác minh, arm64 XAPK có:

```text
SHA-256  459bb01f8357dde82b13a817d4dd5dbf81e7a70d0805cc0d5f1aebde36fa2b7a
Size     1219427332 bytes
Splits   base, arcassets, config.arm64_v8a, config.en, config.mdpi
```

Sau khi tải xuống, hãy chọn file và xác minh nó trước khi mở:

```powershell
$xapk = Get-Item (Read-Host "Full path to the downloaded 7.0.255 arm64 XAPK")
Get-Item $xapk.FullName | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $xapk.FullName
```

Cả kích thước và SHA-256 phải khớp. File của 7.0.256, biến thể armeabi-v7a hoặc bản đã
được mirror đóng gói lại không thể thay thế đầu vào này. Native offset và byte guard
chỉ đúng với build đã nêu.

## Hợp nhất các split của XAPK thành một APK cơ sở

Tải xuống `APKEditor-1.4.9.jar` từ release `REAndroid/APKEditor` GitHub chính
thức. Xác minh công cụ trước khi chạy nó:

```text
SHA-256  a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67
Size     7733037 bytes
```

Chọn nơi lưu giữ công cụ và đầu ra cơ sở:

```powershell
$apkEditor = Get-Item (Read-Host "Full path to APKEditor-1.4.9.jar")
$baseline = Read-Host "Full output path for the merged baseline APK"
$baseline = [IO.Path]::GetFullPath($baseline)

Get-FileHash -Algorithm SHA256 $apkEditor.FullName
java -Xmx4g -jar $apkEditor.FullName merge `
  -i $xapk.FullName `
  -o $baseline
```

Đừng chỉ đổi đuôi `.xapk` thành `.apk`. Base APK đứng riêng không có native library
arm64 và module asset. APKEditor gộp đủ năm module rồi loại bỏ các khai báo bắt buộc
split trong manifest.

Baseline hợp nhất được sử dụng cho dự án này có:

```text
SHA-256  746dd90c2efac21fc88ffd032e5a71c78c0955766477382c7f48ece87e23026e
Size     1206740473 bytes
```

Kiểm tra danh tính của nó:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object Name -Descending |
  Select-Object -First 1
$aapt = Join-Path $buildTools.FullName "aapt.exe"

& $aapt dump badging $baseline |
  Select-String "package:|application-label:|launchable-activity:"
```

Kết quả vẫn phải báo package `moe.low.arc`, label `Arcaea`, version name `7.0.255`,
version code `1209852` và launchable activity `low.moe.AppActivity`. Chữ ký split cũ
không còn hợp lệ sau khi gộp. APK cuối sẽ được align và ký lại ở các bước sau.

## Trước khi build

Hoàn thành chương 3 và 4. Sau đó mở PowerShell và tải các vị trí bạn đã chọn trước đó:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")

Set-Location $repoRoot
python scripts\doctor.py --android
```

Không tiếp tục trừ khi quá trình kiểm tra công cụ nghiêm ngặt vượt qua.

## Hiểu bộ patch công khai

APK là một file ZIP chứa nhiều loại dữ liệu chương trình. Bản build này thay đổi ba lớp:

| Lớp | File trong bản build | Chức năng |
| --- | --- | --- |
| Lớp Android | `AndroidManifest.xml`, resource và `classes.dex` | Package, app label, Android component và cầu nối Java/Smali khởi động AKFC |
| Mã game | `libcocos2dcpp.so` | Server route và native condition của Divine, BYD, Dread Area và Aether Crest |
| Cầu nối file âm thanh | `libfmodProvider.so` | Kết quả trả về cho FMOD sau khi đọc file |

Content bundle nằm ngoài ba lớp trên. Nó cung cấp catalog, layout, jacket và preview sau
khi client kết nối. Patch APK có thể làm selector chấp nhận một bài hát, nhưng không thể
tạo jacket hay file âm thanh đang thiếu.

Việc chuyển đổi được tập hợp từ nguồn trong repository này:

- `patch_android_client_sources.py` sửa manifest, label, package reference và lời gọi
  vòng đời AKFC;
- `AkfcLoader.smali` là cầu nối JNI ở managed code;
- `akfc_loader.cpp` triển khai tải chart được bảo vệ;
- các script tạo một cặp khóa RSA-3072 riêng cho mỗi operator;
- `build_boringssl_android.py` tạo static crypto archive có prefix cho symbol và chỉ
  link archive đó vào AKFC loader;
- `native-plan.json` áp dụng các thay đổi byte có guard cho hai native library gốc.

Không có `.dex` hoặc `.so` đã vá nào được tải xuống từ Akaine. Đầu vào không phải nguồn
duy nhất là XAPK upstream đã được xác minh.

Ba thuật ngữ xuất hiện xuyên suốt chương này. Managed code là phần Android/Java được
biên dịch thành `classes.dex`; Apktool biểu diễn nó bằng Smali để con người có thể đọc
và sửa. Native code là mã máy arm64 trong các thư viện `.so`. Hook chuyển một hàm hoặc
call site đã biết sang logic thay thế; nó không phải hook server từ xa hay sửa mọi hàm
trong game.

### Cách thức hoạt động của patch nhị phân được bảo vệ

`native-plan.json` là danh sách thay thế byte nhỏ. Mỗi thao tác có bốn trường hữu ích:

- `offset` là vị trí byte bên trong native library;
- `before` là chuỗi byte chính xác được mong đợi trong file 7.0.255 chưa được chỉnh sửa;
- `after` là sản phẩm thay thế có cùng độ dài;
- `label` đặt tên dễ đọc cho thay đổi trong build receipt.

Builder kiểm tra SHA-256 của native library gốc, đối chiếu byte `before` tại từng
offset, ghi byte `after`, rồi kiểm tra SHA-256 đầu ra. Nếu một điều kiện không khớp,
quá trình dừng mà không xuất APK. Nhờ vậy offset của 7.0.255 không thể bị ghi nhầm vào
release khác, nơi cùng vị trí có thể chứa mã hoàn toàn khác.

Văn bản thập lục phân là đầu vào của máy chứ không phải là bước mà bạn nên chỉnh sửa
bằng tay. Chỉ thay đổi thao tác gốc sau khi phân tích thư viện đích và cập nhật hash
nguồn, byte được bảo vệ và hash đầu ra cùng nhau.

## Native patch của release làm gì

Native patch chỉ dành cho 7.0.255. Mỗi thao tác kiểm tra byte gốc trước khi ghi vì
offset của phiên bản client khác không an toàn.

Các nhãn trong kế hoạch được nhóm bên dưới theo vấn đề mà người chơi phải đối mặt mà họ
giải quyết.

Login route trả access token. Aggregate route gộp nhiều API call lúc khởi động vào một
request. Content-bundle route cho client biết cần tải resource update nào. Các request
khác, trong đó có Cloud Sync, được tạo từ shared API base.

| Label trong plan | Thay đổi | Lỗi khi thiếu patch |
| --- | --- | --- |
| `production-routes`, `route-helper`, `route-hook-a`, `route-hook-b`, `route-hook-c`, `route-hook-d` | Lưu URL production cho login, aggregate và content bundle, rồi chuyển các call site tương ứng qua route helper. Chỉ chèn URL mới mà không chuyển call site thì request vẫn không đổi. | Login hoặc bundle vẫn đi tới endpoint chính thức, staging hoặc endpoint cũ. |
| `production-shared-api-base` | Thay encrypted shared API base dùng cho request trực tiếp như `/user/me/save`. Base này tách biệt với các chuỗi login và aggregate nhìn thấy được. | Login có vẻ thành công, nhưng Network hoặc Cloud Sync trả `-4`, client báo tài khoản bị đăng xuất bởi thiết bị khác và session không dùng được sau restart. |
| `byd-allowlist`, `byd-registry-hook` | Cho native active-state registry chấp nhận đúng các song ID class 3: `pentiment`, `arcanaeden`, `worldender`, `testify`, `infinitestrife`, `last`, `lasteternity` và `axiumcrisis`. | Ô BYD biến mất hoặc hiện ra nhưng không chọn được dù chart và entitlement đã tồn tại. Allowlist chỉ tác động đến các bài đã nêu. |
| `divine-gate`, `divine-cell-a`, `divine-cell-b` | Mở đúng reveal path và selector cell của Divine. | Bài đã có trong bundle nhưng selector vẫn đen hoặc thiếu. Jacket và preview vẫn phải có trong bundle. |
| `aether-guard-cave`, `aether-guard-hook` | Kiểm tra null trước khi client duyệt special-condition list của Aether Crest; đường đi bình thường không bị đổi. | Mở hoặc bắt đầu Aether Crest ETR có thể dereference danh sách không tồn tại và crash. |
| `dread-area` | Sửa pre-start condition path của Dread Area. | Bài chọn được nhưng lỗi ngay trước khi vào gameplay. |
| `crash-logger` | Giữ nhánh native crash logger ở trạng thái tắt như release đã kiểm thử. Patch này không mở khóa nội dung và không ẩn lỗi Java khỏi logcat. | Client đi qua crash-reporting path khác với release đã xác minh. |
| `fmod-18-read-contract` | Sửa kết quả đọc file trong `libfmodProvider.so` cho đúng contract FMOD mong đợi. | Nhạc có thể trả FMOD error 18 hoặc crash khi bắt đầu dù file âm thanh vẫn tồn tại. |

Phần route cần được hiểu rõ: Arcaea không tạo mọi request từ một hostname dạng text.
Login, aggregate và content bundle có chuỗi URL riêng, còn các endpoint khác dùng shared
base đã mã hóa. Cả hai lớp phải trỏ về cùng server. Vì vậy client vẫn có thể login nhưng
Cloud Sync hỏng nếu thiếu `production-shared-api-base`.

Các hoạt động byte được bảo vệ được liệt kê ở trên được xuất bản trong
`patches/arcaea-7.0.255-arm64/native-plan.json`. Chúng được tạo từ nền tảng APK đã được
xác minh và có thể tái tạo mà không cần prebuilt patched native library. README cạnh
plan có command và receipt check chính xác.

Package rename và managed AKFC bridge nằm trong
`scripts/patch_android_client_sources.py` cùng thư mục `smali` cạnh native plan. Phần
tiếp theo giải thích các thay đổi trước khi áp dụng.

Repository cũng chứa C++ source và command build AKFC loader. Mỗi operator tạo một cặp
khóa RSA 3072-bit riêng; private key chỉ được nhúng vào loader của operator đó, còn
public key dùng để mã hóa chart.

## Bước 1: chọn địa điểm build

```powershell
$outputFolder = Read-Host "Full path for build output"
$outputFolder = [IO.Path]::GetFullPath($outputFolder)
New-Item -ItemType Directory -Force $outputFolder | Out-Null

$decoded = Join-Path $outputFolder "decoded"
$managedApk = Join-Path $outputFolder "AkaineXD-managed-unsigned.apk"
$unsignedApk = Join-Path $outputFolder "AkaineXD-unsigned.apk"
$alignedApk = Join-Path $outputFolder "AkaineXD-aligned.apk"
$signedApk = Join-Path $outputFolder "AkaineXD-release.apk"
```

## Bước 2: decode baseline đã hợp nhất

```powershell
$apktool = Get-Item (Read-Host "Full path to apktool_2.12.1.jar")
Get-FileHash -Algorithm SHA256 $apktool.FullName

java -Xmx6g -jar $apktool.FullName decode -f `
  $baseline `
  -o $decoded
```

File Apktool phải có kích thước 25.926.183 byte với SHA-256
`66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa`.

## Bước 3: vá các managed source

Tập lệnh này chỉnh sửa các file có thể đọc được do Apktool tạo ra. Những thay đổi của nó
tuy nhỏ nhưng phải thống nhất với nhau:

| File | Thay đổi | Lý do |
| --- | --- | --- |
| `AndroidManifest.xml` | Đổi `moe.low.arc` thành `akai.arc.lmao`, gồm bảy component authority và host/scheme của login callback. | Android coi package là danh tính ứng dụng. Provider authority và callback phải theo package mới, nếu không thao tác share hoặc login có thể trỏ nhầm app. Package mới cũng cho phép cài riêng với client chính thức. |
| `res/values/strings.xml` | Đổi launcher label từ Arcaea thành AkaineXD. | Đây chỉ là tên Android hiển thị, không đổi mạng hay gameplay. |
| `BuildConfig.smali` | Đặt `APPLICATION_ID` thành `akai.arc.lmao`. | Build identity mà code đọc phải khớp manifest package. |
| `AppActivity.smali` | Cập nhật share provider authority, gọi `AkfcLoader.init()` sau khi native library đã load và gọi `wipeDecrypted()` khi activity bị hủy. | Loader chỉ hook được `libcocos2dcpp.so` sau khi library tồn tại; plaintext chart phải được xóa khi activity kết thúc. |
| `AkfcLoader.smali` | Thêm cầu nối Java-to-native cho hai hàm của loader. | Java cần JNI bridge để gọi export C++. |

Mỗi thay đổi đều có số lần khớp dự kiến. Không tìm thấy chuỗi thường có nghĩa là đầu vào
sai phiên bản. Tìm thấy quá nhiều lần khiến script không chứng minh được vị trí nào an
toàn. Cả hai trường hợp đều dừng build.

```powershell
Set-Location $repoRoot
python scripts\patch_android_client_sources.py `
  --decoded $decoded `
  --receipt (Join-Path $outputFolder "managed-patch-receipt.json")
```

Điều này chỉ thay đổi các chuỗi nguồn bị khóa phiên bản chính xác và thêm cầu nối Smali
công khai. Bất kỳ kết quả trùng khớp nào bị thiếu hoặc trùng lặp sẽ dừng quá trình xây
dựng.

## Bước 4: tạo khóa AKFC của server này

AKFC bảo vệ chart theo hai lớp. Chart được mã hóa bằng một khóa AES ngẫu nhiên; khóa AES
đó tiếp tục được bọc bằng RSA public key của operator. APK chứa private key tương ứng
dưới dạng dữ liệu C đã làm rối để mở khóa AES lúc chơi. Client build bằng private key
khác sẽ không đọc được protected chart này.

Tạo một cặp khóa cho cặp server/client và giữ nó cho các bản build sau này. Việc xoay nó
yêu cầu mã hóa lại các chart được bảo vệ bằng khóa chung cũ.

Private key nằm trong APK đã cài nên người có đủ thời gian vẫn có thể trích xuất nó.
AKFC làm việc sao chép chart đã phát hành khó hơn; đây không phải DRM dựa trên phần cứng
và không bảo đảm bí mật vĩnh viễn.

```powershell
$keyFolder = Read-Host "Private folder for this server's AKFC keys"
$keyFolder = [IO.Path]::GetFullPath($keyFolder)
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$keyHeader = Join-Path $keyFolder "embedded_key.h"

python scripts\generate_akfc_keypair.py `
  --private-key $privateKey `
  --public-key $publicKey

python scripts\generate_akfc_key_header.py `
  --private-key $privateKey `
  --output $keyHeader
```

Giữ private key và generated header bên ngoài Git. Server dùng public key khi mã hóa
AFF container.

## Bước 5: build AKFC loader

Cài đặt **NDK (Side by side)** từ Công cụ SDK của Android Studio, sau đó chọn thư mục
NDK:

```powershell
$env:ANDROID_NDK_ROOT = Read-Host "Full path to the installed Android NDK"
$loader = Join-Path $outputFolder "libakfcloader.so"
$nativeFolder = Join-Path $decoded "lib\arm64-v8a"
$cryptoWork = Join-Path $outputFolder "boringssl-work"
$crypto = Join-Path $outputFolder "libakfc-crypto.a"

python scripts\build_boringssl_android.py `
  --work $cryptoWork `
  --output $crypto

python scripts\build_akfc_loader.py `
  --source patches\arcaea-7.0.255-arm64\native\akfc_loader.cpp `
  --key-header $keyHeader `
  --crypto $crypto `
  --output $loader

Copy-Item $loader (Join-Path $nativeFolder "libakfcloader.so")
```

Symbol của BoringSSL nhận prefix `akfc_` trước khi link vào loader. Bản build không thêm
hay thay thế `libcrypto.so` dùng chung cho cả process, vì vậy AKFC runtime không thể can
thiệp vào crypto hoặc session đăng nhập của client.

Trong runtime, loader chỉ xử lý các file trông giống như
tải xuống chart và bắt đầu bằng byte ma thuật `AKFC`:

1. chặn request mở file hoặc đọc kích thước file;
2. chờ một lát nếu bản tải xuống `.tmp` chưa đạt kích thước đã khai báo;
3. xác thực identity của container và unwrap khóa AES;
4. giải mã AFF vào vùng lưu trữ riêng của app và báo đúng plaintext size cho chart
   reader;
5. xóa các plaintext file đã theo dõi khi Android activity bị hủy.

Asset thông thường tiếp tục đi qua hàm file gốc. Loader chỉ giải mã khi file có đúng
magic byte `AKFC`; riêng đuôi `.aff` không đủ để kích hoạt.

## Bước 6: rebuild và áp dụng các patch gốc được bảo vệ

Apktool biên dịch managed source đã sửa thành `classes.dex`, binary manifest và Android
resource. `build_android_client.py` mở APK vừa rebuild rồi chỉ sửa các native member có
guard. Thứ tự này giúp archive cuối chứa cả Android/JNI bridge lẫn native code mà bridge
gọi tới.

```powershell
java -Xmx6g -jar $apktool.FullName build `
  $decoded `
  -o $managedApk

python scripts\build_android_client.py `
  --source $managedApk `
  --plan patches\arcaea-7.0.255-arm64\native-plan.json `
  --kit-root $repoRoot `
  --output $unsignedApk

Get-Content "$unsignedApk.receipt.json"
```

Biên nhận phải liệt kê tất cả 17 nhãn gốc, bao gồm `production-shared-api-base`. Kế
hoạch này bảo vệ các hash `libcocos2dcpp.so` và `libfmodProvider.so` chính xác ban
đầu ngay cả khi Apktool thay đổi vùng chứa ZIP xung quanh.

## Bước 7: tìm Công cụ build Android

Sử dụng thư mục Build-Tools được fresh install nhất thay vì giả sử phiên bản hoặc ổ đĩa:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object Name -Descending |
  Select-Object -First 1

$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"

Get-Item $zipalign, $apksigner, $aapt
```

Tất cả ba tập tin phải tồn tại.

## Bước 8: align APK

Thư viện gốc yêu cầu căn chỉnh trang. Quy trình phát hành sử dụng căn chỉnh trang 16 KiB
và căn chỉnh ZIP 4 byte:

```powershell
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
& $zipalign -c -P 16 -v 4 $alignedApk
```

Lệnh thứ hai phải kết thúc bằng `Verification successful`.

## Bước 9: tạo signing identity tên của bạn một lần

Chọn vị trí lưu keystore và alias. Nếu đã tạo key cho package này, hãy dùng
lại nó; việc tạo khóa mới khiến cho việc cập nhật install-over không thể thực hiện được.

```powershell
$keystore = Read-Host "Full path for your private Android keystore"
$keystore = [IO.Path]::GetFullPath($keystore)
$keyAlias = Read-Host "Key alias"

if (-not (Test-Path $keystore)) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $keystore) | Out-Null
  keytool -genkeypair `
    -keystore $keystore `
    -alias $keyAlias `
    -keyalg RSA `
    -keysize 4096 `
    -validity 10000
}
```

`keytool` yêu cầu mật khẩu và nhận dạng chứng chỉ một cách tương tác. Lưu trữ mật khẩu
trong trình quản lý mật khẩu. Không bao giờ đặt kho khóa hoặc mật khẩu vào Git, bộ tài
nguyên, screenshot hoặc shell script.

Sao lưu kho khóa này một cách an toàn. Mất nó có nghĩa là các APK trong tương lai không
thể cập nhật ứng dụng đã cài đặt nếu không gỡ cài đặt và xóa dữ liệu cục bộ của ứng dụng
đó.

## Bước 10: ký và xác minh

```powershell
& $apksigner sign `
  --ks $keystore `
  --ks-key-alias $keyAlias `
  --v4-signing-enabled false `
  --out $signedApk `
  $alignedApk

& $apksigner verify --verbose --print-certs $signedApk
```

Việc xác minh phải báo cáo chữ ký v2 và v3 như đã được xác minh. Ghi lại chứng chỉ người
ký SHA-256; mọi bản build sau này cho cùng package phải báo cùng giá trị.

## Bước 11: kiểm tra package và phiên bản

```powershell
$badging = & $aapt dump badging $signedApk
$badging | Select-String "package:|application-label:|launchable-activity:"
```

Theo tiêu chí 7.0.255, kết quả phải hiển thị `akai.arc.lmao`, `AkaineXD`, phiên bản
`7.0.255`, version code `1209852` và `low.moe.AppActivity`.

Đồng thời ghi lại danh tính hiện vật:

```powershell
Get-Item $signedApk | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $signedApk
```

## Bước 12: chọn fresh install hoặc install-over

Kết nối thiết bị hoặc trình giả lập Android và chạy:

```powershell
adb devices
$package = "akai.arc.lmao"
adb shell pm path $package
```

Nếu package chưa được cài, hãy fresh install:

```powershell
adb install $signedApk
```

Chỉ install-over khi package đang cài có cùng signing certificate:

```powershell
adb install -r -d $signedApk
```

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` có nghĩa là người ký khác. Không tự động gỡ cài
đặt: việc gỡ cài đặt sẽ xóa dữ liệu ứng dụng cục bộ. Ký bằng khóa gốc hoặc đưa ra quyết
định sao lưu và fresh install rõ ràng.

## Bước 13: khởi chạy với nhật ký sạch

```powershell
$package = "akai.arc.lmao"
$activity = "low.moe.AppActivity"

adb logcat -c
adb shell am force-stop $package
adb shell am start -n "$package/$activity"
Start-Sleep -Seconds 10
adb shell pidof $package
```

PID chỉ cho thấy rằng quá trình này đang hoạt động. Lưu nhật ký hoàn chỉnh trước khi tái
tạo sự cố:

```powershell
$logFile = Join-Path $outputFolder "client-logcat.txt"
adb logcat -d | Set-Content -Encoding utf8 $logFile

Select-String -Path $logFile -Pattern `
  "Fatal signal","FATAL EXCEPTION","JNI DETECTED ERROR", `
  "FileUtilsSaveError","LoadUnlocksMap","Cocos2dxDownloader", `
  "ClassNotFoundException","FMOD"
```

## Bước 14: kiểm tra tiêu chí release

Kiểm tra theo thứ tự này để lỗi xác định lớp chịu trách nhiệm:

1. Đến màn hình tiêu đề mà không cần vòng lặp khởi động.
2. Hoàn tất quá trình tải xuống content bundle mới và khởi động lại ứng dụng.
3. Đăng ký hoặc đăng nhập.
4. Sử dụng **Cloud Sync → Tải xuống** và quay lại màn hình tiêu đề.
5. Mở Music Play và chờ preview phát.
6. Mở một bài official thông thường và bắt đầu chart.
7. Kiểm tra jacket và preview của các bài Divine.
8. Kiểm tra Final Verdict BYD cho Infinite Strife, Arcana Eden, Pentiment, World
   Ender, Testify, Last và Last Eternity.
9. Kiểm tra Axium Crisis BYD/Axium Divergence.
10. Mở Aether Crest ETR.
11. Tải xuống và bắt đầu một protected fan chart.
12. Khởi động lại ứng dụng và lặp lại một chart chính thức và một chart được bảo vệ.

Không gọi bản build sẵn sàng phát hành sau khi chỉ đến màn hình tiêu đề.

## Chẩn đoán lỗi theo giai đoạn

| Triệu chứng | Lớp nghi vấn | Kiểm tra đầu tiên |
| --- | --- | --- |
| APK không cài được | signing/alignment | `apksigner verify`, `zipalign -c`, signer không khớp |
| Crash trước title sau khi bundle đạt 100% | tính toàn vẹn của bundle catalog | mọi song `set` và child `pack_parent` đều trỏ tới pack tồn tại |
| Login hoặc content bundle dùng sai server | native route patch | input hash của plan, production/staging route, giới hạn byte của URL |
| Music Play mở nhưng một nhóm bài bị đen | selector asset trong bundle | jacket và preview entry; không sửa bằng global unlock flag |
| Ô BYD không xuất hiện hoặc không chọn được | native registry gate | đúng song ID và difficulty class trong allowlist |
| Aether Crest ETR crash | native special-condition list | null guard có trong patch plan đã chọn |
| Protected chart tải xong nhưng không chơi được | AKFC runtime | loader, prefixed static crypto và DEX integration cùng một patch set 7.0.255 |
| Download icon không biến mất | server metadata/object set | file khai báo, hash và hidden shell chart khớp dữ liệu phân phối |
| Chạy được một lần nhưng hỏng sau restart | persisted content chưa đầy đủ | lấy logcat từ cold start và kiểm tra trạng thái bundle đã tải |

Không sửa bundle boot crash bằng cách xóa pack entry ngẫu nhiên. Không được xóa một pack
khi song `set` hoặc child `pack_parent` vẫn tham chiếu tới nó.

## Danh sách kiểm tra phát hành

Giữ một receipt ngắn cho mỗi candidate:

- nguồn APK SHA-256;
- native patch plan SHA-256;
- output APK SHA-256 và kích thước;
- package, label, version name và version code;
- signer certificate SHA-256;
- APK member đã thay thế;
- API/bundle route target;
- bundle version đã test;
- kết quả fresh install hoặc install-over;
- tiêu đề, thông tin đăng nhập, Cloud Sync, chart chính thức, BYD/ETR đặc biệt và kết
  quả chart được bảo vệ;
- kết quả quét crash pattern;
- các vấn đề đã biết còn tồn tại.

Giữ APK đã ký trước đó cho tới khi candidate mới vượt qua checklist. Rollback nghĩa là
install-over APK known-good có cùng signer, không phải xóa app data hay phục hồi một cơ
sở dữ liệu không liên quan.

## Các tập tin luôn ở chế độ riêng tư

GitHub cố ý không chứa:

- APK nguồn;
- prebuilt modified native library hoặc DEX payload;
- signing key sản xuất;
- game asset thương mại;
- private chart encryption material;
- production domain, credentials hoặc dữ liệu người chơi.

Quá trình build là công khai. Các đầu vào mà dự án không thể phân phối lại vẫn ở chế
độ riêng tư và được xác minh bằng hash trước khi sử dụng.
