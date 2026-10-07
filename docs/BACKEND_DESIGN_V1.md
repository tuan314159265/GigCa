# Thiết kế backend GigCa — bản triển khai v1

Ngày: 07/10/2026. Trạng thái: thiết kế đề xuất, chưa phải các endpoint/bảng đã triển khai.

## 1. Phạm vi và nền tảng hiện có

Backend hiện có `api/dashboard.py` dùng ThreadingHTTPServer, gọi Engine và đọc fixture/sample/pipeline/PostGIS; `api/provider_proxy.py` có proxy TomTom. Data có migration, ETL, weather refresh và EngineDataInterface. Engine là hàm thuần tạo bốn hướng độc lập. StudioAdmin đang bật preview nên chưa gọi luồng live.

Mục tiêu v1: tài xế nhập/lấy vị trí, nhận bốn hướng có trạng thái dữ liệu rõ, xem tuyến và chọn điểm thay thế thuộc cùng hướng. Lưu được input, snapshot và kết quả để truy nguyên. Không cam kết đủ bốn hướng với dữ liệu thật: fare/booking/dropoff còn thiếu. Không thêm camera, dự báo xác suất có cuốc, tài khoản nền tảng gọi xe hoặc điều hướng tránh kẹt tự động vào v1.

Đề xuất một ứng dụng Python modular monolith, PostgreSQL/PostGIS dùng chung với Data, một worker cập nhật dữ liệu. Dùng FastAPI/Pydantic cho lớp HTTP mới; tái sử dụng Engine/Data thay vì viết lại. Đây là lựa chọn kiến trúc đề xuất, không phải dependency đang có. Chưa cần microservice, Redis, WebSocket hoặc message broker.

## 2. Ranh giới trách nhiệm

| Role | Chịu trách nhiệm | Không chịu trách nhiệm |
|---|---|---|
| FE | GPS có sự đồng ý, input, chọn hướng/điểm, map, loading/error | Công thức xếp hạng, provider key |
| Backend | Phiên, validation, điều phối nguồn/Engine, route, API, cache, lưu kết quả | Suy diễn booking từ POI/traffic |
| Data | Provider adapters, ETL, chuẩn hóa, PostGIS, freshness/coverage/provenance | Chọn thay tài xế |
| Engine | Readiness, scorer, giải thích, bốn kế hoạch, candidates | HTTP, auth, DB, clock hệ thống |

Cấu trúc đề xuất: `backend/app/{http,schemas,services,repositories,providers,jobs}`; tests ở `backend/tests`. `services/recommendations.py` điều phối; `services/selections.py` xử lý lựa chọn; `repositories` chỉ truy cập DB. Lõi Engine giữ trong `engine/src`; adapter và ETL giữ trong `data`.

## 3. Ngữ cảnh tài xế

- Origin bắt buộc trong API mới; không âm thầm mặc định Bến Thành. Gồm lat/lng, accuracy_m nếu GPS có, recorded_at và source=gps/manual.
- Idle: tính từ waiting_started_at khi tài xế chủ động bắt đầu chờ; hỗ trợ manual_idle_min. Không tự cho rằng tài xế đã trả khách nếu chưa có sự kiện xác nhận.
- horizon_min mặc định 60, giới hạn sản phẩm v1 1–480; max_reposition_km mặc định 3, giới hạn 0–50; idle 0–1440. Đây là giới hạn API đề xuất dựa trên adapter hiện có, không phải toàn bộ ràng buộc toán học Engine.
- Rain tolerance low/medium/high, mặc định medium. goal_weights tùy chọn; không dùng để gộp bốn hướng thành overallScore.
- Live/fixture do cấu hình server quyết định. UI tài xế không chọn sample/pipeline/database. Demo triển khai riêng và gắn is_demo trên mọi kết quả.
- Timestamp lưu UTC, hiển thị Asia/Ho_Chi_Minh; Engine nhận thời điểm đánh giá rõ ràng. Snapshot cũ không đổi generated_at thành hiện tại để giả dữ liệu mới.

