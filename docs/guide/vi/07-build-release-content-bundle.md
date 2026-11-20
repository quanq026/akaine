# Phát hành bundle 7.3.1 đã chuẩn bị

[English](../07-build-release-content-bundle.md) | Tiếng Việt

1. Lấy một bộ bundle đầy đủ cho 7.3.1 gồm manifest JSON và tất cả file `.cb`. Kiểm manifest có `applicationVersionNumber` là `7.3.1`, `previousVersionNumber` là `null` và có thẻ xác thực cho songlist, packlist và unlocks.
2. Tải các phần lên [R2](05-cloudflare-content.md) theo đúng tên. Mỗi bản phát hành dùng tiền tố riêng để có thể quay lại bản trước.
3. Dùng [chương server](05a-install-game-server.md) để cài manifest, đặt SHA-256 và URL R2. Kiểm bằng request tải bundle của client mới, rồi kiểm lại với client đã có phiên bản đích.

Repo hiện hướng dẫn xuất bản bundle đã chuẩn bị. Công cụ đóng bundle 7.3.1 từ asset thô chưa có trong quy trình public.
