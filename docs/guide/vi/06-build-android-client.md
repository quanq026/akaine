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
$xapkExpectedSize = 1219427332
$xapkExpectedHash = "459bb01f8357dde82b13a817d4dd5dbf81e7a70d0805cc0d5f1aebde36fa2b7a"
$xapkHash = (Get-FileHash -Algorithm SHA256 $xapk.FullName).Hash.ToLowerInvariant()

if ($xapk.Length -ne $xapkExpectedSize -or $xapkHash -ne $xapkExpectedHash) {
  throw "XAPK size or SHA-256 does not match the verified arm64 input."
}

$xapk | Select-Object Name, Length
$xapkHash
```

Cả kích thước và SHA-256 phải khớp. File của 7.0.256, biến thể armeabi-v7a hoặc bản đã
được mirror đóng gói lại không thể thay thế đầu vào này. Native offset và byte guard
chỉ đúng với build đã nêu.

`Get-Item` xác định đường dẫn và đọc kích thước file thật. Hai biến tiếp theo giữ giá
trị tham chiếu đã xác minh. `Get-FileHash` đọc toàn bộ download nên có thể mất một lúc
với file 1,2 GB. Câu lệnh `if` dừng nếu một trong hai giá trị sai. Thấy hai dòng output
cuối nghĩa là input gate đã pass; XAPK chưa bị chỉnh sửa.

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

$apkEditorExpectedSize = 7733037
$apkEditorExpectedHash = "a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67"
$apkEditorHash = (Get-FileHash -Algorithm SHA256 $apkEditor.FullName).Hash.ToLowerInvariant()
if ($apkEditor.Length -ne $apkEditorExpectedSize -or $apkEditorHash -ne $apkEditorExpectedHash) {
  throw "APKEditor size or SHA-256 does not match the verified tool."
}

java -Xmx4g -jar $apkEditor.FullName merge `
  -i $xapk.FullName `
  -o $baseline
if ($LASTEXITCODE -ne 0) {
  throw "XAPK merge failed."
}

$baselineExpectedSize = 1206740473
$baselineExpectedHash = "746dd90c2efac21fc88ffd032e5a71c78c0955766477382c7f48ece87e23026e"
$baselineInfo = Get-Item $baseline
$baselineHash = (Get-FileHash -Algorithm SHA256 $baseline).Hash.ToLowerInvariant()
if ($baselineInfo.Length -ne $baselineExpectedSize -or $baselineHash -ne $baselineExpectedHash) {
  throw "Merged baseline does not match the verified reference."
}
```

`-Xmx4g` cho Java merge process dùng tối đa 4 GiB RAM. `merge` yêu cầu APKEditor gộp
split module, `-i` chọn XAPK và `-o` chọn đường dẫn APK mới. Lệnh không sửa `$xapk`.
Gate kích thước/hash cuối chứng minh năm module dự kiến đã tạo đúng baseline dùng để
xây các patch phía sau.

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
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")
if (-not $sdk) {
  throw "ANDROID_SDK_ROOT is not set. Return to chapter 3."
}

$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object { [version]$_.Name } -Descending |
  Select-Object -First 1

if (-not $buildTools) {
  throw "No Android Build-Tools installation was found."
}
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
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

