# Kinh nghiệm và lỗi đã gặp khi xây dựng Akaine 7.0.255

[English](../08-lessons-and-failures.md) | Tiếng Việt

Chương này ghi lại các vấn đề đã gặp khi xây dựng và vận hành client, content bundle và
server 7.0.255. Mục đích là giúp bạn không lặp lại cùng một cách chẩn đoán sai. Nó không
thay thế quy trình build và release trong chương 6 và 7.

Những sai lầm tốn thời gian nhất thường đến từ việc sửa nhầm tầng. Akaine có Android
wrapper, native game code, content bundle, kho bài remote, server metadata, account data
và nhiều lớp cache. Một tầng pass không chứng minh tầng tiếp theo cũng đúng.

## Dùng đúng mức bằng chứng

Hãy dùng mô tả hẹp và chính xác nhất khi báo cáo kết quả:

| Mức | Điều nó chứng minh |
| --- | --- |
| Static verified | File, hash, package metadata hoặc cấu trúc manifest đúng mà chưa chạy client. |
| Server verified | Đã quan sát đúng API response và trạng thái phía server. |
| Client verified | Client thật hoàn thành hành động được gọi tên mà không crash hoặc nhận response bất thường. |
| Gameplay verified | Chart đã vào gameplay đủ lâu để thực sự dùng chart và audio. |
| Restart verified | Cùng trạng thái vẫn hoạt động sau khi tắt hẳn và mở lại app. |

"File tồn tại", "service active" và "đã vào title screen" đều là thông tin hữu ích.
Không điều nào trong số đó tự nó là kết quả release hoàn chỉnh.

## Bắt đầu từ triệu chứng rồi cô lập tầng lỗi

| Triệu chứng | Tầng kiểm tra đầu tiên | Bằng chứng cần lấy trước khi sửa |
| --- | --- | --- |
| APK không cài được | package identity, alignment và signer | lỗi adb install, `aapt` badging, kết quả zipalign và apksigner |
| Login được nhưng Cloud Sync làm logout | native request routing | client log, server request log và route của direct API call |
| Bundle báo `-1013` | bundle manifest và partition byte | manifest, tên part, offset, length, hash và Range response |
| Bundle tới 100% rồi boot-loop | catalogue reference hoặc startup resource | log cold start đầu tiên cùng `songlist`/`packlist` cuối |
| Bài bị đen dù có tồn tại | selector asset hoặc native reveal state | hash jacket/preview và so sánh với một bài control tốt |
| BYD hiện nhưng không chọn được | native class-3 registry state | song ID chính xác, difficulty class và hành vi/log selector |
| Icon download còn mãi | DownloadList contract | request của client, `song_metadata.json`, allowlist và object CDN thật |
| Bài crash lúc bắt đầu chơi | chart/audio/AKFC runtime | dòng fatal hoặc FMOD trong logcat, độ khó được chọn và file đã cấp |
| Score lưu nhưng PTT không đổi | chart constant và rating eligibility | chart row, best-score rating và khả năng vào B30/recent |

Ghi thời gian chính xác và ngừng thao tác sau khi crash. Mở app liên tục có thể đẩy phần
logcat hữu ích ra khỏi buffer.

## Bài học client: một hostname không phải toàn bộ routing

Một bản client build lại từ source có thể đăng nhập, nhưng Cloud Sync trả lỗi `-4` và
tài khoản trông như bị logout sau restart. Ban đầu DB server, login token và DNS bị nghi
ngờ vì triệu chứng giống lỗi xác thực.

Client thực tế có hai cơ chế routing. Chuỗi nhìn thấy được xử lý login, aggregate và
content-bundle request. Direct endpoint như request save data dùng một shared API base
được mã hóa riêng. Chỉ patch URL nhìn thấy tạo ra client trông như đã kết nối cho tới
khi nó dùng một direct route.

Fix được thêm vào guarded native plan, rồi được xác minh bằng đủ chuỗi: login, Cloud
Sync download, force-stop, mở lại, xác nhận tài khoản vẫn đăng nhập, rồi Cloud Sync lần
nữa.

