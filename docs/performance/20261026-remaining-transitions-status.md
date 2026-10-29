# Trạng thái tối ưu ba đoạn menu/loading — 26/10/2026

## Kết quả hiện tại

Đã hoàn tất đo riêng ba luồng trên V36 và một lượt chia nhỏ vùng tốn thời gian
của mỗi luồng. **Chưa có patch client mới được chấp nhận cho ba đoạn này.**
V36 cùng bản sửa news10 vẫn là APK bình thường được giữ lại.

| Luồng | Số đo chính | Kết luận được chứng minh |
| --- | --- | --- |
| Vào Song Select | Khởi tạo khoảng 1,93–2,38 s; hai khối UI/trạng thái cuối chiếm khoảng 66% trong lượt đo sâu warm | Dọn texture chỉ 2–3 ms; dựng danh sách bài riêng khoảng 190 ms, không phải phần lớn nhất |
| Mở Pack Select | Lần tạo đầu khoảng 1,92 s; mở lại cùng scene 51–52 ms | Layer đã được tái sử dụng; cập nhật mỗi lần mở chỉ 32–54 ms |
| Tạo PackListLayer | Warm 1,30–1,33 s; điền catalog/UI 944–960 ms, sidebar/scheduling 334–348 ms | Population chiếm khoảng 72%; sidebar khoảng 26% và gồm cả xử lý native gốc |
| Loading gameplay | GameScene warm khoảng 1,57–1,67 s; Background/Track 495–507 ms, UI 298–347 ms, phần cuối 448–450 ms | Chi phí phân tán ở nhiều bước dựng scene; purge 1–2 ms, GameModel 7–9 ms |

Đây là số đo native wall/CPU và presentation gap riêng, không phải tổng thời gian
CLI hay FPS trung bình của một cửa sổ trộn nhiều scene. Mỗi probe có ba root hợp
lệ, cùng GL owner, thứ tự điểm đầy đủ và không hết quota. Các lượt cuối có emu
thử bundle riêng được pause hoặc tắt; source/audio/chart và cấu hình ASG giữ nguyên.

## Quyết định theo ngưỡng chi phí trong kế hoạch

Không có thao tác trùng hay đối tượng có thể tái sử dụng an toàn được chứng minh
đủ để kỳ vọng một patch nhỏ giảm ít nhất 30% đoạn khựng. Phần lớn chi phí là dựng
UI mới; biết tên một khối tốn thời gian không chứng minh khối đó có thể bỏ đi.

- Song Select: không bỏ các lần cập nhật state/list/delegate chỉ vì cùng gọi một
  hàm; các nhánh có thể dùng pack và input khác nhau. Dừng thêm probe theo budget
  coarse + một partition của kế hoạch.
- Pack Select: không thêm cache layer thứ hai hoặc bỏ cập nhật vốn nhẹ. Cần thiết
  kế cách dựng nội dung nhìn thấy/tái sử dụng presenter nếu population thực sự
  có công việc dư; vẫn phải giữ mọi pack, category và khả năng thêm pack sau này.
  Static review đã chốt: chưa chứng minh một phần có thể bỏ an toàn. Hoãn patch
  theo ngưỡng chi phí đã thống nhất.
- Gameplay: không có bằng chứng chart/audio gây phần lớn chi phí. Một worker hoặc
  preload toàn hệ thống sẽ là phạm vi lớn hơn, có rủi ro owner thread, hủy tác vụ,
  readiness, memory và audio clock; chưa triển khai.

Các hướng trên được để lại để quyết định mức đầu tư tiếp theo. Không công bố
phần trăm cải thiện mới cho ba đoạn; chúng vẫn còn lag.

## Trạng thái máy và rollback

Tất cả APK chẩn đoán NoFDE chỉ được dùng trên emulator-5556 và đã được tháo.
Normal V36 được cài lại, mapped core `ce5210…` và monitor `ee84fc…` khớp chính xác;
ASG vẫn bật. Không cài probe lên máy thật, không thay production. Các APK tạm trên
`W:/Not at home/Akaine-QA-tmp-20261026` đã được kiểm hash rồi xóa; còn 0 byte APK
trong thư mục tạm này. Build, source, receipts và log gốc giữ trên D/workspace.

## Bundle staging song song

Staging đã chuyển từ lite `.20` sang base nguyên chất lượng `.25`: 10 phần,
4.538.288.896 byte, 20.903 logical file, 2.543 bài/63 pack. Native downloader trên
emu riêng đã tải qua mạng, apply và restart giữ nguyên, không tải lại. Không dùng
ADB để inject bundle ở lượt kiểm này. Production không đổi.

Xem [báo cáo online và rollback](../bundles/prod18-aurora-original25-online.md).
Native Download/gameplay từng bài chưa kiểm trong task bundle: người dùng đã chọn
dừng ở kiểm bundle và không đồng ý điều khoản tài khoản QA. Metadata/body hash
mạng không thay thế kiểm native playback.

## Bằng chứng

- `20261026-remaining-transitions-baseline.json`
- `20261026-songselect-phase-attribution.json`
- `20261026-songselect-middle-attribution.json`
- `20261026-songselect-late-targets.json`
- `20261026-packopen-phase-attribution.json`
- `20261026-packopen-middle-attribution.json`
- `20261026-gameload-phase-attribution.json`
- `20261026-gameload-middle-attribution.json`
