# Chạy thử dashboard GigCa

## Local

Chạy từ `D:\HCMUT\STUDY\261\Gigca\GigCa`, không phải thư mục template bên ngoài.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api/requirements.txt
# Chỉ copy nếu chưa có .env; không ghi đè key đã điền.
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m api.v1_server
```

Terminal thứ hai:

```powershell
cd D:\HCMUT\STUDY\261\Gigca\GigCa\web
# node_modules hiện đã có; chỉ npm ci khi cần cài lại và đã dừng Next server.
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Trong `web/.env.local`: NEXT_PUBLIC_GIGCA_PREVIEW=false; GIGCA_API_URL=http://127.0.0.1:8000. Khởi động lại Next sau khi sửa env. Mở http://127.0.0.1:3000/auth/login, tạo tài khoản hoặc đăng nhập tài khoản của bạn.

## Hai luồng khác nhau

- **Vị trí và lịch sử của tôi:** lấy GPS hoặc tìm địa điểm, nhập yêu cầu rồi Tính gợi ý. Backend sử dụng GIGCA_DATA_MODE=live trong `.env`. Lịch sử cá nhân lấy theo tài khoản đã xác thực. Tài xế mới không có dữ liệu cuốc nên thu nhập/giữ vị trí có thể chưa đủ dữ liệu; weather và rest/routing vẫn có thể hoạt động. API key không tạo ra lịch sử hoặc booking.
- **Mô phỏng nghiên cứu:** đặt GIGCA_RESEARCH_DEMO=true ở `.env`, khởi động lại backend. Dataset mặc định ở `.cache/synthetic/gigca-drivers-32-v2/contextual-seed7`. Chọn tài xế D001…D032 rồi Tính gợi ý. Chế độ này tái hiện bối cảnh sau ngày cuối dữ liệu, không gọi live weather/traffic/routing và không lưu vào lịch sử thật. Nền bản đồ vẫn là nền địa lý trực tuyến; các marker thuộc mô phỏng. Mưa synthetic không có xác suất mưa được hiệu chỉnh, nên biểu đồ xác suất có thể trống.

Nhãn ML/thống kê/thiếu dữ liệu luôn đi cùng kết quả. Năng suất theo công thức khác dự đoán ML cho một chu kỳ; khoảng chỉ hiển thị khi backtest xác nhận độ phủ. Số mẫu, lỗi và lý do giữ baseline nằm ở chi tiết model. Bốn hướng vẫn bấm xem được khi thiếu dữ liệu. Model đang fit/cache theo nội dung lịch sử trong request; chưa phải hệ thống training job độc lập triển khai production.

## Provider và key

| Nguồn | Cấu hình | Giới hạn |
|---|---|---|
| Open-Meteo | Không key trong luồng đang dùng | Dự báo lưới gần tọa độ, không đo chính xác từng điểm |
| TomTom Search | API_TOMTOM phía backend | Tìm địa điểm/POI; POI chưa xác minh quyền đỗ |
| TomTom Routing | Cùng key, quyền routing | Geometry, thời gian, khoảng cách; không mặc định có traffic mọi đoạn |
| TomTom Traffic Flow | Cùng key, quyền traffic | Segment gần GPS không đại diện toàn tuyến |
| TomTom map tiles | Có thể cần quyền sản phẩm riêng | Key hiện tại trả 403 khi thử; UI chuyển nền OpenStreetMap |
| ShopAIKey | GIGCA_LLM_* | Chỉ cần khi tạo persona mới; web không gọi LLM |
| Camera | Chưa nối catalog/ảnh vào UI | Không chặn luồng chính |

Các section traffic trong bảng tuyến lấy từ chính response routing; khi thiếu thì hiển thị chưa có, không mặc định thông thoáng. Lớp giao thông bản đồ là lớp provider hiện tại, không thể hiện số lượng xe đo được. Dataset history synthetic không cung cấp camera hoặc traffic live.

Provider timeout/cache đã có; chưa có bộ quản lý quota/rate-limit provider toàn hệ thống. Không triển khai công khai bản demo với polling nhiều người khi chưa bổ sung phần đó. Key ở backend; không dùng biến NEXT_PUBLIC cho secret. SSL_CERT_FILE chỉ dùng đường dẫn chứng chỉ tồn tại trên máy Windows; không đưa đường dẫn Windows vào container Linux.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m scripts.check_demo_providers
.\.venv\Scripts\python.exe -m unittest discover -s api/tests -q
.\.venv\Scripts\python.exe -m unittest discover -s engine/tests -q
```

`check_demo_providers` gọi một số request provider, có thể tính vào quota; không in key. Báo cáo `.cache/provider-smoke.json`. `scripts.smoke_demo_app` kiểm tra HTTP qua frontend đang chạy bằng tài khoản local thử riêng, lưu credentials ở `.cache/demo-account.json` (không commit), kiểm tra auth cookie, research và một request live. Không dùng script này để load-test provider. Báo cáo `.cache/app-smoke.json`.

## Docker

```powershell
docker compose -f compose.app.yaml up --build
# Bật thêm dataset nghiên cứu local (thư mục dataset phải tồn tại):
docker compose -f compose.app.yaml -f compose.research.yaml up --build
```

Frontend dùng GIGCA_API_URL=http://backend:8000 trong container; tài khoản/history hiện dùng SQLite trong named volume gigca_sessions. PostGIS của lớp data không tự thay DB tài khoản. Không xóa volume nếu cần giữ tài khoản. Dataset research mount read-only và không nằm trong image/Git. Các thay đổi Docker ở đợt này cần kiểm tra build trên Docker Engine của bạn; không coi build Next local là đã kiểm tra Docker.