Quy tắc giữ lại là phải lần theo đúng request bị lỗi. Login thành công không chứng minh
mọi nhóm API dùng chung host.

## Bài học client: bisection thắng một giả thuyết rất thuyết phục

AKFC loader ban đầu có nguy cơ đóng gói một `libcrypto.so` cho toàn process. Nó có thể
ảnh hưởng native code không liên quan, nên public build chuyển sang BoringSSL static có
prefix `akfc_` cho symbol.

Khi lỗi logout vẫn còn, rất dễ tiếp tục đổ lỗi cho loader, DEX rebuild hoặc crypto.
Các candidate sau đó được build với mỗi lần chỉ đổi một thành phần. Client dùng public
static loader và không có process-wide crypto vẫn sync được khi ghép với native game
library đã biết là tốt. Thay library đó làm lỗi tái hiện và dẫn tới shared API base bị
thiếu.

Đây là lý do chương 6 giữ receipt của từng APK member. Hãy so sánh entry trong archive
và mỗi candidate chỉ đổi một biến. Nhiều thay đổi cùng lúc có thể tạo build chạy được
nhưng không cho biết thay đổi nào thật sự cần thiết.

## Bài học client: install-over phụ thuộc signer

Package name và version code chưa đủ để Android cập nhật app. APK ký bằng certificate
khác không thể thay package đang cài. Uninstall để "sửa" lỗi này sẽ xóa application data
local.

Giữ một signing identity cho package, ghi certificate SHA-256 và sao lưu keystore. Nếu
không biết signer hiện tại, hãy dừng và quyết định rõ local data có thể mất hay không.
Không tự động uninstall như fallback khi install lỗi.

## Bài học bundle: checking 100% vẫn có thể tạo boot loop vĩnh viễn

Một bundle từng tải và check tới 100%, sau đó crash trước start screen ở mọi lần mở.
Byte và quá trình truyền đều hợp lệ. Một pack đã bị xóa trong khi song và child pack vẫn
tham chiếu tới nó.

Client chấp nhận archive rồi lỗi muộn hơn khi resolve quan hệ catalogue. Vì vậy builder
7.0.255 hiện từ chối `song.set` không phải `single` hoặc ID của pack hiện có, đồng thời
từ chối `pack_parent` không có parent tương ứng.

Không sửa selector bằng cách xóa pack entry cho tới khi màn hình trông sạch. Pack, child
pack và mọi member song phải được thay đổi như một operation catalogue thống nhất.

## Bài học bundle: full root an toàn hơn delta chưa được kiểm chứng

Một số candidate cũ dùng layout một part hoặc delta vì tạo nhanh hơn. Client từ chối
những layout trông hợp lý khi kiểm tra tĩnh bằng `-1013` hoặc tải update lặp lại.

Đường ổn định cho 7.0.255 bắt đầu từ full root đã biết là tốt với
`previousVersionNumber: null`, giữ partition contract của source, tính lại hash của mọi
span và phát hành alias mới. Local pass chưa đủ; manifest cùng mọi part còn phải khớp
sau khi tải đầy đủ qua CDN.

Không ghi byte mới đè lên alias đã bị cache. Content version mới cần object name mới,
kể cả khi release trước bị lỗi.

## Bài học bundle: màn hình 100% có thể vẫn đang xử lý

Bundle lớn có thể nằm ở màn hình checking 100% trong khi client chuyển dữ liệu khỏi
temporary storage và extract. Bấm confirm lần nữa, force-stop hoặc restart emulator ở
giai đoạn đó có thể tạo một lỗi khác.

Theo dõi file growth và log trong một khoảng thời gian có giới hạn. Nếu temporary
bundle data vẫn thay đổi và không có fatal line, hãy chờ. "Phần trăm đứng yên" không
đồng nghĩa "process đã chết".

## Bài học selector: asset hợp lệ không bảo đảm preview xuất hiện

