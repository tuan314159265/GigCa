# Chạy GigCa bằng Docker

Yêu cầu Docker Desktop đang chạy với Linux containers. Chạy mọi lệnh dưới đây từ thư mục `GigCa`, nơi có `compose.app.yaml`.

## Luồng live

Nếu chưa có `.env`, sao chép `.env.example` thành `.env`. Giữ file hiện có nếu đã cấu hình.

```env
API_TOMTOM=your_key
GIGCA_DATA_MODE=live
NEXT_PUBLIC_GIGCA_PREVIEW=false
GIGCA_FRONTEND_PORT=3000
```

```powershell
docker compose -f compose.app.yaml up --build -d
docker compose -f compose.app.yaml ps
```

Mở http://127.0.0.1:3000/dashboard/gigca, cho phép GPS hoặc nhập tọa độ rồi tính gợi ý.
Nếu port 3000 đang được dùng bởi `npm run dev`, dừng process đó hoặc đặt `GIGCA_FRONTEND_PORT=3001` trong `.env`.

Frontend production gọi backend qua `http://backend:8000` trong mạng Compose. Backend không publish port ra máy host. Key chỉ được cấp cho backend lúc chạy, không được chép vào image hay đưa vào build frontend. Không đưa đường dẫn `SSL_CERT_FILE` của Windows vào container; Python image dùng CA của Linux.

Không cần PostGIS cho collector live trực tiếp. Phiên, snapshot và kết quả lưu trong named volume `gigca_sessions`, giữ lại khi restart hoặc `down`. File `compose.yaml` cũ vẫn dành riêng cho PostGIS; Compose app không tự tạo schema, seed hay chạy ETL.

Thiếu key TomTom vẫn có thể lấy dự báo Open-Meteo. Tuyến, POI và giao thông thật cần key; camera và cuốc xe thật chưa có nguồn. Bật live không tự tạo dữ liệu thay thế.

## Preview

Đặt `NEXT_PUBLIC_GIGCA_PREVIEW=true` trong `.env`, rồi chạy lại `up --build -d`. Cờ preview và địa chỉ proxy được đóng vào build Next.js, nên đổi cờ phải rebuild. Docker không đọc `web/.env.local` của máy host.

## Quản lý

```powershell
docker compose -f compose.app.yaml logs --tail 100 -f
docker compose -f compose.app.yaml down
```

Không dùng `down -v` nếu muốn giữ lịch sử. Khi đổi key, chạy lại `up -d` để tạo lại backend với cấu hình mới. Không cần rebuild chỉ để đổi key.

Đây là đóng gói nguyên mẫu local, chưa phải triển khai production có HTTPS, tài khoản và giới hạn request. GPS trên thiết bị khác cần một origin được trình duyệt cho phép, thường là HTTPS; cấu hình hiện tại chỉ mở frontend trên localhost.
