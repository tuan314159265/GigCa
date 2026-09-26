# Data catalog và bàn giao cho Decision Engine

Tài liệu này là mục lục chung giữa role Data và Decision Engine. Cột **JSON mẫu** trỏ trực tiếp đến file để người nhận không phải dò ở tài liệu khác. JSON mẫu là dữ liệu đã lấy/chuẩn hóa cho thử nghiệm, không khẳng định nguồn đã được kiểm chứng đầy đủ.

## Quy ước bàn giao

- Data role lấy dữ liệu nguồn, giữ provenance, chuẩn hóa tên trường/đơn vị và đánh dấu vùng phủ/thời điểm.
- Engine đọc các trường chuẩn hóa trong [`samples/engine_input/hcmc_demo_snapshot.json`](samples/engine_input/hcmc_demo_snapshot.json), không phụ thuộc tên field riêng của provider. Contract draft: [`../contracts/engine_input.schema.json`](../contracts/engine_input.schema.json).
- JSON theo nguồn trong bảng giúp truy lại dữ liệu đã lấy; JSON engine input là ví dụ cấu trúc chung sau chuẩn hóa.
- Khi chưa có dữ liệu, để `null` hoặc ghi rõ trạng thái thiếu; không tự gán 0. Mỗi feed cần `valid_time`/`observed_at` và thời điểm tạo snapshot.
- Mẫu hiện tại lấy quanh **một tọa độ demo**, chưa phải lưới khu vực. Chưa dùng như input khuyến nghị thật cho TP.HCM.

## Biến dữ liệu đầu vào

| Tên biến chuẩn | Kiểu / đơn vị | Phạm vi / thời gian | Nguồn và chuẩn hóa | Decision Engine dùng vào đâu | Dữ liệu thiếu / giới hạn | JSON mẫu |
|---|---|---|---|---|---|---|
| `weather.hourly[].valid_time` | ISO 8601 datetime | Từng giờ dự báo tại điểm/provider grid | Open-Meteo `hourly.time`; giữ timezone provider | Ghép tín hiệu thời tiết cùng khung giờ ra quyết định | Không dùng giờ thiếu hoặc ngoài horizon | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].precipitation_probability_pct` | number, `%` hoặc null | Từng giờ; hiện là forecast quanh một tọa độ | Open-Meteo `precipitation_probability`; chuẩn hóa thành phần trăm | Tín hiệu mưa cho hướng **An toàn & đỡ mệt**; Engine quyết định cách tổng hợp/ngưỡng | Null nếu provider không trả; grid provider có thể lệch điểm hỏi; chưa đại diện từng ô | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].precipitation_mm` | number, mm hoặc null | Lượng precipitation trong khoảng thời gian provider mô tả | Open-Meteo `precipitation`; kiểm tra unit và khoảng tích lũy | Bổ sung tín hiệu mưa, phân biệt lượng mưa với xác suất mưa | Thiếu khác với 0 mm; giá trị forecast, không phải đo tại từng đoạn đường | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].apparent_temperature_c` | number, °C hoặc null | Từng giờ | Open-Meteo `apparent_temperature` | Tín hiệu nóng/lạnh cảm nhận cho hướng an toàn/đỡ mệt | Null nếu thiếu; không tự gọi là chỉ số sức khỏe/an toàn | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].shortwave_radiation_w_m2` | number, W/m² hoặc null | Từng giờ; radiation theo khung thời gian provider | Open-Meteo `shortwave_radiation` | Proxy phơi nắng ban ngày, cần Engine xác định cách dùng | Không đồng nghĩa với UV index hoặc nhiệt độ mặt đường | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].wind_speed_10m_kmh`, `wind_gusts_10m_kmh` | number, km/h hoặc null | Từng giờ; gió ở cao độ chuẩn provider | Open-Meteo `wind_speed_10m`, `wind_gusts_10m` | Tín hiệu thời tiết bổ sung cho hướng an toàn/đỡ mệt | Giữ null nếu thiếu; quan trắc/dự báo ở 10 m không phải gió chính xác tại người lái | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `areas[].poi_counts_by_category` | map category → integer | Một bán kính truy vấn quanh sample point | OSM/Overpass tags; đếm theo nhóm tag chuẩn hóa | Đặc trưng bối cảnh khu vực hoặc tìm điểm chờ/nghỉ; không phải số cuốc | POI thiếu không đồng nghĩa không có địa điểm; count chưa chia diện tích ô thật | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [POI source sample](samples/osm_overpass_pois_hcmc.json) |
| `areas[].routing_samples[].route_distance_m` | number, m | Một cặp điểm origin-destination | OSRM route response `distance`; đổi về mét | Ước lượng chạy rỗng/khả năng tiếp cận trong ví dụ | Mẫu profile `driving`, chưa xác nhận routing xe máy | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [OSRM source sample](samples/osrm_route_hcmc.json) |
| `areas[].routing_samples[].route_duration_s` | number, s | Một cặp điểm origin-destination | OSRM route response `duration`; đổi về giây | Ước lượng thời gian tiếp cận | Không phải live traffic hoặc thời gian chạy xe máy đã kiểm chứng | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [OSRM source sample](samples/osrm_route_hcmc.json) |
| `traffic[].current_speed_kmh`, `free_flow_speed_kmh`, `observed_at` | number, km/h; ISO 8601 | Theo directed road edge và thời điểm quan sát | Chờ chọn Goong/TomTom/nguồn địa phương; chưa có adapter | Có thể mô tả phơi nhiễm giao thông/chi phí tuyến | Chưa có JSON; không thay bằng tỷ lệ cạnh đông hoặc thời gian routing thường | Chưa có sample |

## Biến do Engine tính — chưa phải dữ liệu crawl

Các tên dưới đây chỉ để phân biệt đầu vào với kết quả mô hình; chưa phải contract đã chốt. Công thức, trọng số, ngưỡng và output cần được role Engine đề xuất riêng.

| Biến kết quả đề xuất | Đầu vào liên quan | Ý nghĩa dự kiến | Trạng thái |
|---|---|---|---|
| `weather_exposure` | Xác suất/lượng mưa, nhiệt cảm nhận, bức xạ, gió giật | Mức phơi nhiễm thời tiết của một phương án theo horizon | Chưa có công thức/ngưỡng; Engine đề xuất |
| `route_access_cost` | Quãng đường/thời gian tới vị trí và traffic nếu có | Công sức chạy rỗng để tới ứng viên | Cần profile xe máy và cách tính thống nhất |
| `poi_density_by_category` | POI counts + polygon/diện tích ô | Mật độ POI theo nhóm trong một ô hợp lệ | Sample hiện chưa có polygon/diện tích ô; chưa tính density |
| `position_score` | Dữ liệu hành trình/điểm trả khách hoặc proxy được duyệt | Khả năng giữ vị trí thuận lợi sau chuyến | Chưa có booking/drop-off data; không suy từ POI/traffic |
| `trip_value_score` | Fare/trip data hợp pháp và đủ tin cậy | Xếp hạng hướng tối đa giá trị/cuốc | Chưa có nguồn; không được tạo từ proxy POI |

## Chưa có nguồn/sample

TomTom, OpenWeather, Goong, cổng Giao thông TP.HCM, sự kiện, mật độ xe/booking và giá cuốc chưa có JSON sample. Xem danh sách kiểm chứng nguồn tại [`../docs/05_DATA_SOURCES_TO_VERIFY.md`](../docs/05_DATA_SOURCES_TO_VERIFY.md). Chỉ thêm file sau khi lấy được dữ liệu thật, lưu provenance và kiểm tra quyền sử dụng.
