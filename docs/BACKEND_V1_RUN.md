# Backend v1 — hướng dẫn chạy và phạm vi hiện thực

Chạy từ thư mục GigCa: `python -m api.v1_server` (port 8000). API dashboard cũ được giữ tương thích. Không chạy đồng thời api.dashboard trên cùng port.

Đã có: phiên token 24 giờ, context version, kiểm tra GPS/input, start/stop chờ, gọi Engine, lưu input snapshot và kết quả, lịch sử 20 lần gần nhất, đọc kết quả theo quyền phiên, Idempotency-Key. Dữ liệu ứng dụng cục bộ lưu SQLite `.cache/backend.sqlite3` (gitignored); đây là bước A có thể chạy không cần cài DB. PostGIS hiện vẫn là nguồn dữ liệu địa lý khi chọn mode database. Chưa chuyển kho phiên sang PostgreSQL.

Biến môi trường: GIGCA_DATA_MODE=simulation/sample/pipeline/database (mặc định simulation); GIGCA_SESSION_DB đường dẫn DB cục bộ; cấu hình provider/PostGIS như backend cũ. Simulation trả is_demo=true. Sample/pipeline không phải nguồn live, metadata snapshot giữ mode và thời điểm gốc. Có token không đồng nghĩa đã có tài khoản tài xế.

Luồng client:
1. POST /api/v1/sessions với {} → session_id, token, context_version=0.
2. PATCH /api/v1/sessions/{id}/context với Authorization: Bearer TOKEN, JSON {"context_version":0,"current_lat":10.7769,"current_lng":106.7009,"horizon_min":60,"max_reposition_km":3,"rain_tolerance_level":"medium"} → version=1.
3. POST /api/v1/recommendations với cùng Authorization, Idempotency-Key tùy chọn, JSON {"session_id":"ID","context_version":1}.
4. GET /api/v1/recommendations/{run_id}?session_id=ID → kết quả đã lưu.
5. GET /api/v1/sessions/{id}/recommendations → lịch sử.
6. POST /api/v1/sessions/{id}/waiting JSON {"action":"start","context_version":1}; cập nhật version nhận về trước khi tính tiếp. Stop chỉ ngừng đồng hồ, manual idle sẽ được dùng lại.

Dashboard vẫn dùng endpoint /api/recommendations cũ, không tự tạo phiên hoặc sử dụng API v1. Preview không bị thay đổi. Adapter FE quản lý phiên, history UI, chọn candidate/plan builder, PostGIS persistence phiên, jobs production, rate limit, retention và deployment còn là các bước tiếp theo theo BACKEND_DESIGN_V1.md. Không có endpoint selection giả trả kế hoạch của điểm cũ.

Kiểm chứng: `python -B -m unittest discover -s api/tests -q`; test dùng DB tạm, không gọi provider thật. API v1 được thử HTTP tạo phiên, cập nhật và tính gợi ý. Không công bố live provider/database đã kiểm chứng.