Set-Location $repoRoot
Get-Item $python
& $python scripts\doctor.py --android
```

Không tiếp tục trừ khi quá trình kiểm tra công cụ nghiêm ngặt vượt qua.

Ba dòng đầu tải lại các vị trí đã lưu ở chương 3 và 4. Dòng thứ tư chọn Python trong
virtual environment của repository, nơi đã có package `cryptography` cần thiết; dùng
nhầm system Python có thể làm bước tạo khóa lỗi. `Set-Location` giúp mọi đường dẫn tương
đối trong chương bắt đầu từ cùng một nơi. `Get-Item` chứng minh virtual environment tồn
tại trước khi `doctor.py` kiểm tra Java, adb, Apktool, zipalign và apksigner. Dòng cuối
phải kết thúc bằng `Requested toolchain is ready.`

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

## Cách làm theo các bước build

Hãy dùng một cửa sổ PowerShell duy nhất từ bước 1 đến bước 14. Các biến như
`$outputFolder` và `$signedApk` chỉ tồn tại trong cửa sổ đó. Đóng PowerShell không xóa
file đã tạo, nhưng bạn phải chạy lại các block đặt biến trước khi tiếp tục.

Mỗi lần chỉ paste một code block. Chờ dấu nhắc PowerShell xuất hiện trở lại rồi mới
paste block tiếp theo. Nếu lệnh in lỗi màu đỏ hoặc `$LASTEXITCODE` khác không, hãy dừng
ngay tại bước đó. Chạy tiếp thường chỉ che lỗi đầu tiên bằng nhiều lỗi phát sinh sau.

Cú pháp PowerShell được dùng trong chương này:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `$name = value` | Lưu một giá trị vào biến tạm. Nó không tạo file trừ khi lệnh ở bên phải có tạo file. |
| `Read-Host "Question"` | Dừng để chờ bạn nhập giá trị. Chỉ nhập đường dẫn; không nhập dấu nhắc `>` và không tự thêm dấu ngoặc kép. |
| Dấu `` ` `` ở cuối dòng | Tiếp tục cùng một lệnh ở dòng sau. Phía sau dấu backtick không được có ký tự nào, kể cả dấu cách. |
| `& $tool` | Chạy file thực thi có đường dẫn đầy đủ đang nằm trong biến `$tool`. |
| `|` | Chuyển output của lệnh bên trái sang lệnh bên phải. |
| `Join-Path $folder "name"` | Ghép đường dẫn mà không giả định ký tự ổ đĩa hoặc kiểu dấu gạch chéo. |
| `$LASTEXITCODE` | Mã thoát của chương trình native vừa chạy. Giá trị không là thành công. |

Quy trình build đi qua các artifact sau:

| Artifact | Được tạo bởi | Mục đích | Có giữ sau release không? |
| --- | --- | --- | --- |
| Arm64 XAPK | Tải xuống | Input upstream đã xác minh, chứa năm module split APK. | Giữ hash và một bản local mà bạn có quyền sử dụng. |
| Merged baseline APK | APKEditor | Một APK chứa base, thư viện arm64 và asset split. | Giữ tới khi release được chấp nhận. |
| Thư mục `decoded` | Apktool decode | Manifest, resource và Smali có thể đọc cùng native library đã giải nén. | Có thể build lại; được phép xóa sau release. |
| Managed unsigned APK | Apktool build | Package rename, label và AKFC Java/Smali bridge đã compile lại vào APK. | File trung gian có thể build lại. |
| Unsigned patched APK | Akaine builder | Managed APK cộng các thay đổi native đã guard cho route, gameplay và FMOD. | Giữ receipt; APK có thể build lại. |
| Aligned APK | `zipalign` | Archive chưa ký có ZIP alignment và native-library alignment đúng yêu cầu Android. | File trung gian có thể build lại. |
| Signed release APK | `apksigner` | Artifact cài được, gắn với signing identity của bạn. | Phải giữ, ghi hash và sao lưu. |

Không sửa APK trung gian bằng chương trình ZIP giữa các bước. Mọi thay đổi sau align sẽ
làm sai alignment; mọi thay đổi sau ký sẽ làm chữ ký mất hiệu lực.

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

Giải thích từng dòng:

1. `Read-Host` hỏi nơi được phép ghi vài gigabyte dữ liệu tạm của lần build này. Một
   thư mục mới và rỗng sẽ dễ chẩn đoán nhất.
2. `GetFullPath` chuyển input tương đối như `build` thành một đường dẫn tuyệt đối rõ
   ràng.
3. `New-Item` tạo thư mục. `-Force` chỉ cho phép dùng thư mục đã tồn tại; nó không xóa
   nội dung trong đó.
4. Năm dòng `Join-Path` đặt tên cho các output ở bước sau. Chúng chưa build file nào.

