# Prod 22/10 + Aurora, nguyên chất lượng

Yêu cầu đã chốt ngày 25/10/2026: dùng bundle prod 22/10 (`7.0.255.18`) làm nền,
thêm thư viện Aurora và **giữ Download từng bài như prod**. Không giới hạn 2GB,
không resize/recompress ảnh, không chuyển mã nhạc giảm chất lượng, không bỏ file
trùng APK và không phát hành delta.

## Phạm vi nội dung

- Nền prod có 1.011 bài và 12.947 logical path.
- Giữ nguyên byte 12.946 path; chỉ thay `songs/songlist` để nối thêm Aurora.
- Thêm 1.532 bài đã có audio/chart được chấp nhận: 4.820 chart thật.
- Thêm 7.956 path: 6.404 alias ảnh gốc, 1.532 preview gốc, 17 preview PCM float
  lossless cho trường hợp thiếu preview nguồn và 3 WAV tài nguyên đi kèm.
- Tổng catalog 2.543 bài, 63 pack; Aurora dùng `xd_fan_album` hiện có.
- Không lấy sidebar/layout staging hoặc bảy file riêng của staging17 vào base.

Raw export 15.593 file đã kiểm hash và tập file đầy đủ. Tuy nhiên, 829 source ID
chưa có nội dung được chấp nhận và không trùng ID prod. Không tạo bài giả hay
coi các ID đó là đã nhập xong; trùng ID cũng không chứng minh trùng tác phẩm nhạc.

## Cách ghép

`scripts/build_prod_aurora_bundle.py` nhận recipe local đã được review, chứa
manifest prod18 và bảy phần nguồn, một overlay songlist, danh sách file Aurora
nguyên bản và hash/kích thước. Tool kiểm toàn bộ nguồn, chia lại các phần liên tục
không quá 480MiB rồi kiểm mọi span đầu ra. `previousVersionNumber=null`,
`removed=[]`; đây là một base độc lập.

Songlist mới khớp chính xác byte của catalog Aurora đã có. Chỉ cặp byte và digest
xác thực có sẵn được giữ lại; không đọc hoặc ghi key HMAC. Packlist/unlocks giữ
nguyên byte và digest của prod18.

Recipe và đường dẫn file gốc thuộc private kit ngoài Git. Từ repository root,
với QA Python và recipe đã gắn review:

```powershell
python -c "import json,pathlib,sys;sys.path.insert(0,'scripts');import build_prod_aurora_bundle as b;b.build(json.loads(pathlib.Path(r'<private-recipe.json>').read_bytes()),pathlib.Path(r'D:/AkaineBuilds/<fresh-output>'))"
```

## Tải riêng audio/chart

Ledger candidate giữ 6.434 object cho 1.532 bài, tổng 7.384.847.914 byte: 1.532
audio, 4.860 chart mã hóa (4.820 thật và 40 shim ẩn), 42 tài nguyên bổ sung.
Chart mã hóa giữ nguyên. Đúng 50 audio dẫn xuất được thay bằng byte gốc: 48 MP3
và 2 Ogg trước remux; danh sách/tên file per-song không đổi, cập nhật đúng 50 MD5.

Ledger/metadata chỉ mới chuẩn bị offline và định tuyến vào namespace candidate
mới. Chưa upload hoặc thay metadata, Worker, R2 hay file đang chạy.

## Kích thước candidate offline

Phần payload 4.532.838.207 byte, chia 10 phần không quá 480MiB. Sau khi build
và kiểm hash hoàn tất, receipt riêng ghi manifest và hash từng phần. Kích thước
này không gồm 7,38GB audio/chart tải riêng theo từng bài.

## Trạng thái kiểm native trước khi online

Công cụ có thể dựng bản offline và kiểm byte trước khi kiểm native. Trước khi
kích hoạt còn phải chứng minh 17 preview WAV PCM float, 48 MP3 gốc dưới tên file
hiện có, hai Ogg trước remux và tổng `bundleSize` vượt 4GiB hoạt động đúng.
Static inspection thấy đường audio không ép codec Ogg và có các decoder liên
quan, nhưng không được tính là bằng chứng playback native.

Không hạ chất lượng để né kiểm tương thích. Chưa dùng bản offline để thay bundle
production hoặc chốt đã sửa tiếng ồm/vang trên máy thật.

## Build offline đã hoàn tất

Bản `7.0.255.25`, alias `7.0.255-staging-prod18-aurora-original-base25-20261026`,
đã build và kiểm source/output hash ngày 26/10/2026: 20.903 file, 10 phần, tổng
**4.538.288.896 byte** gồm manifest. Đây là base độc lập, không delta.

[Receipt nhẹ, hash từng phần và trạng thái kích hoạt](prod18-aurora-original25.json).
Media và private recipe không được đưa vào Git.

**Chưa upload hoặc kích hoạt.** Các phép kiểm native về codec và tổng dung lượng
còn ở phía trước; bản này không được tính là đã qua kiểm gameplay/download trên
client. Bundle staging/prod đang chạy không bị thay đổi trong lượt build này.

Đã kiểm độc lập lại toàn bộ 4.532.838.207 byte: 20.903 span và hash cả 10 phần
đều đạt; 12.946 file prod cũ giữ nguyên. Kết quả này xác nhận byte của bản
offline, chưa thay thế kiểm native/API trước khi kích hoạt.

## Mốc triển khai tiếp theo ngày 26/10/2026

Base25 sau đó đã được upload và kích hoạt riêng staging, cùng audio gốc và
metadata tương ứng. Xem [receipt online và trạng thái kiểm native](prod18-aurora-original25-online.md).
Các đoạn "chưa upload" ở trên mô tả mốc build offline trước triển khai này.
