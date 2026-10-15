# Build và chạy GigCa v1.0

Đây là bản tích hợp đầu tiên của dashboard, API phiên, Data và Engine. Phiên bản v1.0 là mốc tích hợp nguyên mẫu, không khẳng định mọi nguồn dữ liệu live hoặc triển khai production đã được kiểm chứng.

## Docker Compose

Yêu cầu Docker Desktop chạy Linux containers. Chạy tại root repo GigCa.

```powershell
# Chỉ tạo file nếu chưa có; không ghi đè key đang dùng.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f compose.app.yaml up --build -d
docker compose -f compose.app.yaml ps
```

Trong `.env`, đặt `GIGCA_DATA_MODE=live`, `NEXT_PUBLIC_GIGCA_PREVIEW=false` và điền `API_TOMTOM` nếu cần POI, tuyến đường và giao thông. Không có key vẫn có thể lấy thời tiết Open-Meteo. Chỉ muốn preview: đặt `NEXT_PUBLIC_GIGCA_PREVIEW=true` rồi rebuild frontend.

Mở http://127.0.0.1:3000/dashboard/gigca. Nếu port 3000 bận, đặt `GIGCA_FRONTEND_PORT=3001` trong `.env` và dùng port 3001.

```powershell
docker compose -f compose.app.yaml logs --tail 100 -f
docker compose -f compose.app.yaml down
```

Lịch sử giữ trong volume `gigca_sessions`; `down -v` sẽ xóa volume đó. Key chỉ truyền lúc chạy backend, không đưa vào image/frontend. Đổi cờ preview cần `up --build -d`; đổi key chỉ cần `up -d`. Không truyền `SSL_CERT_FILE` có đường dẫn Windows vào container Linux.

## Build frontend bằng Node.js

Yêu cầu Node.js 22 và npm. Chạy từ root repo:

```powershell
cd web
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run build
```

Trong `web/.env.local`, đặt `NEXT_PUBLIC_GIGCA_PREVIEW=false` để build live hoặc `true` để preview. Build dùng font local, không cần tải Google Fonts. Địa chỉ proxy mặc định là `http://127.0.0.1:8000`; Docker build dùng `http://backend:8000`.

Để chạy development: `npm run dev -- --hostname 127.0.0.1 --port 3000`. Nếu đã build standalone, chạy `npm run start -- --hostname 127.0.0.1 --port 3000`; Next.js có thể cảnh báo dùng standalone server, Dockerfile đã đóng gói server đó cùng public/static.

## Backend ngoài Docker

Yêu cầu Python 3.12. Từ root repo, tạo môi trường và chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r data/db/requirements.txt
.\.venv\Scripts\python.exe -m api.v1_server
```

Backend mặc định ở 127.0.0.1:8000. Collector live trực tiếp không yêu cầu PostGIS; phiên và kết quả lưu SQLite. `compose.yaml` dành cho PostGIS riêng, không tự chạy migration/seed trong Compose app.

## Kiểm chứng và phạm vi

```powershell
python -B -m unittest discover -s api/tests -q
python -B -m unittest discover -s engine/tests -q
docker compose -f compose.app.yaml config --quiet
```

Tại mốc đóng gói: frontend production build thành công, 19 kiểm thử API qua và cấu hình Compose hợp lệ. Docker daemon chưa hoạt động lúc kiểm tra nên chưa xác nhận build image/run container; TomTom chưa kiểm chứng end-to-end bằng key thật. Camera và dữ liệu cuốc xe thật chưa có nguồn; các kết quả thiếu dữ liệu phải giữ trạng thái thiếu dữ liệu.
