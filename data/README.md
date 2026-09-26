# Data catalog

## Quy ước

- Data role lấy dữ liệu nguồn, giữ provenance, chuẩn hóa tên trường/đơn vị và đánh dấu vùng phủ/thời điểm.
- Engine đọc các trường chuẩn hóa trong [`samples/engine_input/hcmc_demo_snapshot.json`](samples/engine_input/hcmc_demo_snapshot.json), không phụ thuộc tên field riêng của provider. Contract draft: [`../contracts/engine_input.schema.json`](../contracts/engine_input.schema.json).
- JSON theo nguồn trong bảng giúp truy lại dữ liệu đã lấy; JSON engine input là ví dụ cấu trúc chung sau chuẩn hóa.
- Khi chưa có dữ liệu, để `null` hoặc ghi rõ trạng thái thiếu; không tự gán 0. Mỗi feed cần `valid_time`/`observed_at` và thời điểm tạo snapshot.
- `data_status` trong engine input cho biết từng nhóm dữ liệu đang `available`, `partial`, `missing`, `stale` hay `not_integrated`; Engine phải dùng status này để bỏ qua/giảm phạm vi mục tiêu, không hiểu thiếu dữ liệu thành giá trị bằng 0.
- Mẫu hiện tại lấy quanh **một tọa độ demo**, chưa phải lưới khu vực. Chưa dùng như input khuyến nghị thật cho TP.HCM.

## Biến dữ liệu đầu vào

