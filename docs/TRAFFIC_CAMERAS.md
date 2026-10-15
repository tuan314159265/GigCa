# Camera công khai TP.HCM

Main app: bảng giao thông → Chi tiết một đường → camera gần các đoạn thuộc đường đó.
Catalog hiện tại `data/raw/cameras/hcmc-public-cameras.json` lấy ngày 07/10/2026,
796 camera có tọa độ; trạng thái UP là báo cáo lúc lấy catalog, không phải kiểm tra ảnh hôm nay.
Không gọi nguồn thành phố chỉ để tìm tọa độ: spatial search chạy trên catalog local.

API đăng nhập:

- POST `/api/v1/cameras/near-route`: `{ "lines": [[[lat,lng],[lat,lng]]], "radius_m": 300 }`.
  Tối đa 40 polyline, 500 điểm, radius 50–1000m. Mặc định trả tối đa 3 camera gần nhất.
  Khoảng cách tính đến đoạn tuyến, không chỉ đầu/cuối. Các đoạn rời không nối qua khoảng trống.
- GET `/api/v1/cameras/{catalog_id}/image`: trả JPEG/PNG/WebP qua proxy cùng origin.
  `{catalog_id}` là ID record trong catalog; upstream dùng CamId, không nhầm với Code hiển thị.

Nguồn chính đã xác minh: `https://giaothong.hochiminhcity.gov.vn/Render/ImageHandler.ashx?id={CamId}`.
Ngày 15/10/2026 thử CamId 649da72ca6068200171a6dbb nhận HTTP 200 image/jpeg, 49.888 bytes.
Không cần API key TomTom. Đây là endpoint website công khai, chưa phải API tích hợp có SLA.
SnapshotUrl công khai trong catalog là nguồn dự phòng; endpoint CameraHandler port8007 cũ
có thể trả 403. Không dùng credentials riêng hoặc vượt xác thực.

Backend chỉ cho phép host/path cố định; không nhận URL từ client, kiểm tra redirect,
content type/chữ ký ảnh, tối đa 3MB, timeout8s/source, cache thành công/lỗi20s,
tối đa16 cache entry và3 fetch đồng thời. HTML200 không được coi là ảnh.
FE tải khi mở Chi tiết hoặc chọn camera/Làm mới; camera đang xem tự cập nhật mỗi30s
khi tab hiển thị, dừng khi đóng Chi tiết hoặc chuyển tab, trở lại thì cập nhật ngay.
Tuyến/giao thông cũng poll30s khi tab hiển thị (nguồn có thể có cache riêng).
Lỗi tải lần đầu thì thử camera tiếp theo; lỗi khi đã có ảnh thì giữ ảnh cũ kèm cảnh báo.
Không chặn model/routing/traffic. Không tự poll tất cả camera.

Tải ảnh lúc là thời điểm backend nhận ảnh, KHÔNG phải thời điểm chụp.
Nguồn hiện không cung cấp captured_at đã xác minh; không gắn nhãn video live.
Gần tuyến không chứng minh góc nhìn camera cùng chiều hoặc cùng mặt đường (cầu/đường song song).
Nguồn còn nguyên link mở cổng thành phố.

Docker compose mount `./data/raw/cameras:/app/cameras:ro`, đặt GIGCA_CAMERA_CATALOG.
Local mặc định đọc file trên. Thiếu catalog hoặc ảnh không tải được có trạng thái rõ ràng.
Refresh catalog khi cần bằng script hiện có:

```powershell
.\.venv\Scripts\python.exe scripts/fetch_public_cameras.py --output data/raw/cameras/hcmc-public-cameras.json
```

Lệnh refresh gọi website, có thể thất bại nếu website đổi API; không ghi đè file cũ khi lỗi.