Tại thời điểm này chỉ `$outputFolder` phải tồn tại. Nếu nó có file từ lần build lỗi,
hãy chọn thư mục mới để không nhầm file trung gian cũ với kết quả hiện tại.

## Bước 2: decode baseline đã hợp nhất

```powershell
$apktool = Get-Item (Read-Host "Full path to apktool_2.12.1.jar")
Get-FileHash -Algorithm SHA256 $apktool.FullName

java -Xmx6g -jar $apktool.FullName decode -f `
  $baseline `
  -o $decoded
```

Ý nghĩa từng phần:

| Phần | Ý nghĩa |
| --- | --- |
| `$apktool = Get-Item ...` | Hỏi đường dẫn jar và dừng ngay nếu file đó không tồn tại. |
| `Get-FileHash` | Tính danh tính của jar trước khi chạy code đã tải về. |
| `java` | Khởi động Java runtime đã cài ở chương 3. |
| `-Xmx6g` | Cho Apktool dùng tối đa 6 GiB RAM. Đây là giới hạn, không phải cấp ngay 6 GiB. |
| `-jar $apktool.FullName` | Chạy Apktool jar đã xác minh. |
| `decode` | Chuyển Android resource nhị phân và biểu diễn DEX thành thư mục có thể chỉnh sửa. |
| `-f` | Thay kết quả decode cũ ở output đã chọn. Vì vậy build folder không được chứa công việc bạn cần giữ. |
| `$baseline` | Input là APK đã merge và kiểm tra hash, không phải XAPK gốc hoặc một split APK. |
| `-o $decoded` | Output là thư mục decoded đã đặt tên ở bước 1. |

Xác nhận decode đã hoàn thành và tạo đủ bốn input mà managed patcher sẽ dùng:

```powershell
if ($LASTEXITCODE -ne 0) {
  throw "Apktool decode failed. Do not continue to patching."
}

$requiredDecoded = @(
  (Join-Path $decoded "AndroidManifest.xml")
  (Join-Path $decoded "res\values\strings.xml")
  (Join-Path $decoded "smali\low\moe\AppActivity.smali")
  (Join-Path $decoded "lib\arm64-v8a\libcocos2dcpp.so")
)

Get-Item $requiredDecoded | Select-Object FullName, Length
```

Cả bốn dòng phải xuất hiện với dung lượng khác không. Thiếu arm64 library thường có
nghĩa là XAPK chưa được merge đúng hoặc bạn đã chọn sai kiến trúc.

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
& $python scripts\patch_android_client_sources.py `
  --decoded $decoded `
  --receipt (Join-Path $outputFolder "managed-patch-receipt.json")
```

Điều này chỉ thay đổi các chuỗi nguồn bị khóa phiên bản chính xác và thêm cầu nối Smali
công khai. Bất kỳ kết quả trùng khớp nào bị thiếu hoặc trùng lặp sẽ dừng quá trình xây
dựng.

Dòng đầu quay lại repository để đường dẫn tương đối `scripts\...` trỏ đúng file.
`--decoded` chọn thư mục sẽ bị chỉnh sửa. `--receipt` ghi lại từng file đã thay đổi và
hash trước/sau; đây là bằng chứng build, không phải APK.

Kiểm tra kết quả trước khi compile:

```powershell
$managedReceiptPath = Join-Path $outputFolder "managed-patch-receipt.json"
$managedReceipt = Get-Content $managedReceiptPath -Raw | ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or $managedReceipt.status -ne "patched") {
  throw "Managed patch did not complete."
}

$managedReceipt.changes |
  Select-Object path, before_sha256, after_sha256 |
  Format-Table -AutoSize
```

Bảng phải có `AndroidManifest.xml`, `strings.xml`, `BuildConfig.smali`,
`AppActivity.smali` và `AkfcLoader.smali` vừa được thêm. Receipt trống hoặc bị thiếu có
nghĩa là bước này chưa hoàn thành. Không tự tạo receipt để bỏ qua kiểm tra.

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

if (-not (Test-Path $privateKey) -and -not (Test-Path $publicKey)) {
  & $python scripts\generate_akfc_keypair.py `
    --private-key $privateKey `
    --public-key $publicKey
} elseif (-not (Test-Path $privateKey) -or -not (Test-Path $publicKey)) {
  throw "Only one AKFC key exists. Restore the matching pair from backup."
}

& $python scripts\generate_akfc_key_header.py `
  --private-key $privateKey `
  --output $keyHeader

Get-Item $privateKey, $publicKey, $keyHeader |
  Select-Object Name, Length
```

