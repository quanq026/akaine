# V34: kết quả rebase trên nền prod 22/10

Bản staging V34 đã được dựng từ APK prod V9 gốc, ký bằng chứng chỉ hiện có và
kiểm trên emu 40G. Bản build nguồn là commit `abca317`.

- Dựng lại đủ năm payload từ source; không dùng SO/DEX staging cuối làm đầu vào.
- 5.413 member ngoài payload và 4.996 asset APK giữ nguyên nội dung của prod.
- Account Management, Logout, đăng nhập QA và Cloud Sync Download đã đạt.
- Tempest dùng đúng gauge 6 trong gameplay.
- Chọn nhân vật, tìm bài, Replay Off, Pause/Resume/Retry/Quit đã đạt.
- Lượt thu playback dùng giới hạn 20 giây; WAV thực tế dài 19,264 giây.
- Restart vẫn đăng nhập, giữ bundle staging `.20` và không tải bundle lại.
- Kiểm độc lập source/profile/runtime đều không phát hiện lỗi trong phạm vi này.

APK: `AkaineXD-7.0.255-staging-prod22-rebase-v34-20261025.apk`

SHA-256: `2f4705230db06034d520b57ca0836bba424cbd7f9a6c6c79e42d92be06c23b4c`

Xem [receipt và giới hạn kiểm tra](RELEASE_V34.json),
[bảng thay đổi](ACCEPTED_CHANGES.md) và [cách build](BUILD.md).

Đây là bản staging đã kiểm các luồng nêu trên. Chưa phát hành production;
chưa xác minh toàn bộ thư viện/nhân vật, lưu điểm, FPS dài hạn hoặc âm thanh máy
thật. Bundle staging `.20` hiện có vẫn giữ tài nguyên đã nén mất chất lượng;
bản khôi phục ảnh/preview gốc vẫn offline. Rebase APK không được tính là đã sửa
xong phần tài nguyên hoặc tiếng ồm/vang được báo trên máy thật.

Đã bổ sung [năm lượt đo FPS/CPU/bộ nhớ và menu trên emu](../performance/20261025-v34-emulator.md).
Các số đo ngắn này không thay thế kiểm FPS dài hạn hoặc máy thật.
