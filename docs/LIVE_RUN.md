# Chạy GigCa theo GPS/input hiện tại

Đã hiện thực collector live ở data/live_collector.py và FE gọi API phiên v1. Đây thay thế mô tả phần collector chưa có trong LIVE_INPUT_DESIGN.md và BACKEND_V1_RUN.md. Preview vẫn dùng fixture riêng khi NEXT_PUBLIC_GIGCA_PREVIEW=true.

## Cấu hình

Backend GigCa/.env (đã tạo local, gitignored):

```
API_TOMTOM=
GIGCA_DATA_MODE=live
GIGCA_SESSION_DB=.cache/backend.sqlite3
```

Điền key TomTom của bạn, giữ ở server. Không cần PostGIS để chạy collector live trực tiếp phiên bản này; phiên và snapshot/kết quả lưu SQLite cục bộ. Chế độ database cũ vẫn dùng PostGIS.

Frontend gigca-studio/.env.local:

```
NEXT_PUBLIC_GIGCA_PREVIEW=false
```

Khởi động từ thư mục backend: `python -m api.v1_server` (8000). Frontend: `npm run dev -- --hostname 127.0.0.1 --port 3000`. Next proxy /api tới 8000. Không chạy api.dashboard đồng thời cùng port. Sau thay đổi env restart service tương ứng.

## Sử dụng

Mở /dashboard/gigca → Vị trí của tôi hoặc nhập cả hai tọa độ → chỉnh thời gian xét, giới hạn km, mức chịu mưa → Tính gợi ý. Không tự tính bằng Bến Thành khi chưa có vị trí. FE tạo token phiên trong bộ nhớ, gửi context/version và yêu cầu Engine. Không có lựa chọn nguồn database trên form tài xế nữa. Sau khi có kết quả, polling 60 giây khi tab đang hiển thị dùng vị trí đã xác nhận gần nhất; chưa watchPosition liên tục. Muốn cập nhật GPS di chuyển, bấm lấy vị trí và tính lại.

Backend lấy dự báo Open-Meteo theo tọa độ, tìm tối đa 3 quán cafe trong bán kính tối đa 5km qua TomTom và lấy route motorcycle từ origin; loại route vượt max km. TomTom Flow chỉ là segment gần GPS; không đại diện toàn bộ vùng. Cache có key tọa độ/radius và giữ observed_at lần fetch thật; lỗi nguồn không fallback fixture. Không tự xác nhận parking hoặc mở cửa. Collector v1 chỉ tìm cafe, chưa mở rộng mọi loại POI. Engine thời tiết sử dụng giờ bắt đầu; precipitation của Open-Meteo thuộc giờ trước được chuyển cửa sổ tương ứng.

Hai hướng fare/dropoff chưa có dữ liệu thật trả insufficient_data. POI/route/traffic cần TomTom key; nếu thiếu vẫn có thể nhận weather khi mạng cho phép. Các số mô phỏng của preview không xuất hiện trong response live.

## Kiểm chứng và giới hạn

17 test API (gồm collector stub, thay tọa độ, mất nguồn, route vượt radius, phân quyền phiên), 54 test Engine; TypeScript pass. Cần phân biệt stub với smoke test provider thật. Không công bố TomTom hoạt động khi chưa có key. Proxy route/map/traffic dùng code nhánh Data có sẵn; chưa triển khai candidate selection mới, routing tránh kẹt tự động hoặc camera. Lịch sử lưu server nhưng chưa có màn hình lịch sử FE. Collector chưa persist provider observations vào PostGIS và chưa có scheduler production.

Nguồn API đối chiếu: https://open-meteo.com/en/docs và https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route .

Smoke test 07/10/2026: gọi qua Next proxy port 3000, API phiên v1 với tọa độ 10.7769/106.7009 trả live, 3 giờ dự báo Open-Meteo thật và safety_comfort=partial. TomTom chưa có key nên chưa kiểm chứng trực tiếp. Python MSYS dùng SSL_CERT_FILE trỏ .cache/windows-roots.pem xuất từ Windows LocalMachine Root; không tắt xác minh TLS. File chứng chỉ/cache và .env không commit. Nếu chuyển máy cần dùng CA trust hợp lệ của môi trường mới.
