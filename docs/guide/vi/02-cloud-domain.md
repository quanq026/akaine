# Tạo cloud server và kết nối tên miền

[English](../02-cloud-domain.md) | Tiếng Việt

Chương này tạo các tài khoản cloud, khởi động Linux server và nối server với tên miền
của bạn. Khi hoàn tất, server có một public IP cố định và `api.your-domain` phân giải
qua Cloudflare.

## Thời gian và chi phí

Lên kế hoạch từ 45 đến 90 phút, cộng với thời gian chờ xác minh tài khoản.

Nếu tài khoản AWS mới của bạn có Free plan, hãy chọn nó khi đăng ký. AWS hiện cấp 100
USD credit ban đầu và cho phép nhận thêm tối đa 100 USD. Free plan kéo dài tối đa sáu
tháng hoặc tới khi credit hết. Lightsail plan dùng trong hướng dẫn có giá niêm yết 12
USD/tháng, nên credit có thể chi trả giai đoạn làm quen ban đầu.

Công dân Việt Nam từ 18 đến 23 tuổi có thể đăng ký miễn phí một tên miền `.id.vn` trong
hai năm. iNET là một trong những nhà đăng ký `.vn` tham gia và xác minh tính đủ điều
kiện với eKYC. Nếu bạn không đủ điều kiện, iNET và các nhà đăng ký khác thường đưa ra
khuyến mại tên miền giá rẻ bắt đầu từ khoảng 40.000 đồng; luôn kiểm tra cả năm đầu tiên
và giá gia hạn trước khi mua.

Cloudflare DNS, CDN và SSL đều miễn phí. R2 Standard bao gồm 10 GB dung lượng lưu trữ
mỗi tháng, một triệu thao tác ghi và mười triệu thao tác đọc mỗi tháng. Dung lượng bổ
sung là 0,015 USD mỗi GB-tháng và đường ra Internet từ R2 là miễn phí. Việc triển khai
Akaine nhỏ thường sẽ ở mức dưới 1 USD/tháng cho R2.

Sau sáu tháng, bạn có thể nâng cấp AWS lên mức sử dụng trả phí, chuyển sang nhà cung cấp
VPS khác hoặc tắt server. Xuất server và cơ sở dữ liệu của bạn trước khi gói AWS miễn
phí hết hạn; tài khoản gói miễn phí đã hết hạn có thể không thể truy cập được.

## Bạn cần

- địa chỉ email bạn kiểm soát;
- số điện thoại để xác minh tài khoản;
- thẻ thanh toán được AWS và nhà đăng ký của bạn chấp nhận;
- trình quản lý mật khẩu;
- tài khoản AWS đủ điều kiện nhận tín dụng hoặc phương thức thanh toán để sử dụng có trả
  phí sau này.

## Cách làm theo chương này

Bước 1 đến 8 và bước 10 được thực hiện trong trình duyệt. Bước 9 và 11 được thực hiện
trong Windows PowerShell. Hãy giữ một ghi chú setup riêng trong password manager chỉ
với các giá trị không bí mật sau:

```text
MY_DOMAIN=
SERVER_IP=
LIGHTSAIL_REGION=
LIGHTSAIL_INSTANCE=akaine-server
```

Không đặt password, recovery code, SSH private key hoặc AWS credential vào ghi chú đó.
Hoàn thành từng bước đánh số trước khi chuyển bước. Trang còn ghi `Pending`, `Creating`
hoặc `Verifying` chưa vượt qua gate.

## Bước 1: tạo và bảo mật tài khoản Cloudflare

1. Mở `dash.cloudflare.com` trong trình duyệt của bạn.
2. Chọn **Đăng ký**.
3. Nhập địa chỉ email của dự án và một mật khẩu duy nhất.
4. Xác minh email Cloudflare gửi cho bạn.
5. Trong bảng điều khiển, hãy mở menu hồ sơ của bạn, sau đó **Hồ sơ của tôi** → **Xác
   thực**.
6. Kích hoạt xác thực hai yếu tố. Ứng dụng xác thực sẽ thích hợp hơn SMS.
7. Lưu mã khôi phục trong trình quản lý mật khẩu của bạn hoặc bản sao lưu ngoại route.

Không tiếp tục cho đến khi bạn có thể đăng xuất và đăng nhập lại bằng xác thực hai yếu
tố.

## Bước 2: đăng ký tên miền

### `.id.vn` miễn phí thông qua iNET

