# Backend tài khoản và lịch sử tài xế (local)

## Database

Backend tiếp tục dùng SQLite ở `GIGCA_SESSION_DB` (mặc định `.cache/backend.sqlite3`). Các bảng tài khoản/lịch sử được tạo bổ sung khi `Backend` khởi động, không xóa phiên hoặc kết quả cũ. Khởi động lại hoặc đăng nhập lại không mất lịch sử. Docker giữ file trong volume `gigca_sessions`.

PostgreSQL/PostGIS qua `GIGCA_DATABASE_URL` hiện phục vụ dữ liệu không gian của role Data; tài khoản/lịch sử chưa chuyển sang PostgreSQL.

## Đăng nhập

| Method | Path | Nội dung |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | `{ "username": "driver01", "password": "mat-khau-toi-thieu-12-ky-tu", "display_name": "Tài xế 01" }` |
| POST | `/api/v1/auth/login` | `{ "username": "driver01", "password": "..." }` |
| POST | `/api/v1/auth/logout` | `{}` và Bearer token |
| GET | `/api/v1/me` | Danh tính đang đăng nhập |

Tên đăng nhập 3–64 ký tự ASCII chữ/số/`_.-`, không phân biệt hoa thường. Mật khẩu 12–128 ký tự; không ghi mật khẩu thô. Hash PBKDF2-HMAC-SHA256 với salt ngẫu nhiên, 600.000 vòng. Token ngẫu nhiên chỉ lưu hash, có hạn 7 ngày. Đăng xuất thu hồi token đó; các phiên dùng token đó không còn truy cập được. Giới hạn thử xác thực: 10 lần/tên đăng nhập và 60 lần/IP trong 15 phút (tính cả đăng ký). Không tin header chuyển tiếp IP chưa được kiểm chứng.

Response đăng ký/đăng nhập có `driver`, `token`, `token_type`, `expires_in_s`. Gửi `Authorization: Bearer <token>` khi truy cập tài nguyên cá nhân. Không gửi password/token trong query string.

## Phiên làm việc và lịch sử gợi ý

1. Đăng nhập, giữ token tài khoản.
2. `POST /api/v1/sessions` với `{}` **và token tài khoản** để tạo phiên thuộc tài xế.
3. `PATCH /api/v1/sessions/{id}/context` với tọa độ, tùy chọn và `context_version` như API trước.
4. `POST /api/v1/recommendations` với `session_id`, `context_version` và token. Backend tự nạp hồ sơ, tối đa 5.000 chuyến và 5.000 đợt chờ mới nhất của chính tài xế vào engine. Client không thể chỉ định chủ sở hữu khác.
5. `GET /api/v1/me/recommendations?limit=20&offset=0` lấy lịch sử qua mọi phiên của tài xế; `GET /api/v1/me/recommendations/{id}` lấy kết quả đầy đủ, gồm input và phiên bản engine/config đã dùng.

Phiên khách cũ vẫn hoạt động khi gọi trực tiếp backend để tương thích. Không tự gán lịch sử khách cho tài khoản mới. Frontend có `/auth/login` và `/auth/register`, tái sử dụng layout V1 của template với tone navy. Dashboard yêu cầu đăng nhập; menu tài khoản ở header có nút đăng xuất.

Frontend gọi `/api/v1/*` qua Route Handler Next.js: token backend được giữ trong cookie HttpOnly, SameSite=Lax (Secure khi HTTPS), không trả token cho JavaScript trình duyệt. Proxy đính token vào request backend và kiểm tra Origin cho các request ghi. Session dashboard vì vậy được tạo dưới tài khoản hiện tại. Khi đăng nhập/đăng xuất, tải lại trang đầy đủ để xóa state tài xế trước. Khi backend/token không hợp lệ, cần đăng nhập lại.

## Hồ sơ và nhật ký

- `GET/PATCH /api/v1/me/profile`: biểu cước, tỷ lệ thực nhận, nhiên liệu và mục tiêu. PATCH nhận các trường trong `data/driver_input/driver_profile_template.json`; `null` xóa override để quay về cấu hình mặc định.
- `POST /api/v1/me/log-imports/preview`: nhận `trips`, `wait_spells` dạng mảng JSON hoặc chuỗi CSV đúng template; tối đa 2.000 dòng mỗi loại và 1 MiB request. Bắt buộc `consent_reference`, `collected_via`. Chỉ gửi lịch sử thực do tài xế cung cấp; hệ thống không xác minh độc lập nguồn khai báo.
- Response có `import_id`, `report`: số dòng hợp lệ, dòng bị loại, cảnh báo và ID trùng đã có. Chưa lưu nhật ký vào lịch sử sử dụng cho model ở bước preview.
- `POST /api/v1/me/log-imports/{id}/confirm` với `{}`: lưu các dòng hợp lệ trong transaction; không ghi đè ID đã tồn tại; gọi lặp không nhân đôi dữ liệu. Preview hết hạn sau 24 giờ.
- `GET /api/v1/me/trips` và `GET /api/v1/me/wait-spells`: lịch sử cá nhân, `limit` 1–100, `offset` không âm.
- `GET /api/v1/me/data-status`: số bản ghi của tài xế. `model_status=not_evaluated` không đồng nghĩa model đạt; kết quả kiểm tra model nằm trong `ml_insights` của lần tính gợi ý.

ID chuyến và đợt chờ là duy nhất **trong từng tài khoản**. Toàn bộ truy vấn profile/import/history đều lấy chủ sở hữu từ token. Truy cập import/kết quả của tài xế khác trả 404. Session không thuộc tài xế đang đăng nhập trả 401.

## Cách chạy và kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pip install -r api/requirements.txt
.\.venv\Scripts\python.exe -m api.v1_server
.\.venv\Scripts\python.exe -m unittest discover -s api/tests -v
```

Chạy thử không có provider key: đặt `GIGCA_DATA_MODE=sample` trong `.env`. Đây là snapshot nguồn mẫu, không phải dữ liệu theo vị trí hiện tại. Không commit database hoặc lịch sử tài xế.

## Phạm vi triển khai

Đây là app local có đăng nhập và phân quyền, chưa có khôi phục mật khẩu, xác minh email, MFA hoặc quản trị tài khoản. Dùng HTTPS và cấu hình reverse proxy trước khi mở server ra Internet. Guest compatibility ở backend chỉ phục vụ xem gợi ý, không có quyền đọc hồ sơ/lịch sử tài khoản. SQLite chưa mã hóa dữ liệu trên đĩa; cần quản lý quyền file và backup riêng. Giao diện xem/import lịch sử chưa có trong lần thêm trang auth này.

## Bản đồ hiện tại

`NEXT_PUBLIC_GIGCA_PREVIEW=true` làm frontend dùng snapshot preview cố định. Để dùng dữ liệu theo tọa độ: frontend đặt flag thành `false` rồi restart/rebuild; backend đặt `GIGCA_DATA_MODE=live`; cấu hình `API_TOMTOM` ở backend. Open-Meteo cấp dự báo tại lưới gần tọa độ; TomTom cấp tìm địa điểm/POI, tuyến xe máy và traffic segment gần GPS. `/api/route` trả route gốc gồm geometry/summary từ provider. Collector engine chỉ nạp tóm tắt tuyến. Chưa có traffic map-matching toàn tuyến và camera live trong lần thay đổi này. Key được cấu hình không bảo đảm mọi tọa độ có đủ dữ liệu hoặc endpoint hoạt động; cần kiểm tra thực tế provider.
