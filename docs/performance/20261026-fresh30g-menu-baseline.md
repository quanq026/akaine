# Emu 30G: gameplay và vấn đề menu/loading

Đây là baseline V34 + bundle nguyên chất lượng `.25` trên emu mới30G. Chưa có
bản sửa hiệu năng từ những số đo này.

| Cửa sổ | FPS trung bình | 1% low |
| --- | ---: | ---: |
| Gameplay HighFPS | 114,97 | 50,57 |
| Gameplay khóa60 | 60,00 | 36,64 |
| Song Select All đứng yên | 28,86 | 21,58 |
| Main Menu đứng yên | 100,45 | 45,98 |
| Song Select lọc Daybreak | 79,98 | 49,25 |

Cùng DaybreakFTR/Hikari0/ReplayOff/speed1/offset0/SFX0, emu API35 dịchARM64,
4core/RAM4GiB/720p120Hz. Không có CLI/screenshot/audio recorder trong các cửa sổ
idle. Cửa sổ45s có9 lệnh native đi qua MainMenu, SongSelect, PackSelect và loading;
khoảng trình bày dài nhất2.776,22ms. Không dùng FPS gameplay để chốt menu mượt.

Một diagnostic QA tạm đã đo geometry prepass0,879ms/lần trênAllSongs (2,72%thời
gian) và0,033ms khi lọc. Interval Java yêu cầu8.333.333ns. Đường geometry có tồn
tại nhưng chưa giải thích được cả frame~34ms; không áp dụng cache/culling khi
chưa chứng minh đúng chi phí và ảnh hưởng layout/input. Visual pool sẵn có đã
được tính đến. Diagnostic có giới hạn unwind, được giữ riêng và đã khôi phục
APK thường sau đo; không đưa lên máy thật hay coi là release.

Source đang bổ sung `guide status`/`guide next`: mỗi lần chỉ tiến một bước native,
đọc step/readiness và giữ guard. Test146ca (một native fixture skip trênWindows,
đạt riêng quaWSL);8lệnh guide-next thực tế qua Welcome/Settings/MainMenu đạt.
Trường hợp PackHint+LevelWarning vẫn cần bằng chứng và xử lý riêng, chưa gọi đã sửa.

Xem [receipt và giới hạn](20261026-fresh30g-menu-baseline.json). Source này thuộc
nhánh công việc, chưa cập nhật profile/hashcontrol hoặc chốt candidateV35.