Sử dụng tùy chọn này nếu bạn là công dân Việt Nam từ 18 đến 23 tuổi và chưa nhận ưu đãi
`.id.vn` miễn phí.

1. Mở iNET OnePortal và chọn dịch vụ đăng ký `.id.vn` miễn phí.
2. Đăng nhập hoặc tạo tài khoản iNET.
3. Hoàn tất eKYC bằng tài liệu nhận dạng và xác minh khuôn mặt của riêng bạn.
4. Tìm kiếm tên `.id.vn` mà bạn muốn.
5. Hoàn thành việc khai báo chủ sở hữu và nộp hồ sơ đăng ký.
6. Đợi trạng thái tên miền hoạt động trong iNET.

Mỗi người đủ điều kiện có thể nhận được một `.id.vn` miễn phí, vì vậy hãy chọn tên cẩn
thận. Chương trình hiện tại bao gồm tên miền trong hai năm. Trước khi khoảng thời gian
đó kết thúc, hãy kiểm tra các điều khoản gia hạn hoặc chuẩn bị chuyển sang miền khác.

### Tên miền trả phí

Nếu bạn không đủ điều kiện, hãy mua miền phù hợp ít tốn kém nhất từ ​​iNET hoặc nhà đăng
ký khác. Giá khuyến mãi có thể trên dưới 40.000đ nhưng giá gia hạn có thể khác nhau.
Tránh chọn miền chỉ vì năm đầu tiên giá rẻ.

Viết tên miền thực của bạn vào đây trước khi tiếp tục:

```text
MY_DOMAIN=____________________________
```

Lưu domain đã chọn vào ghi chú setup riêng. Các chương sau dùng `your-domain` và
`example.com` làm placeholder; không chuỗi nào trong số đó được xuất hiện trong DNS
record hoặc APK thật.

## Bước 3: kết nối tên miền với Cloudflare

1. Trong bảng điều khiển Cloudflare, hãy mở **Trang web** và chọn **Thêm miền**.
2. Nhập tên miền bạn đã đăng ký và chọn gói miễn phí.
3. Cloudflare quét các bản ghi DNS hiện có. Tiếp tục đến trang server tên.
4. Cloudflare hiển thị hai server tên được chỉ định. Giữ trang này mở.
5. Trong iNET hoặc trang quản lý tên miền của nhà đăng ký của bạn, hãy thay thế server
   tên hiện có bằng hai server tên Cloudflare.
6. Quay lại Cloudflare và chọn **Kiểm tra server tên ngay**.

Nếu DNSSEC đã được bật tại nhà đăng ký, hãy tắt nó trước khi thay đổi server tên. Chỉ
bật lại DNSSEC trong Cloudflare sau khi vùng này hoạt động.

### Kiểm tra thay đổi nameserver

Mở tên miền trong Cloudflare. Trang Tổng quan phải có nội dung **Đang hoạt động** chứ
không phải "Đang chờ cập nhật server tên". Không tạo hồ sơ sản xuất trong khi khu vực
đang chờ xử lý.

## Bước 4: tạo và bảo mật tài khoản AWS

1. Mở `aws.amazon.com` và chọn **Tạo tài khoản AWS**.
2. Hoàn tất xác minh email, thông tin liên hệ, xác minh thanh toán và xác minh điện
   thoại.
3. Chọn gói AWS Free nếu gói này được cung cấp và bạn đang sử dụng thời hạn tín dụng sáu
   tháng. Chỉ chọn gói trả phí nếu bạn cần các dịch vụ không có trong gói miễn phí hoặc
   muốn server tiếp tục sau thời gian miễn phí.
4. Đăng nhập vào Bảng điều khiển quản lý AWS với tư cách là chủ sở hữu tài khoản.
5. Mở menu tài khoản → **Credentials bảo mật**.
6. Kích hoạt MFA cho người dùng root và lưu trữ thông tin khôi phục một cách an toàn.
7. Mở **Quản lý hóa đơn và chi phí** và xác nhận số dư tín dụng cũng như ngày hết hạn.
8. Nếu bạn chọn gói trả phí, hãy mở **Ngân sách** → **Tạo ngân sách** và tạo ngân sách
   hàng tháng 20 USD với thông báo qua email ở mức 50%, 80% và 100%.

Không bao giờ tạo khóa truy cập cho người dùng root AWS. Credentials về quản trị
trình duyệt và tự động hóa sẽ được xử lý riêng.

## Bước 5: tạo server Lightsail

