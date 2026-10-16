# GigCa API

Python 3.12 / ThreadingHTTPServer, không phải FastAPI.
Chạy python -m api.v1_server từ root; Docker và cấu hình theo [README chính](../README.md).

## Thành phần

- v1_server.py, dashboard.py: HTTP và điều phối khuyến nghị.
- driver_accounts.py, session_service.py: tài khoản/phiên/lịch sử SQLite.
- main_model.py: artifact, miền hỗ trợ, hai mục tiêu ML.
- live_candidates.py: điểm đến API, công trình ưu tiên, POI địa phương dự phòng.
- poi_policy.py: điều chỉnh POI–thời gian nhỏ.
- provider_proxy.py, nearby_traffic.py, traffic_cameras.py: nguồn ngoài.
- llm_explanations.py: diễn giải có bằng chứng và provider dự phòng.

## API chính

| Method | Endpoint | Vai trò |
|---|---|---|
| GET | /api/health | Health check |
| POST | /api/v1/auth/register | username, password, display_name |
| POST | /api/v1/auth/login | Đăng nhập |
| POST | /api/v1/auth/logout | Thu hồi token |
| GET | /api/v1/me | Tài khoản |
| POST | /api/v1/sessions | Tạo phiên |
| PATCH | /api/v1/sessions/{id}/context | Vị trí/tùy chọn, kiểm tra version |
| POST | /api/v1/recommendations | session_id, context_version |
| GET | /api/v1/me/recommendations | Lịch sử riêng |
| GET/PATCH | /api/v1/me/profile | Hồ sơ |
| GET | /api/v1/traffic/nearby?lat=...&lng=... | Đường quanh GPS |
| POST | /api/v1/cameras/near-route | Camera gần tuyến |
| GET | /api/v1/cameras/{id}/image | Snapshot |

Backend trực tiếp dùng Authorization: Bearer token; browser dùng BFF với cookie HttpOnly.
Username 3–64 ký tự ASCII chữ/số/_.-, password 12–128 ký tự.
Password hash PBKDF2-HMAC-SHA256 với salt; token lưu hash, có hạn và thu hồi khi logout.
Tài nguyên cá nhân kiểm tra chủ sở hữu. Database tài khoản không commit.

## Vận hành

GIGCA_LIVE_CANDIDATES=true bật ứng viên động; false dùng catalog cũ.
Ứng viên cache 300 giây; POI context 900 giây; LLM thành công 300 giây.
Provider tương thích OpenAI → Gemini → lý do engine; LLM không đổi target/score/money.
Không có TomTom thì thiếu điểm đến/tuyến/traffic live; không tự sinh dữ liệu giả.
Camera snapshot không xác nhận thời điểm chụp.

SQLite ở named volume; model/dataset readonly. Chỉ nạp joblib tin cậy, khớp hash và phiên bản sklearn.
Thay artifact cần restart backend.

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s api/tests -q
~~~
