# Luồng nhận input hiện tại và dữ liệu theo GPS

Trạng thái: hợp đồng triển khai bổ sung cho BACKEND_DESIGN_V1; chưa có collector live hoàn chỉnh trong code. Không coi việc api v1 nhận GPS là đã lấy dữ liệu live.

## Input FE

PATCH /api/v1/sessions/{id}/context, Authorization Bearer token:

```json
{
  "context_version": 0,
  "current_lat": 10.7769,
  "current_lng": 106.7009,
  "idle_duration_min": 15,
  "horizon_min": 60,
  "max_reposition_km": 3,
  "rain_tolerance_level": "medium"
}
```

Các trường trên đã được backend v1 hỗ trợ. Cần bổ sung origin_accuracy_m (nullable, >=0), origin_recorded_at (ISO timestamp), origin_source (gps/manual). Ba trường này thuộc metadata phiên, không truyền trực tiếp vào DriverContext. FE không gửi API key, area_id cố định, fare tự dựng hoặc mode demo/live.

Nút Vị trí của tôi lấy GPS thật, hiện tọa độ và thời điểm cập nhật; từ chối quyền thì nhập vị trí thủ công. Khi chưa có origin xác nhận, không tự tính bằng tọa độ initialInput Bến Thành. Preview dùng phiên riêng có nhãn và không trộn với phiên live.

## Collector cần triển khai

Hàm `collect_for_origin(origin, evaluated_at, horizon_min, radius_km)` trả snapshot đúng contract Engine, provenance và lỗi nguồn. Cấu hình server GIGCA_DATA_MODE=live là mode mới phải bổ sung; API hiện chưa hỗ trợ mode này.

1. Chọn khu vực trong radius bằng PostGIS geography ST_DWithin, không đọc GIGCA_AREA_ID cố định. Nếu không có khu vực được phủ, có thể tạo point_sample theo origin và ghi coverage rõ; không dựng dữ liệu cuốc/điểm trả.
2. Weather: truy vấn forecast mới phù hợp vị trí và khoảng thời gian cần xét. Nếu chưa có, refresh cho tọa độ đó rồi lưu vintage. Extractor hiện đọc tọa độ sample cố định cần đổi thành tham số lat/lng; web.get_weather hiện chỉ đọc dữ liệu DB đã cập nhật, không tự fetch Open-Meteo. Dự báo có grid_location, issued/fetched_at, valid_time; không sửa sample cũ thành thời tiết hiện tại.
3. POI: truy vấn PostGIS và tùy chọn bổ sung TomTom Search quanh origin. Chuẩn hóa cafe/parking/gas_station/rest; unknown quyền đỗ xe giữ unknown, không đặt verified=true chỉ vì tìm được tên trên bản đồ.
4. Routing: trước Engine, lấy route distance/duration theo origin tới tập POI nghỉ giới hạn. Profile phải được xác nhận phù hợp xe máy. Route thất bại thì loại/đánh dấu thiếu, không thay bằng đường thẳng. Route tới khu vực chỉ là enrichment; scorer cuốc hiện vẫn dùng ước tính của chính Engine.
5. Traffic: TomTom Flow tại điểm/segment được quan sát và metadata vùng phủ. Một lần fetch tại GPS không đại diện mọi đường trong radius. Traffic tiles phục vụ hình ảnh UI riêng, không chuyển pixel thành dữ liệu mật độ hoặc điểm Engine. Incident chưa tích hợp đầy đủ không được giả là Engine đã dùng.
6. Trip value/dropoff: chỉ đọc nguồn nghiệp vụ hợp lệ nếu có; hiện thiếu thì readiness hai hướng đầu insufficient_data. Không dùng POI/traffic thay thế.
7. Gắn snapshot_id, thời điểm đánh giá, thời điểm từng observation, nguồn, limitations; validate contract rồi gọi Engine. Tính và trả đúng thời tiết đã chọn theo scope Engine.

## Điều phối và response

POST /api/v1/recommendations giữ session_id/context_version; server quyết định nguồn. Response mở rộng data_mode=live|simulation|sample|pipeline|database, is_demo, evaluated_at ISO, origin_used, snapshot.as_of, provider_status từng nguồn và warnings. Live có thể partial; live không đồng nghĩa mọi hướng available. Source lỗi không fallback âm thầm sang fixture.

FE hiện loading trong khi thu thập; trả partial nếu còn đủ dữ liệu hữu ích. Lỗi weather không làm mất POI; thiếu traffic không hiện tốc độ 0. Map chỉ hiển thị route thực, nguồn thiếu thì badge chưa có tuyến. Mỗi kết quả gắn context_version; GPS mới đến khi request cũ chạy thì bỏ response cũ và tính lại có giới hạn tần suất.

Cache weather theo provider grid + vintage + forecast window; POI theo vùng + loại + phạm vi; route theo origin/target/profile/options; traffic theo segment và observed_at. TTL tách khỏi độ hợp lệ dữ liệu. Độ dịch chuyển GPS, accuracy và thời gian cập nhật dùng quyết định refresh; ngưỡng phải là cấu hình sản phẩm, không hardcode giả định độ chính xác.

## Thứ tự sửa code

A. FE: tách initialInput demo khỏi origin live; gọi phiên v1, cập nhật context/version, gửi tính gợi ý; xử lý error envelope mới. Hiện FE vẫn gọi API cũ.
B. Data: collector theo lat/lng; refactor weather extractor nhận origin; spatial lookup thay area_id cố định; giữ nguồn/coverage/time.
C. Backend: mode live, tích hợp collector, lưu snapshot nguyên bản và output; trả origin_used và conditions đúng scope.
D. UI: cập nhật marker/tuyến/charts từ response mới; preview vẫn độc lập; không yêu cầu tài xế chọn database.
E. Kiểm chứng: hai GPS xa nhau không nhận cùng snapshot cứng; thay radius/horizon/rain làm thay đổi dữ liệu/đánh giá phù hợp; GPS ngoài coverage báo rõ; provider lỗi/expired không dùng fixture; dữ liệu cuốc thiếu giữ insufficient_data; session isolation và context race.

Chỉ bật mặc định live sau smoke test provider có key và DB được cấu hình. Các test fixture hiện có không thay thế smoke test này.