## 4. API v1 đề xuất

Tất cả endpoint ứng dụng dưới `/api/v1`; giữ `/api/*` cũ trong giai đoạn chuyển FE.

| Method/path | Nội dung |
|---|---|
| POST /sessions | Tạo phiên ẩn danh có token phiên ngẫu nhiên, không cần đăng ký ở v1 |
| PATCH /sessions/{id}/context | GPS, cài đặt; trả context_version tăng dần |
| POST /sessions/{id}/waiting | action=start/stop, cập nhật đồng hồ chờ |
| POST /recommendations | session_id, context_version; tính và lưu một lần chạy |
| GET /recommendations/{id} | Đọc kết quả đã lưu, không tính lại âm thầm |
| POST /recommendations/{id}/selections | objective và candidate_id; chọn hướng/điểm thay thế |
| GET /sessions/{id}/recommendations | Lịch sử phân trang bằng cursor |
| GET /routes/{id} | Hình học GeoJSON, distance_m, duration_s, profile, observed_at |
| GET /conditions | Theo vị trí/radius/horizon; weather, traffic và trạng thái từng nguồn |
| GET /places | Theo vị trí/radius/category; POI và verification |
| GET /sources/status | Coverage, thời điểm, lỗi nguồn đã làm sạch, không chứa secrets |
| GET /capabilities | configured và reachable_checked_at tách riêng; có key không đồng nghĩa provider đang chạy |
| GET /map/tiles/{z}/{x}/{y} | Tile proxy allowlist server |
| GET /traffic/tiles/{z}/{x}/{y} | Lớp tốc độ tương đối, không gọi là số lượng xe |
| GET /health/live; GET /health/ready | Tiến trình sống; DB/migration sẵn sàng |

POST hỗ trợ Idempotency-Key theo phiên, cùng key khác payload trả 409. Token phiên gửi trong Authorization, kiểm tra quyền sở hữu ở mọi request. Context_version cũ trả 409 để FE tải lại, tránh kết quả theo GPS cũ.

Response recommendation có: recommendation_id, evaluated_at, origin, context_version, engine_version, config_hash, snapshot_id, is_demo, objectives, conditions, data_quality. Mỗi objective có status, confidence, primary_candidate_id, candidates, plan, limitations. Conditions phải dùng đúng dự báo Engine đã chọn, không lấy phần tử weather đầu tiên của snapshot tùy ý.

Candidate thống nhất envelope: candidate_id, target_ref={kind:area|poi,id}, name, location, rank, metrics (theo từng objective), explanation, route_status. Giữ ID gốc area_id/poi_id; ID envelope duy nhất trong lần chạy. Giá trị thiếu là null. Không ép score nghỉ 0–1, position 0–100 và yield đ/giờ thành cùng thang đo.

Error envelope: error.code, error.message, error.request_id, error.retryable. 422 input sai; 401 thiếu token; 404 tài nguyên không thuộc phiên/không có; 409 xung đột context; 429 giới hạn; 503 không có snapshot sử dụng được. Thiếu một nguồn vẫn trả 200 với trạng thái partial/insufficient_data từng hướng. API route độc lập có thể trả 502 nếu provider thất bại; không làm mất kết quả Engine đã lưu.

## 5. Luồng tính gợi ý