1. Trong thanh tìm kiếm Bảng điều khiển AWS, nhập `Lightsail` và mở nó.
2. Chọn **Tạo phiên bản**.
3. Trong **Vị trí phiên bản**, hãy chọn khu vực gần nhất có nhiều người chơi nhất. Đối
   với khán giả Việt Nam/Đông Nam Á, hãy chọn ** Singapore**.
4. Chọn **Linux/Unix**.
5. Chọn **Chỉ hệ điều hành**, sau đó chọn **Ubuntu 24.04 LTS**.
6. Trong phần instance plan, chọn Linux plan có:
   - public IPv4
   - RAM 2 GB
   - 2 vCPU
   - SSD 60 GB
   - giá 12 USD/tháng tại thời điểm viết hướng dẫn
7. Nhập `akaine-server` làm version name.
8. Chọn **Tạo phiên bản**.

Đợi cho đến khi trạng thái phiên bản trở thành **Đang chạy**.

Mở instance một lần và xác nhận blueprint là Ubuntu 24.04 LTS, region đúng với lựa chọn
của bạn. Nếu một trong hai sai, hãy thay instance mới còn rỗng ngay lúc này thay vì sửa
mọi command phía sau cho một image ngoài dự kiến.

## Bước 6: tạo địa chỉ IP cố định

IPv4 công khai mặc định có thể thay đổi sau khi dừng/bắt đầu. DNS phải trỏ đến một địa
chỉ không thay đổi.

1. Trong Lightsail, mở **Mạng** từ menu bên trái.
2. Chọn **Tạo IP tĩnh**.
3. Chọn cùng khu vực Singapore.
4. Gắn nó vào `akaine-server`.
5. Đặt tên là `akaine-server-ip` và chọn **Tạo**.
6. Sao chép địa chỉ IPv4 vào trình quản lý mật khẩu hoặc ghi chú thiết lập của bạn.

```text
SERVER_IP=____________________________
```

Ghi địa chỉ chính xác dưới dạng bốn số thập phân cách nhau bằng dấu chấm. Trang static
IP phải cho thấy nó đã attach vào `akaine-server`; static IP chưa attach không bảo vệ
địa chỉ instance khỏi thay đổi.

## Bước 7: tải xuống khóa SSH của bạn

1. Trong Lightsail, mở **Tài khoản** → **Khóa SSH**.
2. Trong khu vực Singapore, tải xuống khóa riêng mặc định.
3. Di chuyển file `.pem` đã tải xuống vào một thư mục riêng mà bạn chọn.
4. Không bao giờ tải file này lên GitHub, Discord hoặc bộ lưu trữ đám mây mà không được
   mã hóa mạnh.

## Bước 8: định cấu hình tường lửa Lightsail

Mở `akaine-server` → **Mạng** → **Tường lửa IPv4**. Xóa quyền truy cập SSH rộng rãi và
tạo các quy tắc sau:

| Mục đích | Giao thức | Cảng | Nguồn được phép |
| --- | --- | --- | --- |
| Quản trị SSH | TCP | 22 | IPv4 công cộng hiện tại của bạn, theo sau là `/32` |
| Chuyển hướng web | TCP | 80 | Tất cả địa chỉ IPv4 |
| API HTTPS | TCP | 443 | Tất cả địa chỉ IPv4 |
| Liên kết chơi | UDP | 10900 | Tất cả địa chỉ IPv4, chỉ khi bạn bật Link Play |
| Liên kết chơi | TCP | 10901 | Tất cả địa chỉ IPv4, chỉ khi bạn bật Link Play |

Để tìm IPv4 công cộng hiện tại của bạn, hãy tìm kiếm `what is my IP` trong trình duyệt
của bạn. Nếu nó hiển thị `203.0.113.10`, hãy nhập `203.0.113.10/32`. Khi IP nhà của bạn
thay đổi, hãy cập nhật quy tắc này trước khi thử lại SSH.

## Bước 9: kiểm tra SSH từ Windows

Mở PowerShell. Command sẽ hỏi key và static IP:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the downloaded SSH private key")
$serverIp = Read-Host "Lightsail static IPv4 address"

if ($serverIp -notmatch '^(?:\d{1,3}\.){3}\d{1,3}$') {
  throw "The server address is not an IPv4 value."
}