Giữ private key và generated header bên ngoài Git. Server dùng public key khi mã hóa
AFF container.

Ba dòng `Join-Path` đầu đặt tên cho cặp khóa và C header được sinh ra. Nhánh `if` chỉ
tạo cặp mới khi cả hai khóa đều chưa tồn tại. Nhánh `elseif` dừng nếu chỉ còn một nửa
cặp khóa; tạo lại nửa còn thiếu sẽ cho hai khóa không thể làm việc cùng nhau. Ở các lần
build sau, hai khóa cũ được dùng lại và chỉ `embedded_key.h` được tạo lại.

`--private-key` là RSA key sẽ được nhúng vào loader. `--public-key` là encryption key
tương ứng mà phía đóng gói chart sử dụng. `--output` ghi dữ liệu C cho native compiler.
Lệnh cuối chỉ in tên và kích thước file, không hiển thị nội dung private key.

## Bước 5: build AKFC loader

Cài đặt **NDK (Side by side)** từ Công cụ SDK của Android Studio, sau đó chọn thư mục
NDK:

```powershell
$env:ANDROID_NDK_ROOT = Read-Host "Full path to the installed Android NDK"
$loader = Join-Path $outputFolder "libakfcloader.so"
$nativeFolder = Join-Path $decoded "lib\arm64-v8a"
$cryptoWork = Join-Path $outputFolder "boringssl-work"
$crypto = Join-Path $outputFolder "libakfc-crypto.a"

& $python scripts\build_boringssl_android.py `
  --work $cryptoWork `
  --output $crypto
if ($LASTEXITCODE -ne 0) {
  throw "BoringSSL build failed."
}

& $python scripts\build_akfc_loader.py `
  --source patches\arcaea-7.0.255-arm64\native\akfc_loader.cpp `
  --key-header $keyHeader `
  --crypto $crypto `
  --output $loader
if ($LASTEXITCODE -ne 0) {
  throw "AKFC loader build failed."
}

Copy-Item $loader (Join-Path $nativeFolder "libakfcloader.so")
Get-Item $crypto, $loader, (Join-Path $nativeFolder "libakfcloader.so") |
  Select-Object FullName, Length
```

Giải thích từng dòng:

1. `ANDROID_NDK_ROOT` cho hai Python build script biết phải dùng NDK toolchain nào.
   Tiền tố `$env:` truyền giá trị cho process con trong cửa sổ PowerShell hiện tại; nó
   không thay đổi Windows vĩnh viễn.
2. `$loader` là arm64 shared library đã compile. `$nativeFolder` là đúng thư mục mà
   Apktool sẽ đóng gói thành `lib/arm64-v8a/`.
3. `$cryptoWork` chứa BoringSSL checkout đã ghim revision và output CMake. Lần build
   đầu phải tải và compile nên có thể mất vài phút. Lần sau dùng lại checkout sau khi
   kiểm tra revision.
4. `$crypto` là static archive sau khi mọi exported symbol được thêm prefix `akfc_`.
5. `build_akfc_loader.py` compile `akfc_loader.cpp`, include key header đã tạo và link
   prefixed crypto archive.
6. `Copy-Item` đặt loader đã hoàn thành vào decoded APK tree. Nếu chỉ build mà không
   copy, library vẫn nằm ngoài APK.

Bảng cuối phải hiện ba file không rỗng. Hai dòng loader phải có cùng kích thước vì một
file là build output và file kia là bản copy trong decoded tree. Thiếu `cmake`, `ninja`,
compiler hoặc `llvm-objcopy` là lỗi cài NDK/SDK; hãy quay lại Android Studio SDK Tools
thay vì sửa script.

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
if ($LASTEXITCODE -ne 0) {
  throw "Apktool rebuild failed."
}