1. Xác thực phiên, validate context và version, chốt evaluated_at một lần.
2. Dùng PostGIS ST_DWithin để tìm các vùng/điểm trong phạm vi; bỏ phụ thuộc GIGCA_AREA_ID cố định của prototype. Ghi rõ phạm vi nguồn và vùng không được phủ.
3. Data đọc forecast phù hợp vị trí/thời gian, POI, traffic còn hạn và routing samples. Chỉ refresh trực tiếp có timeout; không để một provider giữ toàn request vô hạn.
4. Chuẩn hóa snapshot immutable có provenance. Loại/đánh dấu stale theo quy tắc Engine/Data; lưu snapshot và trạng thái thiếu. Forecast lịch sử demo không được dùng như dự báo hôm nay.
5. Gọi load_for_engine rồi run_driver_engine với context/preferences; Engine không fetch mạng.
6. Persist kết quả Engine nguyên bản, version/config_hash, candidates và cảnh báo. Dùng route enrichment riêng cho điểm đích có tọa độ; không sửa công thức scorer bằng tuyến mới sau khi đã tính.
7. Trả kết quả để FE hiện ngay. Tuyến có thể pending rồi FE lấy lại GET recommendation có presentation revision; raw Engine output vẫn immutable. Cần ghi rõ metrics chạy rỗng của scorer hiện là ước tính, khác với ETA tuyến thực.

Rest scorer cần route samples hợp lệ trước khi gọi Engine; route enrichment sau tính không tự biến một hướng thiếu dữ liệu thành available. Nếu cần bổ sung route rồi tính lại, tạo lần chạy mới có snapshot mới.

## 6. Chọn điểm thay thế — yêu cầu quan trọng

Candidates là các điểm trong cùng objective, không phải hướng thứ năm. Backend kiểm tra candidate thuộc recommendation/objective/phiên; không nhận một tọa độ tùy ý như ứng viên hợp lệ.

Engine hiện tạo plan chủ yếu cho điểm đầu bảng. Không được lấy plan điểm A rồi chỉ thay tên thành B: thời gian, metrics và hành động có thể sai.

Cần tách plan builders trong Engine để dựng plan từ một candidate cụ thể trên chính snapshot/context đã lưu. Selection service gọi builder, bổ sung route và trả selected_candidate, selected_plan, route, warnings. Giữ nguyên xếp hạng/primary của kết quả gốc; lựa chọn tài xế lưu riêng. Đây là thay đổi Engine cần triển khai, chưa có đầy đủ hiện nay.

Safety_comfort không mặc nhiên có 2–3 điểm thay thế: safe_corridors/avoid_zones hiện có thể chỉ là mô tả, chưa có hình học. Chỉ vẽ/chọn corridor khi Data cung cấp ID và geometry kiểm chứng; nếu thiếu, hiển thị điều kiện và kế hoạch, không tạo tuyến giả.

## 7. Database ứng dụng bổ sung

Giữ bảng Data đang có: area, weather_forecast, poi_feature, poi_grid_cell, waiting_location_candidate, route_observation, traffic_flow_observation, traffic_incident_observation, etl_run và summary tables.

Thêm migration riêng cho:

| Bảng | Trường/chức năng chính |
|---|---|
| driver_session | id UUID, token_hash, created_at, expires_at, context_version, context JSONB, waiting_started_at |
| recommendation_snapshot | id, schema_version, evaluated_at, payload JSONB, payload_hash, is_demo, provenance JSONB |
| recommendation_run | id, session_id FK, snapshot_id FK, context JSONB, engine_version, config_hash, raw_output JSONB, created_at |
| recommendation_candidate | id, run_id FK, objective, target_kind, target_id, rank, point geography(Point,4326), metrics JSONB; unique(run_id,objective,target_kind,target_id) |
| recommendation_selection | id, run_id FK, candidate_id FK nullable, objective, selected_plan JSONB, created_at; kiểm tra candidate cùng run/objective |
| route_result | id, origin/target geography, profile, distance_m, duration_s, geometry GeoJSON, provider, observed_at, expires_at, status; lưu theo chính sách provider |
| idempotency_record | session_id/key unique, payload_hash, response_ref, expires_at |

GiST index cho geography; B-tree session_id/created_at và run_id/objective/rank. Snapshot/run ghi trong transaction. Không tạo bảng fare/booking giả: chỉ thiết kế ingestion và schema khi có nguồn được xác nhận.