| Tên biến chuẩn | Kiểu / đơn vị | Phạm vi / thời gian | Nguồn và chuẩn hóa | Decision Engine dùng vào đâu | Dữ liệu thiếu / giới hạn | JSON mẫu |
|---|---|---|---|---|---|---|
| `weather.hourly[].valid_time` | ISO 8601 datetime | Từng giờ dự báo tại điểm/provider grid | Open-Meteo `hourly.time`; giữ timezone provider | Ghép tín hiệu thời tiết cùng khung giờ ra quyết định | Không dùng giờ thiếu hoặc ngoài horizon | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].precipitation_probability_pct` | number, `%` hoặc null | Từng giờ; hiện là forecast quanh một tọa độ | Open-Meteo `precipitation_probability`; chuẩn hóa thành phần trăm 0–100 | Tín hiệu dự báo khu vực/giờ có thể mưa; so sánh với mức chịu mưa tài xế chọn | Null nếu provider không trả; grid provider có thể lệch điểm hỏi; chưa đại diện từng ô. Mapping mức chịu mưa sang ngưỡng còn chờ Engine/nhóm chốt | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `weather.hourly[].precipitation_mm` | number, mm hoặc null | Lượng precipitation trong khoảng thời gian provider mô tả | Open-Meteo `precipitation`; kiểm tra unit và khoảng tích lũy | Bổ sung tín hiệu mưa, phân biệt lượng mưa với xác suất mưa | Thiếu khác với 0 mm; giá trị forecast, không phải đo tại từng đoạn đường | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [Weather source sample](samples/open_meteo_weather_hcmc.json) |
| `areas[].poi_counts_by_category` | map category → integer | Một bán kính truy vấn quanh sample point | OSM/Overpass tags; đếm theo nhóm tag chuẩn hóa | Đặc trưng bối cảnh khu vực hoặc tìm điểm chờ/nghỉ; không phải số cuốc | POI thiếu không đồng nghĩa không có địa điểm; count chưa chia diện tích ô thật | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [POI source sample](samples/osm_overpass_pois_hcmc.json) |
| `areas[].routing_samples[].profile` | string | Theo từng cặp điểm | Profile từ request routing provider | Engine biết giới hạn mode của route khi dùng | `driving` trong sample không đồng nghĩa xe máy | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [OSRM source sample](samples/osrm_route_hcmc.json) |
| `areas[].routing_samples[].route_distance_m` | number, m | Một cặp điểm origin-destination | OSRM route response `distance`; đổi về mét | Ước lượng chạy rỗng/khả năng tiếp cận trong ví dụ | Mẫu profile `driving`, chưa xác nhận routing xe máy | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [OSRM source sample](samples/osrm_route_hcmc.json) |
| `areas[].routing_samples[].route_duration_s` | number, s | Một cặp điểm origin-destination | OSRM route response `duration`; đổi về giây | Ước lượng thời gian tiếp cận | Không phải live traffic hoặc thời gian chạy xe máy đã kiểm chứng | [Engine input](samples/engine_input/hcmc_demo_snapshot.json) · [OSRM source sample](samples/osrm_route_hcmc.json) |
| `driver_preferences.rain_tolerance_level` | enum: `low`, `medium`, `high` | Mức tài xế chọn cho request/ca | Frontend/API request; không lấy từ weather provider | Cho Engine biết tài xế chấp nhận mưa đến mức nào khi so sánh probability/intensity theo khu vực và giờ | Tên mức và mapping sang ngưỡng %/mm chưa chốt; không gán thresholds ngầm | Chưa có sample request; weather/engine input sample không tự chọn preference |
| `traffic[].current_speed_kmh`, `free_flow_speed_kmh`, `observed_at` | number, km/h; ISO 8601 | Theo directed road edge và thời điểm quan sát | Chờ chọn Goong/TomTom/nguồn địa phương; chưa có adapter | Có thể mô tả phơi nhiễm giao thông/chi phí tuyến | Chưa có JSON; không thay bằng tỷ lệ cạnh đông hoặc thời gian routing thường | Chưa có sample |

## Các nhóm dữ liệu cần tính đến dù hiện chưa có nguồn

Các trường này được liệt kê để Engine thiết kế nhánh thiếu dữ liệu ngay từ đầu. `missing` nghĩa là chưa có dữ liệu được kiểm chứng, không có nghĩa giá trị đo bằng 0.

| Nhóm | Tên biến dự kiến | Mô tả / hướng sử dụng | Nguồn cần kiểm chứng | Trạng thái hiện tại |
|---|---|---|---|---|
| Mạng đường | `edges[].edge_id`, `from_node`, `to_node`, `length_m`, `one_way`, `access_modes`, `road_class`, `barrier` | Đồ thị có hướng và hạn chế tiếp cận; nền tảng để định tuyến xe máy và tính tuyến ứng viên. | OSM/Overpass hoặc Goong; cần QA đường cấm, cầu, hầm, sông và lối vào | Chưa có graph/snapshot cạnh; route OSRM đơn lẻ chỉ là sample |
| Điều kiện theo đoạn đường | `current_speed_kmh`, `free_flow_speed_kmh`, `congestion_level`, `incident_type`, `closure`, `observed_at` | Traffic, tai nạn, thi công/đóng đường gắn vào edge và thời điểm; dùng tính chi phí/phơi nhiễm tuyến. | TomTom, cổng Giao thông TP.HCM, Goong nếu API có | `missing`; không suy từ tỷ lệ đường đông xung quanh |
| Điểm chờ/nghỉ đã xác minh | `place_id`, `place_type`, `opening_hours`, `access`, `parking_allowed`, `verified_at` | Điểm nghỉ/chờ và điều kiện sử dụng. POI parking/toilet/cafe tự nó không chứng minh tài xế được dừng/đỗ. | OSM/Goong để tìm ứng viên; xác minh thực địa/đơn vị quản lý | POI mẫu có tag thô; quyền dừng/đỗ chưa xác minh (`partial`) |
| POI theo khu vực | `poi_count_by_category`, `area_area_km2`, `poi_density_by_category` | Đếm và mật độ POI trong polygon/ô; đặc trưng bối cảnh, không phải lượng cầu chuyến xe. | OSM/Overpass + lưới/polygon đã chốt | Mẫu mới đếm quanh một điểm; chưa có polygon hoặc density |
| Sự kiện | `event_id`, `event_type`, `venue_location`, `starts_at`, `ends_at`, `expected_attendance` | Ngữ cảnh hoạt động theo nơi/thời gian; không tự suy ra số cuốc hay doanh thu. | Lịch sự kiện công khai/đơn vị tổ chức, cần điều khoản và độ mới | `missing`; chưa có nguồn/API xác nhận |
| Nguồn cung xe | `available_vehicle_count`, `vehicle_density`, `observed_at` | Số lượng/mật độ xe nếu có nguồn hợp pháp; có thể ảnh hưởng cạnh tranh nhưng phải biết vùng và thời gian đo. | API được nền tảng cấp phép hoặc dữ liệu quan sát được phép dùng | `missing`; không có API Grab/Xanh SM đã xác nhận |
| Nhu cầu và điểm trả khách | `booking_rate`, `request_count`, `destination_distribution`, `dropoff_count` | Tín hiệu cuốc theo khu vực/giờ và phân bố điểm đến; cần ẩn danh, đủ đại diện và được phép sử dụng. | Nền tảng cấp phép hoặc nhật ký tự nguyện đã ẩn danh | `missing`; POI/traffic không thay thế được |
| Giá trị chuyến | `trip_fare_vnd`, `net_trip_value_vnd`, `trip_distance_m`, `service_time_s` | Giá trị/chi phí chuyến nếu có dữ liệu giá và chi phí được kiểm chứng; phục vụ mục tiêu giá trị/cuốc. | API/nhật ký có quyền sử dụng; cần định nghĩa gross/net và chi phí | `missing`; không tạo điểm giá trị từ proxy |
| Thời gian và lịch | `local_hour`, `day_of_week`, `is_public_holiday` | Ngữ cảnh giờ/ngày; giờ và thứ có thể suy ra từ timestamp, ngày lễ cần lịch đáng tin cậy. | Tính nội bộ từ `valid_time`; nguồn lịch ngày lễ nếu dùng | Giờ/ngày suy ra được; ngày lễ chưa tích hợp |
| Phiên tài xế và tùy chọn | `origin`, `idle_duration_min`, `horizon_min`, `max_reposition_km`, `goal_weights`, `avoid_conditions` | Input do tài xế nhập/chọn, không phải feed nhà cung cấp; giới hạn phương án và cá nhân hóa bốn hướng. | Frontend/API request contract | Chưa nằm trong data snapshot; Backend/Frontend sẽ bàn giao qua request |

## Biến do Engine tính — chưa phải dữ liệu crawl

Các tên dưới đây chỉ để phân biệt đầu vào với kết quả mô hình; chưa phải contract đã chốt. Công thức, trọng số, ngưỡng và output cần được role Engine đề xuất riêng.

| Biến kết quả đề xuất | Đầu vào liên quan | Ý nghĩa dự kiến | Trạng thái |
|---|---|---|---|
| `rain_exposure` | Xác suất mưa, lượng mưa và `rain_tolerance_level` | Mức mưa dự báo theo khu vực/giờ so với mức tài xế chấp nhận | Engine đề xuất cách tổng hợp/ngưỡng; chưa được hiệu chỉnh |
| `route_access_cost` | Quãng đường/thời gian tới vị trí và traffic nếu có | Công sức chạy rỗng để tới ứng viên | Cần profile xe máy và cách tính thống nhất |
| `poi_density_by_category` | POI counts + polygon/diện tích ô | Mật độ POI theo nhóm trong một ô hợp lệ | Sample hiện chưa có polygon/diện tích ô; chưa tính density |
| `position_score` | Dữ liệu hành trình/điểm trả khách hoặc proxy được duyệt | Khả năng giữ vị trí thuận lợi sau chuyến | Chưa có booking/drop-off data; không suy từ POI/traffic |
| `trip_value_score` | Fare/trip data hợp pháp và đủ tin cậy | Xếp hạng hướng tối đa giá trị/cuốc | Chưa có nguồn; không được tạo từ proxy POI |

## Mức sẵn sàng theo bốn hướng quyết định

JSON engine input có `objective_readiness` để Backend/Engine biết nên tính, giới hạn hay đánh dấu chưa đủ dữ liệu cho từng hướng. Đây là trạng thái khả dụng của bằng chứng, không phải điểm xếp hạng.

| Mục tiêu | Dữ liệu cần | Sẵn sàng với sample hiện tại | Xử lý khi thiếu |
|---|---|---|---|
| `max_trip_value` — tối đa giá trị/cuốc | Giá trị cuốc, booking/destination distribution, thời gian/chi phí chuyến | `insufficient_data` | Không xếp hạng theo giá trị/cuốc; không dùng POI hoặc traffic thay fare/request data |
| `maintain_position` — giữ vị trí tốt | Điểm trả khách/phân bố destination hoặc proxy được duyệt; routing xe máy | `insufficient_data` | Không khẳng định xác suất cuốc kế tiếp; route mẫu `driving` không đủ cho đánh giá vận hành |
| `rest_spot` — gợi ý điểm chờ/nghỉ | POI ứng viên, quyền tiếp cận/dừng đỗ, giờ mở cửa và phù hợp xe máy | `partial` | Có thể hiển thị POI như ứng viên chưa xác minh; không gọi là điểm dừng an toàn/hợp pháp |
| `safety_comfort` — an toàn, có xét mức chịu mưa | Dự báo mưa theo khu vực/giờ và mức chịu mưa; traffic/incident nếu có nguồn | `partial` | Chỉ dùng forecast mưa trong phạm vi/time hợp lệ; báo thiếu traffic/incidents; không tính mệt từ thời tiết |

**Phạm vi thời tiết hiện tại:** chỉ bàn giao xác suất mưa và lượng mưa dự báo. Nhiệt cảm nhận, nắng/bức xạ, gió và UV không nằm trong input Engine hiện tại; không tính điểm mệt từ các biến đó.

## Cách Engine xử lý thiếu dữ liệu

- Dựa vào `data_status` trước khi dùng mỗi nhóm. `available` vẫn phải kiểm tra `valid_time`/`observed_at` và phạm vi; `partial` chỉ dùng đúng phạm vi ghi trong `reason`; `missing`/`stale`/`not_integrated` thì bỏ khỏi phép tính.
- Dựa vào `objective_readiness` để không xếp hạng mục tiêu đang `insufficient_data`; `partial` phải đi kèm giới hạn/cảnh báo.
- Nếu thiếu dữ liệu cốt lõi của một hướng, trả `insufficient_data` cho hướng đó hoặc không xếp hạng hướng đó. Không tự bù bằng 0, POI, tỷ lệ cạnh đông hay một nhóm dữ liệu khác.
- Hiển thị nguồn và giới hạn để tài xế/Backend biết gợi ý nào dựa trên dữ liệu thật, dữ liệu một phần hay chưa khả dụng.

Nguồn chưa có sample gồm Goong, OpenWeather, TomTom, cổng Giao thông TP.HCM, sự kiện, mật độ xe/booking và giá cuốc. Xem [`../docs/05_DATA_SOURCES_TO_VERIFY.md`](../docs/05_DATA_SOURCES_TO_VERIFY.md); chỉ thêm sample sau khi lấy dữ liệu thật và ghi provenance/quyền sử dụng.