Một số bài Divine/Konzetsu có jacket và `preview.ogg` hợp lệ nhưng selector vẫn đen hoặc
im lặng. Thay asset và đổi server unlock không xử lý được hành vi. So sánh với control
song cho thấy native pre-challenge reveal state đã suppress selector trước khi FMOD
tham gia.

Release fix chỉ thay đổi native state path đã xác minh của 7.0.255. Bundle asset vẫn
bắt buộc, nhưng không phải nguyên nhân gốc trong sự cố đó.

Luôn so sánh một bài lỗi với một bài tốt. Nếu cả hai request cùng loại asset hợp lệ
nhưng khác nhau trước playback, hãy kiểm tra client state gate trước khi build lại CDN
content.

## Bài học selector: entitlement không làm BYD tự bấm được

Server có thể cấp bài và bundle có class-3 chart, trong khi BYD tile vẫn không hiện hoặc
hiện nhưng không bấm được. Các bài Final Verdict và Axium Crisis cho thấy khác biệt này.

Tầng còn thiếu là active-state registry của client cho một số class-3 song ID cụ thể.
Guarded allowlist chỉ sửa những ID đã xác minh; nó không tự cấp mọi BYD chart lạ.

Hãy test difficulty tab thật. Thấy bài ở FTR không chứng minh BYD tồn tại. Thấy BYD tile
cũng không chứng minh bấm vào sẽ tới gameplay.

## Bài học gameplay: FMOD error 18 không chỉ có một nguyên nhân

FMOD error 18 từng bị coi là bằng chứng `base.ogg` bị thiếu. Trong thực tế nó cũng có
thể xuất hiện khi file-read contract sai hoặc chart request một effect file không resolve
được. Nếu cùng OGG chạy được với control chart, audio container khó có thể là vấn đề duy
nhất.

Kiểm tra log để biết chính xác filename FMOD đã cố mở. Kiểm tra AFF arc-effect token,
difficulty-specific audio path và native read result. Không thay đi thay lại một OGG
hợp lệ khi chưa có bằng chứng decode file đó lỗi.

## Bài học gameplay: special chart cần state null-safe

Aether Crest ETR có thể crash vì special-condition list không tồn tại trong khi native
code mặc định rằng nó có. Asset, entitlement và chart delivery đều có thể đúng trước
lần dereference này.

Patch được chấp nhận thêm null guard và giữ nguyên đường non-null bình thường. Cách này
an toàn hơn ép global "unlocked" ở renderer branch phía sau. Với chart đặc biệt, hãy tìm
shared state check sớm nhất bị lỗi.

## Bài học download: bốn inventory phải khớp nhau

Một remote song được mô tả bởi nhiều inventory:

1. `songlist` trong bundle, gồm `remote_dl` và `additional_files`;
2. `song_metadata.json` trên server;
3. allowlist cho protected file;
4. public và protected object thực tế trên R2/CDN.

Nếu bundle yêu cầu thêm video hoặc WAV mà metadata không khai báo, hoặc metadata khai
báo file mà storage không trả được, client có thể giữ icon download dù OGG chính và
chart đều hợp lệ.

Hãy coi `additional_files` là tập con của metadata file list. Xác minh response, byte
count và checksum thật cho mọi object được request. Một file trả `200` không chứng minh
toàn bộ download set của bài đã đủ.

Difficulty-specific preview tách biệt với playable audio. Khi `audioOverride` bật,
selector có thể cần `<ratingClass>_preview.ogg` dù downloadable `<ratingClass>.ogg` tồn
tại ở nơi khác.

## Bài học emulator: process chết không phải lúc nào cũng là app crash

Trong lúc cài bundle lớn, emulator thiếu RAM bị treo và low-memory killer của Android
đã dừng game. Không có native fatal, JNI error hoặc linker failure. Chỉ nhìn màn hình
thì sự kiện giống hệt crash sau download.

Kiểm tra logcat cho `SIGABRT`, `FATAL EXCEPTION`, tombstone và process-exit reason. LMKD
kill, ANR toàn hệ thống và emulator stall thuộc về test environment cho tới khi tái hiện
được bằng bằng chứng app-level crash. Tăng RAM emulator đã giúp cùng data và APK hoàn
thành bootstrap.