Chính sách đề xuất cho demo: phiên 24 giờ, lịch sử 7 ngày, không ghi GPS liên tục; có thao tác xóa phiên. Thời hạn production cần chốt với yêu cầu sản phẩm và điều khoản provider. Không mặc nhiên lưu raw payload/tile TomTom lâu dài; giữ chính sách nguồn Data đã ghi.

## 8. Jobs, cache, lỗi nguồn

Worker chạy weather refresh theo lịch cấu hình; lịch 60 phút là giá trị khởi đầu đề xuất, cần đối chiếu provider. Traffic polling theo nhu cầu: tái dùng cache 45 giây hiện có; quan sát quá 30 phút bị lọc theo Engine hiện tại. Route TTL ngắn và key gồm origin, target, profile, traffic option; không tái dùng tuyến từ vị trí cách xa tài xế.

V1 cache trong process cho provider, DB dùng cho job khóa/idempotency; khi nhiều replica mới dùng Redis/shared cache. Weather job ghi forecast vintage mới, không ghi đè lịch sử. Worker có khóa chống chạy trùng, retry hữu hạn/backoff và trạng thái lần chạy. Retention chạy định kỳ, không xóa snapshot còn được run tham chiếu trong thời gian giữ lịch sử.

Timeout tổng recommendation đề xuất 10 giây, upstream mỗi lần 3–5 giây, tối đa một retry trong deadline. Chỉ enrichment các điểm chính và 2 ứng viên thay thế khi được yêu cầu, tránh gọi route cho mọi POI. FE polling theo nhu cầu/visibility; chưa cần push realtime.

## 9. Triển khai và kiểm chứng

Docker Compose: frontend Next.js, backend ASGI, worker và PostGIS. Provider keys/DB URL qua môi trường server; không NEXT_PUBLIC key. Same-origin proxy; HTTPS khi triển khai, giới hạn kích thước body/radius/horizon/rate, allowlist upstream chống proxy tùy ý. Log request_id, latency, source failures, Engine mode; không log token/key/toàn bộ GPS. Metric: provider lỗi, tỷ lệ stale, số hướng insufficient_data, độ trễ recommendation.

Giai đoạn A: schema HTTP v1 + sessions + persistence + bridge FE, vẫn fixture rõ nhãn. Tiêu chí: cùng input/snapshot cho output tất định, lịch sử truy nguyên, không lộ dữ liệu giữa phiên.

Giai đoạn B: chọn vùng theo GPS + PostGIS + forecast job + TomTom route/traffic. Tiêu chí: GPS ngoài coverage báo thiếu, mất provider không làm giả kết quả, map tuyến đúng origin/target; test integration bằng DB test và provider stub, sau đó smoke test live có key.

Giai đoạn C: candidate envelope + plan builders + selection + FE so sánh. Tiêu chí: chọn B cập nhật đúng target/metrics/steps/route, vẫn giữ kết quả A nguyên bản; loại lựa chọn sai objective/phiên.

Giai đoạn D: vận hành, quota, retention, deployment; sau đó mới ingestion fare/booking nếu có nguồn. Không dùng việc test fixture đạt để công bố dự báo thu nhập thực tế.

## 10. Những điểm phải sửa từ prototype

- API mới yêu cầu origin rõ ràng, thống nhất default Engine 15/60/3/medium thay vì 25/180 demo; FE giới hạn horizon phải khớp 480.
- Chọn area theo GPS thay cho area_id môi trường cố định.
- Trả weather đúng scope Engine sử dụng, không fallback tùy tiện sang vùng đầu tiên.
- Phân biệt cấu hình key và kết nối thực, snapshot time và evaluated_at.
- Tách raw Engine metrics ước tính khỏi route/ETA trực tiếp.
- Thêm phiên, history, idempotency và selected-plan builder; hiện chưa có.
- Giữ dữ liệu demo tách nguồn live; không nâng status available chỉ vì có UI hoặc API trả 200.