& $python scripts\build_android_client.py `
  --source $managedApk `
  --plan patches\arcaea-7.0.255-arm64\native-plan.json `
  --kit-root $repoRoot `
  --output $unsignedApk
if ($LASTEXITCODE -ne 0) {
  throw "Guarded native patch failed."
}

$nativeReceiptPath = "$unsignedApk.receipt.json"
$nativeReceipt = Get-Content $nativeReceiptPath -Raw | ConvertFrom-Json
$nativeLabels = @()
foreach ($property in $nativeReceipt.binary_patch_labels.PSObject.Properties) {
  $nativeLabels += @($property.Value)
}

if ($nativeReceipt.status -ne "unsigned-built") {
  throw "Native build receipt is not complete."
}
if ($nativeLabels.Count -ne 17 -or $nativeLabels -notcontains "production-shared-api-base") {
  throw "Native patch receipt does not contain the full release plan."
}

Get-Item $managedApk, $unsignedApk | Select-Object Name, Length
$nativeLabels | Sort-Object
```

Biên nhận phải liệt kê tất cả 17 nhãn gốc, bao gồm `production-shared-api-base`. Kế
hoạch này bảo vệ các hash `libcocos2dcpp.so` và `libfmodProvider.so` chính xác ban
đầu ngay cả khi Apktool thay đổi vùng chứa ZIP xung quanh.

Lệnh Apktool `build` chuyển toàn bộ decoded tree thành APK trở lại. Lệnh tiếp theo có
bốn input:

| Tham số | Ý nghĩa |
| --- | --- |
| `--source $managedApk` | APK chứa managed edit và AKFC loader vừa compile. |
| `--plan ...native-plan.json` | Danh sách native operation có guard, khóa theo phiên bản. |
| `--kit-root $repoRoot` | Root dùng để tìm public source payload mà plan gọi tên. Trong lệnh này nó không phải private resource kit. |
| `--output $unsignedApk` | APK mới nhận native change. File này vẫn chưa được ký. |

Builder xác minh source member trước khi sửa, xóa v1 signature entry cũ, ghi qua file
tạm và tạo receipt cạnh APK. Block kiểm tra đếm đủ 17 operation label và kiểm tra patch
shared API base rất dễ bị bỏ sót. Nếu block này lỗi, không ký APK dù `$unsignedApk` tình
cờ đã tồn tại.

## Bước 7: tìm Công cụ build Android

Sử dụng thư mục Build-Tools được fresh install nhất thay vì giả sử phiên bản hoặc ổ đĩa:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object { [version]$_.Name } -Descending |
  Select-Object -First 1

if (-not $buildTools) {
  throw "No Android Build-Tools installation was found."
}

$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"

Get-Item $zipalign, $apksigner, $aapt
```

Tất cả ba tập tin phải tồn tại.

`Get-ChildItem` liệt kê các Build-Tools version đã cài. Pipeline đưa từng tên folder
qua `[version]` để `35.0.0` được xếp đúng cao hơn `9.0.0`. `Select-Object -First 1`
giữ bản mới nhất. Ba dòng `Join-Path` đặt tên chính xác cho executable dùng ở dưới;
`Get-Item` là bước kiểm tra file tồn tại cuối cùng.

## Bước 8: align APK

Thư viện gốc yêu cầu căn chỉnh trang. Quy trình phát hành sử dụng căn chỉnh trang 16 KiB
và căn chỉnh ZIP 4 byte:

```powershell
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK alignment failed."
}
& $zipalign -c -P 16 -v 4 $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "Aligned APK verification failed."
}
```

Lệnh thứ hai phải kết thúc bằng `Verification successful`.

`-P 16` align native library không nén cho memory page 16 KiB. `-f` cho phép thay output
aligned cũ ở đường dẫn đã chọn. `-v` in quá trình làm việc, còn `4` áp dụng ZIP alignment
bốn byte thông thường. Lệnh thứ hai dùng `-c` để kiểm tra thay vì ghi. Đây là gate riêng:
chỉ thấy `$alignedApk` tồn tại chưa chứng minh alignment thành công.

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
  if ($LASTEXITCODE -ne 0) {
    throw "Android signing-key generation failed."
  }
}