ssh -i $sshKey.FullName "ubuntu@$serverIp"
```

`Get-Item` kiểm tra key file tồn tại. `$serverIp` giữ địa chỉ trong cửa sổ PowerShell
hiện tại, còn format check đơn giản bắt hostname, URL hoặc input rỗng trước khi chạy
SSH. `-i` cho SSH biết private key nào chứng minh bạn được phép quản trị instance.

Kết nối đầu tiên hỏi bạn có tin cậy dấu vân tay của server hay không. Chỉ xác nhận nếu
IP là IP tĩnh bạn vừa tạo. Kết nối thành công kết thúc tại dấu nhắc tương tự như:

```text
ubuntu@ip-172-xx-xx-xx:~$
```

Gõ `exit` để quay lại Windows.

Nếu kết nối hết thời gian, hãy kiểm tra xem quy tắc tường lửa SSH có chứa IP công cộng
hiện tại của bạn không. Đừng giải quyết vấn đề bằng cách mở cổng 22 cho toàn bộ
Internet.

## Bước 10: tạo bản ghi DNS đầu tiên

Quay lại Cloudflare và mở miền của bạn → **DNS** → **Bản ghi**. Tạo nên:

| Kiểu | Tên | Nội dung | Trạng thái ủy quyền | TTL |
| --- | --- | --- | --- | --- |
| MỘT | `api` | IP tĩnh Lightsail của bạn | Chỉ DNS | Tự động |
| MỘT | `link` | IP tĩnh Lightsail của bạn | Chỉ DNS | Tự động |

Hiện tại, cả hai bản ghi chỉ có DNS. Đám mây màu xám có nghĩa là Cloudflare xuất bản câu
trả lời DNS nhưng không có lưu lượng proxy. `link` sẽ vẫn chỉ ở dạng DNS vì Link Play sử
dụng các cổng TCP/UDP mà proxy HTTPS thông thường không mang theo. Chương cài đặt server
sẽ chuyển sang màu cam `api` sau khi HTTPS được định cấu hình.

Chưa tạo `assets`. Nó sẽ được gắn trực tiếp vào thùng R2 sau khi bộ tài nguyên được
chuẩn bị.

## Bước 11: xác minh DNS từ Windows

Đóng và mở lại PowerShell. Nhập domain thật và static IP khi được hỏi:

```powershell
$domain = Read-Host "Your registered domain without https://"
$serverIp = Read-Host "Lightsail static IPv4 address"

$apiAnswer = nslookup "api.$domain" 1.1.1.1 2>&1 | Out-String
$linkAnswer = nslookup "link.$domain" 1.1.1.1 2>&1 | Out-String

if ($apiAnswer -notmatch [regex]::Escape($serverIp)) {
  throw "api.$domain does not resolve to the static IP."
}
if ($linkAnswer -notmatch [regex]::Escape($serverIp)) {
  throw "link.$domain does not resolve to the static IP."
}

$apiAnswer
$linkAnswer
```

Cả hai lệnh sẽ hiển thị IP tĩnh Lightsail. Các thay đổi DNS thường xuất hiện sau vài
phút nhưng các bản ghi được lưu vào cache có thể mất nhiều thời gian hơn.

Command query resolver `1.1.1.1` của Cloudflare thay vì tin câu trả lời cũ trong cache
Windows hoặc router. Hai block `if` là stop gate. Nếu một block lỗi, hãy kiểm tra đúng
DNS record đó và chờ propagation; không tạo record trùng như một cách retry.

## Kiểm tra công việc của bạn

- Cloudflare hiển thị tên miền là Đang hoạt động.
- Xác thực hai yếu tố AWS MFA và Cloudflare được bật.
- Số dư tín dụng AWS/ngày hết hạn được ghi lại hoặc tồn tại cảnh báo ngân sách gói trả
  phí 20 USD.
- `akaine-server` đang chạy ở Singapore với gói 2 GB.
- Một IPv4 tĩnh được đính kèm.
- SSH chỉ thành công từ IP được phép của bạn.
- `api.your-domain` và `link.your-domain` phân giải thành IP tĩnh.

## Xóa thiết lập đám mây

Nếu bạn dừng ở đây và không muốn tiếp tục tính phí server:

1. Xóa Lightsail instance.
2. Xóa static IP sau khi instance không còn.
3. Xóa bản ghi DNS `api` và `link`.
4. Hủy hoặc tắt tự động gia hạn nếu không muốn giữ tên miền.

Xóa instance không tự xóa mọi tài nguyên đã gắn hoặc đặt trước. Kiểm tra trang
**Networking** và **Snapshots** của Lightsail trước khi coi việc dọn dẹp là hoàn tất.

Tiếp theo: [Chuẩn bị máy tính Windows](03-workstation.md).
