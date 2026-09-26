# Data catalog — trường dữ liệu dự kiến

Tên dưới đây là tên chuẩn hóa nội bộ để các role thống nhất. Trường provider-specific cần giữ trong adapter/raw metadata nếu cần truy vết. `null`/không có nghĩa là chưa lấy được, không có coverage hoặc nguồn không cung cấp; không tự điền thành 0.

## Snapshot chung

| Tên biến | Kiểu/đơn vị | Mô tả |
|---|---|---|
| `schema_version` | string | Phiên bản schema của file. |
| `dataset_id` | string | Định danh loại snapshot. |
| `generated_at` | ISO 8601 datetime | Thời điểm crawler tạo file. |
| `location.latitude` | number, độ WGS84 | Vĩ độ điểm lấy mẫu. |
| `location.longitude` | number, độ WGS84 | Kinh độ điểm lấy mẫu. |
| `coverage.radius_m` | number, m | Bán kính vùng POI lấy quanh tâm. |
| `sources[]` | object list | Provider, URL tài liệu/API, attribution/license và trạng thái của từng nguồn. |

## Thời tiết (`weather.hourly[]`)

| Tên biến | Kiểu/đơn vị | Mô tả |
|---|---|---|
| `valid_time` | ISO 8601 datetime | Giờ dự báo áp dụng; không phải thời điểm tải dữ liệu. |
| `precipitation_mm` | number, mm | Tổng precipitation của khung thời gian theo định nghĩa provider; với Open-Meteo hourly là lượng của giờ trước. |
| `precipitation_probability_pct` | number, % | Xác suất có precipitation do provider dự báo; không phải độ tin cậy chắc chắn tại một điểm. |
| `apparent_temperature_c` | number, °C | Nhiệt độ cảm nhận theo mô hình provider. |
| `shortwave_radiation_w_m2` | number, W/m² | Bức xạ sóng ngắn trung bình theo khung thời gian; dùng làm tín hiệu nắng, không tự quy đổi thành UV/chỉ số an toàn. |
| `wind_speed_10m_kmh` | number, km/h | Tốc độ gió tại cao độ chuẩn 10 m theo provider. |
| `wind_gusts_10m_kmh` | number, km/h | Gió giật cực đại của khung giờ trước theo provider. |
| `weather_code_wmo` | integer | Mã trạng thái thời tiết WMO từ provider. |

## POI (`pois[]`)

| Tên biến | Kiểu/đơn vị | Mô tả |
|---|---|---|
| `osm_type` | string | Kiểu phần tử OSM: node/way/relation. |
| `osm_id` | integer | ID phần tử trong OpenStreetMap. |
| `name` | string/null | Tên POI nếu OSM có ghi. |
| `latitude`, `longitude` | number, độ WGS84 | Node location hoặc tâm bounding box cho way/relation; trường hợp tâm xấp xỉ phải có `point_method`. |
| `point_method` | enum | Cách tạo tọa độ: `node_coordinate` hoặc `osm_bbox_center_approximation`. Không dùng tâm bbox như lối vào/điểm dừng chính xác. |
| `category` | string | Nhóm chuẩn hóa (amenity, shop, public_transport…). |
| `subcategory` | string/null | Giá trị tag cụ thể (cafe, toilets, parking…). |
| `tags` | object | Tags OSM giữ lại để truy vết/chuẩn hóa sau. |

POI là mô tả nơi chốn. POI không xác nhận chỗ được phép dừng/đỗ và không cho biết số cuốc, mật độ xe hay xác suất nhận cuốc. Chưa tính mật độ trong raw snapshot; mật độ phải tính theo polygon ô và diện tích thực.

## Đường, routing, giao thông (đang chờ provider)

| Tên biến đề xuất | Kiểu/đơn vị | Mô tả/trạng thái |
|---|---|---|
| `edge_id`, `from_node`, `to_node` | string | ID edge có hướng và hai node nối. |
| `length_m` | number, m | Chiều dài edge theo graph. |
| `duration_s` | number, s | Thời gian đi theo routing provider/profile và thời điểm lấy. Không mặc định là live traffic. |
| `routing_profile` | string | Profile phương tiện dùng để tạo route (car/bike/custom…). |
| `current_speed_kmh` | number, km/h | Tốc độ quan sát từ traffic provider nếu có. Chưa có trong sample. |
| `free_flow_speed_kmh` | number, km/h | Tốc độ thông thoáng dùng làm baseline. |
| `traffic_confidence` | number/null | Confidence của provider nếu được định nghĩa. Không tự diễn giải thành xác suất cuốc. |
| `observed_at` | ISO 8601 datetime | Thời điểm traffic observation có hiệu lực. |

## Sự kiện, báo cáo, nhu cầu (chưa có nguồn xác nhận)

| Tên biến đề xuất | Mô tả/trạng thái |
|---|---|
| `event_id`, `event_type`, `starts_at`, `ends_at`, `geometry` | Ngữ cảnh sự kiện; cần nguồn lịch chính thức, địa điểm và thời gian. Event không chứng minh nhu cầu gọi xe. |
| `incident_id`, `incident_type`, `reported_at`, `geometry` | Tai nạn/đóng đường/điều tiết giao thông nếu provider công bố API và quyền dùng. |
| `available_vehicle_count` | Mật độ/đếm xe nếu nền tảng/nguồn hợp pháp cung cấp; hiện chưa có. |
| `booking_rate`, `destination_distribution`, `trip_value_vnd` | Tín hiệu booking/điểm đến/giá cần dữ liệu được cấp phép hoặc nhật ký tự nguyện đã ẩn danh; không suy từ traffic/POI. |