Get-Item $keystore | Select-Object FullName, Length, LastWriteTime
```

`keytool` yêu cầu mật khẩu và nhận dạng chứng chỉ một cách tương tác. Lưu trữ mật khẩu
trong trình quản lý mật khẩu. Không bao giờ đặt kho khóa hoặc mật khẩu vào Git, bộ tài
nguyên, screenshot hoặc shell script.

Sao lưu kho khóa này một cách an toàn. Mất nó có nghĩa là các APK trong tương lai không
thể cập nhật ứng dụng đã cài đặt nếu không gỡ cài đặt và xóa dữ liệu cục bộ của ứng dụng
đó.

`-keystore` chọn private key container, còn `-alias` đặt tên cho một key bên trong.
`-keyalg RSA -keysize 4096` tạo signing key; nó không liên quan tới RSA-3072 AKFC chart
key riêng. `-validity 10000` giữ signing certificate hợp lệ trong 10.000 ngày. Với một
deployment test cá nhân, các câu hỏi về danh tính có thể dùng giá trị mô tả; chúng không
thay đổi package name.

Guard `if` là có chủ đích. Nếu keystore đã tồn tại, lệnh không tạo signer mới. Hãy xác
nhận đường dẫn được in ra nằm ngoài Git repository trước khi tiếp tục.

## Bước 10: ký và xác minh

```powershell
& $apksigner sign `
  --ks $keystore `
  --ks-key-alias $keyAlias `
  --v4-signing-enabled false `
  --out $signedApk `
  $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK signing failed."
}

& $apksigner verify --verbose --print-certs $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK signature verification failed."
}
```

Việc xác minh phải báo cáo chữ ký v2 và v3 như đã được xác minh. Ghi lại chứng chỉ người
ký SHA-256; mọi bản build sau này cho cùng package phải báo cùng giá trị.

`sign` đọc aligned APK và ghi một file khác tại `--out`; nó không sửa aligned input.
`--ks` và `--ks-key-alias` chọn identity đã tạo ở bước 9. V4 signing bị tắt vì guide
phân phối một APK thay vì APK đi kèm file `.idsig` riêng. Lệnh verify đọc APK hoàn chỉnh,
kiểm tra các signing scheme và in certificate digest dùng cho so sánh install-over sau
này.

## Bước 11: kiểm tra package và phiên bản

```powershell
$badging = & $aapt dump badging $signedApk
$badging | Select-String "package:|application-label:|launchable-activity:"
```

Theo tiêu chí 7.0.255, kết quả phải hiển thị `akai.arc.lmao`, `AkaineXD`, phiên bản
`7.0.255`, version code `1209852` và `low.moe.AppActivity`.

`aapt dump badging` đọc metadata từ APK mà không cần cài. Dòng đầu chứa package,
version code và version name. Dòng label điều khiển tên ở launcher. Dòng
launchable-activity cho Android biết activity nào mở từ icon. Nếu bất kỳ giá trị nào
khác, hãy quay lại bước managed patch hoặc chọn input; đổi tên file không sửa được APK
metadata.

Đồng thời ghi lại danh tính hiện vật:

```powershell
Get-Item $signedApk | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $signedApk
```

## Bước 12: chọn fresh install hoặc install-over

Kết nối thiết bị hoặc trình giả lập Android và chạy:

```powershell
adb devices
$serial = Read-Host "Device serial shown in the first column above"
$package = "akai.arc.lmao"
adb -s $serial shell pm path $package
```

`adb devices` phải hiện thiết bị cần dùng với trạng thái `device`. `unauthorized` có
nghĩa là phải mở khóa màn hình và chấp nhận USB-debugging prompt. `offline` có nghĩa là
kết nối lại hoặc khởi động lại emulator. `$serial` buộc mọi lệnh sau nhắm đúng thiết bị
bạn chọn thay vì để adb tự chọn thiết bị đầu tiên.