Điều này không có nghĩa mọi crash đều do emulator. Nguyên nhân phải đến từ log, không
phải từ thời điểm cửa sổ biến mất.

## Bài học CDN: Range và cache HIT không chứng minh throughput

Range request nhỏ có thể trả `206`, đúng `Content-Range` và `CF-Cache-Status: HIT` trong
khi client tải file lớn vẫn chậm hoặc timeout. Trong một lần điều tra, cloud host độc
lập tải nhanh còn kết nối Windows thi thoảng tụt mạnh.

Xác minh byte trước, sau đó đo full hoặc concurrent download từ mạng thứ hai trước khi
đổi R2 hay cache rule. Cache semantic đúng chứng minh route và byte, không chứng minh
tốc độ kéo dài của một client connection.

## Bài học server: active chưa có nghĩa ready

Sau khi restart service, `systemctl` có thể báo `active` trước khi local HTTP port bind
xong. Nginx trả `502` trong thời gian ngắn. Restart thêm chỉ làm quan sát nhiễu hơn.

Dùng readiness loop có timeout trên API route dự kiến. Chỉ promote hoặc rollback sau
khi route thành công hoặc hết timeout. Process state là một signal; HTTP contract mới
là release gate.

Content-bundle API cũng phải không bị cache. Static bundle object phù hợp với cache dài,
nhưng response `/game/content_bundle` bị cache có thể làm client hiện tại tải lại content
cũ.

## Bài học data: compatibility phải nằm ở boundary

Một số client cũ dùng compatibility song ID trong khi 7.0 dùng canonical ID. Đổi stored
score theo client đang test sẽ chia đôi lịch sử người chơi. Thiết kế an toàn hơn giữ một
storage identity canonical và chỉ translate khi serialize cho legacy client.

Nguyên tắc tương tự áp dụng cho progression field 7.0. Hãy mở rộng account data cũ mà
không bỏ score, purchase hoặc cloud save. Xác minh cả account đã tồn tại và account mới;
chỉ test admin account có thể che migration gap.

Score được lưu không tự chứng minh PTT đúng. Chart constant, best-score rating và khả
năng vào B30/recent đều tham gia kết quả đó.

## Bài học release: staging phải chứng minh route và feature

Staging API khỏe không chứng minh client đã cài đang dùng nó. Trước khi chấp nhận staging
test, hãy đối chiếu request mới của client với staging server log và xác minh content
version trả về. Nếu không, client có thể âm thầm test production trong khi mọi người tin
rằng staging đã pass.

Promote đúng bộ byte đã test trên staging. Build lại giữa staging và production tạo ra
artifact mới, kể cả khi source không cố ý thay đổi. Giữ APK, bundle manifest, server
configuration và database backup cũ cho tới khi cold install, restart và download bình
thường đều pass.

Khi request trả `429`, chờ hết retry window rồi tiếp tục đúng bước đó. Build lại, đổi
tên hoặc clear data không sửa rate limiting và còn phá mất bằng chứng hữu ích.

## Các quy tắc được giữ lại sau những sự cố này

- Mỗi lần chỉ đổi một tầng và giữ receipt của nó.
- So sánh case lỗi với một control đã biết là tốt.
- Giữ log hữu ích đầu tiên trước khi mở lại hoặc retry.
- Dùng tên bất biến mới cho release object.
- Coi download, gameplay và restart là các gate riêng.
- Không uninstall, clear player data hoặc sửa production như đường tắt chẩn đoán.
- Giữ staging cô lập và chứng minh client đã đi tới endpoint nào.
- Chỉ gọi kết quả release-ready khi client thật pass đúng hành động được gọi tên.

Các quy tắc này nghiêm hơn "đã chạy được một lần" vì phần lớn lỗi tốn thời gian của dự
án đều từng chạy được một lần, pass một tầng hoặc trông đúng khi quan sát từ nhầm phía
của hệ thống.