`pm path` chỉ đọc thông tin. Dòng bắt đầu bằng `package:` nghĩa là AkaineXD đã được cài.
Thông báo `package ... was not found` nghĩa là đây là fresh install.

Nếu package chưa được cài, hãy fresh install:

```powershell
adb -s $serial install $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "Fresh APK installation failed."
}
```

Chỉ install-over khi package đang cài có cùng signing certificate:

```powershell
adb -s $serial install -r -d $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "Install-over failed."
}
```

Với install-over, `-r` giữ application data và thay APK. `-d` cho phép cài lại cùng
version code hoặc version code thấp hơn trong kiểm thử có kiểm soát; nó không bỏ qua
kiểm tra chữ ký. Lệnh thành công kết thúc bằng `Success`.

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` có nghĩa là người ký khác. Không tự động gỡ cài
đặt: việc gỡ cài đặt sẽ xóa dữ liệu ứng dụng cục bộ. Ký bằng khóa gốc hoặc đưa ra quyết
định sao lưu và fresh install rõ ràng.

## Bước 13: khởi chạy với nhật ký sạch

```powershell
$package = "akai.arc.lmao"
$activity = "low.moe.AppActivity"

adb -s $serial logcat -c
adb -s $serial shell am force-stop $package
adb -s $serial shell am start -n "$package/$activity"
Start-Sleep -Seconds 10
adb -s $serial shell pidof $package
```

Dòng đầu xóa log cũ trên thiết bị để crash của bản build khác không lẫn vào lần test
này. `force-stop` tạo cold process start. `am start` mở đúng cặp package/activity. Thời
gian chờ mười giây cho native library và start screen load. `pidof` phải in ra một số;
kết quả rỗng nghĩa là process đã thoát và cần thu log ngay.

PID chỉ cho thấy rằng quá trình này đang hoạt động. Lưu nhật ký hoàn chỉnh trước khi tái
tạo sự cố:

```powershell
$logFile = Join-Path $outputFolder "client-logcat.txt"
adb -s $serial logcat -d | Set-Content -Encoding utf8 $logFile

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

Mỗi lần chỉ làm một hành động đã đánh số. Ghi `PASS` hoặc `FAIL`, thời gian trên máy và
những gì thấy trên màn hình. Nếu app đóng, treo hoặc tự quay về title screen, hãy ngừng
thao tác và lưu logcat trước khi mở lại. Mở lại trước có thể đẩy dòng crash hữu ích ra
khỏi log buffer.

Dùng các điều kiện chấp nhận sau:

| Hạng mục | Pass | Điều kiện fail và phải dừng |
| --- | --- | --- |
| Bundle | Download và checking tới 100%, mở được title/menu, restart không tải lại. | `-1013`, tải lặp, crash trước title hoặc loading loop. |
| Login/session | Tài khoản vẫn đăng nhập sau khi tắt mở app hoàn toàn. | Login được một lần nhưng lần mở sau quay về guest. |
| Cloud Sync | Download hoàn thành, quay lại bình thường và session vẫn hoạt động sau restart. | Lỗi `-4`, thông báo “another device”, logout hoặc sync lỗi. |
| Official audio/chart | Preview phát và chart bắt đầu mà không có FMOD error. | Preview im lặng, FMOD 18, process thoát hoặc quay lại trước gameplay. |
| Divine/BYD/ETR | Jacket và difficulty tile render, tile bấm được và gameplay bắt đầu. | Selector đen, thiếu tile, tile không bấm được hoặc crash sau khi chọn. |
| Protected fan chart | Icon download biến mất, chart bắt đầu và vẫn bắt đầu được sau restart. | Icon tồn tại vĩnh viễn, download error, AKFC/JNI error hoặc chỉ chạy được lần đầu. |

Pass một dòng phía sau không xóa fail ở dòng trước. Giữ APK ở trạng thái candidate cho
tới khi mọi dòng bắt buộc đều pass trên cùng một signed build.

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
