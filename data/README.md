# Data catalog

## Quy ước

- Data role lấy dữ liệu nguồn, giữ provenance, chuẩn hóa tên trường/đơn vị và đánh dấu vùng phủ/thời điểm.
- Engine đọc các trường chuẩn hóa trong [`samples/engine_input/hcmc_demo_snapshot.json`](samples/engine_input/hcmc_demo_snapshot.json), không phụ thuộc tên field riêng của provider. Contract draft: [`../contracts/engine_input.schema.json`](../contracts/engine_input.schema.json).
- JSON theo nguồn trong bảng giúp truy lại dữ liệu đã lấy; JSON engine input là ví dụ cấu trúc chung sau chuẩn hóa.
- Khi chưa có dữ liệu, để `null` hoặc ghi rõ trạng thái thiếu; không tự gán 0. Mỗi feed cần `valid_time`/`observed_at` và thời điểm tạo snapshot.
- `data_status` trong engine input cho biết từng nhóm dữ liệu đang `available`, `partial`, `missing`, `stale` hay `not_integrated`; Engine phải dùng status này để bỏ qua/giảm phạm vi mục tiêu, không hiểu thiếu dữ liệu thành giá trị bằng 0.
- Mẫu hiện tại lấy quanh **một tọa độ demo**, chưa phải lưới khu vực. Chưa dùng như input khuyến nghị thật cho TP.HCM.

## Database và bàn giao Engine

MVP dùng PostgreSQL + PostGIS với schema theo grain và ETL run FK. Xem [hướng dẫn database](db/README.md) và [thiết kế chi tiết](../docs/07_DATABASE_DESIGN.md). Module import cho Engine là [`data.engine_interface.EngineDataInterface`](engine_interface.py); hàm `get_engine_input(area_id)` trả snapshot theo `contracts/engine_input.schema.json` v0.1. Adapter đọc dữ liệu đã nạp trong DB, không tự gọi API. Traffic được xuất thành `traffic[]` theo `TrafficEdge` của Engine; incident chưa có parser/scorer nên vẫn `not_integrated`.

Nhánh Engine parse POI từ `pois[]` cấp snapshot, trong khi contract Data để ứng viên điểm chờ trong từng `areas[].waiting_location_candidates[]`. Dùng [`data.engine_bridge.load_for_engine(snapshot)`](engine_bridge.py) để chuyển snapshot sang `EngineInput`; bridge giữ mọi điểm là chưa xác minh và không bịa fare/booking. Engine đã nhận `traffic[]` ở cấp snapshot; `EngineDataInterface` truy vấn traffic DB và xuất đúng `TrafficEdge`. Bridge cũng có thể nhận `traffic_edges` nếu caller cần chuyển trực tiếp một observation runtime.

### Kết quả nối thử với `origin/engine` (05/10/2026)

Đã fetch `origin/engine` (`1d2a987`) nhưng giữ nguyên branch Data hiện tại; mã Engine được checkout tạm trong `/tmp` để chạy adapter, không merge đè thay đổi của hai nhóm. Nối snapshot ETL qua `data.engine_bridge` cho kết quả:

| Dữ liệu vào | Kết quả nối | Ý nghĩa / giới hạn |
|---|---:|---|
| Open-Meteo forecast | 48 giờ, 1 vị trí mẫu | Engine đọc được dự báo mưa; chưa đại diện toàn khu vực. |
| Ứng viên chờ OSM | 54 | Được đưa qua adapter như POI chưa xác minh; không khẳng định được phép dừng/chờ. |
| Tuyến OSRM đến ứng viên | 54/54 có route | Chỉ profile `driving`, không xác nhận xe máy hoặc traffic trực tiếp. OSRM Table trả thời gian/quãng đường trên tuyến tối ưu theo profile, không phải xác suất khách đặt cuốc. |
| TomTom Flow | 1 segment thử runtime | Tốc độ 16 km/h so với free-flow 26 km/h; Engine đánh dấu traffic `partial`. Segment gần tọa độ truy vấn, chưa map-matched vào graph và không đại diện cả vùng. |
| Kết quả mục tiêu | `max_trip_value=insufficient_data`; `maintain_position=insufficient_data`; `rest_spot=partial`; `safety_comfort=partial` | Rest spot chỉ là danh sách ứng viên; safety hiện đọc mưa và một segment giao thông. |

TomTom Flow Segment API trả tốc độ hiện tại/tự do cho đoạn gần điểm truy vấn; TomTom khuyến nghị Orbis Traffic cho tích hợp mới. OSRM public demo là best-effort, không nên dùng làm phụ thuộc production. Xem [TomTom Flow Segment docs](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data), [TomTom Traffic API introduction](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/product-information/introduction), [OSRM Table API](https://project-osrm.org/docs/v26.4.0/http#table-service) và [OSRM demo usage policy](https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy).

**Còn thiếu cho Engine:** fare/giá trị chuyến; lịch sử booking và phân bố điểm đến; traffic coverage trên graph tuyến thay vì một segment; incident gắn cạnh đường; xác minh quyền dừng/giờ mở cửa của POI. `vehicle_density` và event cũng chưa có nguồn feed đã xác nhận. POI count, cafe density, tỷ lệ đường chậm và dữ liệu thời tiết không thay được booking/fare nên không được dùng để giả lập hai mục tiêu đầu.

Engine branch hiện có fixture `data/fixtures/hcmc_full_simulated_snapshot.json` để chạy demo đủ bốn mục tiêu; fixture tự ghi nhãn **mô phỏng** và các fare/booking/địa điểm bên trong không phải dữ liệu thật. Dùng fixture đó cho demo logic, còn snapshot Data ở trên để chứng minh cách Engine phản ứng khi dữ liệu thật còn thiếu. Không trộn hai bộ thành một snapshot.

Đã nạp sample vào PostgreSQL/PostGIS và kiểm tra đường bàn giao thật qua `EngineDataInterface.get_engine_input("hcmc_demo_point_01")` → snapshot v0.1 → Engine adapter. Engine nhận 28 giờ forecast còn trong horizon tại thời điểm truy vấn, 54 POI ứng viên, 32 ô mật độ cafe và 54 route; readiness là `insufficient_data`, `insufficient_data`, `partial`, `partial` theo thứ tự bốn mục tiêu. Interface lọc giờ đã qua và giới hạn forecast theo horizon yêu cầu. Traffic được truy vấn từ DB theo vùng; nếu có thì xuất segment gần nhất trong 24 giờ, đánh dấu `partial` nếu còn quan sát trong 30 phút và để Engine lọc freshness. DB sample hiện chưa có traffic observation nên output là `traffic=[]`, status `missing`.

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
| `traffic[].edge_id`, `current_speed_kmh`, `free_flow_speed_kmh`, `observed_at` | string, number km/h, ISO 8601 | Một segment gần khu vực, tối đa 24 giờ gần nhất; Engine chỉ dùng quan sát ≤30 phút | `traffic_flow_observation`: `openlr`/geometry tạo ID ổn định; `current_speed_kph` → `current_speed_kmh`; `fetched_at` → `observed_at` | Engine phân loại tỷ số tốc độ hiện tại/tốc độ tự do và báo traffic sample | Luôn `partial` khi có dữ liệu vì chưa map-match/phủ graph tuyến; Engine không nhận confidence/geometry qua `TrafficEdge`. Tốc độ không phải mật độ xe hoặc tốc độ xe máy đảm bảo | [Local-only flow response](raw/tomtom/) |
| `traffic_incident_observations[].category`, `magnitude_of_delay`, `delay_s`, `geom`, `fetched_at` | enum/integer, seconds, geometry, ISO 8601 | Một incident được trả trong một lần hỏi bbox | TomTom Incident Details; mỗi response là snapshot danh sách sự cố hiện diện trong bbox | Cảnh báo sự cố, kẹt xe, công trình/đóng đường theo vị trí | Incident không bao phủ mọi đoạn đường đang chậm; không thấy incident không có nghĩa đường thông | [Local-only incident response](raw/tomtom/) |

## Các nhóm dữ liệu cần tính đến dù hiện chưa có nguồn

Các trường này được liệt kê để Engine thiết kế nhánh thiếu dữ liệu ngay từ đầu. `missing` nghĩa là chưa có dữ liệu được kiểm chứng, không có nghĩa giá trị đo bằng 0.

| Nhóm | Tên biến dự kiến | Mô tả / hướng sử dụng | Nguồn cần kiểm chứng | Trạng thái hiện tại |
|---|---|---|---|---|
| Mạng đường | `edges[].edge_id`, `from_node`, `to_node`, `length_m`, `one_way`, `access_modes`, `road_class`, `barrier` | Đồ thị có hướng và hạn chế tiếp cận; nền tảng để định tuyến xe máy và tính tuyến ứng viên. | OSM/Overpass hoặc Goong; cần QA đường cấm, cầu, hầm, sông và lối vào | Chưa có graph/snapshot cạnh; route OSRM đơn lẻ chỉ là sample |
| Điều kiện theo đoạn đường | `current_speed_kmh`, `free_flow_speed_kmh`, `congestion_level`, `incident_type`, `closure`, `observed_at` | Traffic, tai nạn, thi công/đóng đường gắn vào edge và thời điểm; dùng tính chi phí/phơi nhiễm tuyến. | TomTom, cổng Giao thông TP.HCM, Goong nếu API có | `missing`; không suy từ tỷ lệ đường đông xung quanh |
| Ứng viên điểm chờ | `candidate_id`, `source_provider`, `poi_type`, `candidate_status`, `permission_to_wait`, `verification_needed`, `area_m2` | Ứng viên từ OSM/TomTom: bãi đỗ, mall, trường, nhà thờ/nơi thờ tự, công viên/khoảng đất, cây xăng, điểm nghỉ. Mọi kết quả dùng `unverified_candidate`, `permission_to_wait=unknown` cho tới khi xác minh quyền vào/chờ và vị trí chính xác. | [OSM candidate sample](samples/osm_waiting_candidates_hcmc.json); TomTom local-only ở `data/raw/tomtom_search/`; kiểm tra thực địa/chủ địa điểm | TomTom Search trả 60 parking, 100 school, 29 church, 100 mall; school/mall chạm giới hạn 100. Không địa điểm nào xác minh quyền chờ; open-land polygon chưa có sample do Overpass timeout |
| Mật độ quán cafe theo ô | `cell_id`, `cell_size_m`, `cafe_poi_count`, `cafe_density_per_km2`, `cafe_poi_count_within_500m`, `geometry` | Đếm cafe rơi trong ô và trong bán kính 500 m quanh tâm ô; mô tả bối cảnh thương mại, không phải lượng cầu chuyến xe. Số đếm lân cận là `null` nếu coverage nguồn không phủ đủ 500 m. | OSM/Overpass; gán POI vào lưới cục bộ kích thước mét | [Lưới mẫu 250 m](samples/osm_poi_grid_hcmc.json): 32 ô phủ trọn vùng mẫu hình tròn bán kính 1 km, tạo từ POI OSM crawl ngày 2026-09-26; không phải phủ TP.HCM |
| POI theo khu vực | `poi_count_by_category`, `area_area_km2`, `poi_density_by_category` | Đếm và mật độ POI trong polygon/ô; đặc trưng bối cảnh, không phải lượng cầu chuyến xe. | OSM/Overpass + lưới/polygon đã chốt | Cafe density đã có trong sample lưới; các lớp POI khác vẫn phụ thuộc vùng crawl và độ đầy đủ OSM |
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
| `cafe_density_per_km2` | Cafe POI count / diện tích ô | Mật độ cafe theo ô; trường neighborhood `cafe_poi_count_within_500m` là số quán trong bán kính 500 m quanh tâm ô | Có sample 250 m; nguồn gốc OSM sample cũ, 32 ô nằm trọn trong vùng coverage |
| `waiting_location_candidates[]` | OSM tags + tọa độ OSM/centroid | Gợi ý nơi cần xem xét: bãi đỗ, nhà thờ/nơi thờ tự, trường, trung tâm thương mại, công viên/khoảng đất rộng, cây xăng, điểm nghỉ/chờ | OSM sample hiện có một phần loại địa điểm; extractor hỗ trợ thêm school/church/open land khi truy vấn mới thành công. TomTom bổ sung local-only ứng viên parking/school/church/mall; ETL chỉ nhập khi bật cờ. Tọa độ way/area có thể là tâm xấp xỉ |
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

Goong, OpenWeather, cổng Giao thông TP.HCM, sự kiện, mật độ xe/booking và giá cuốc chưa có sample. Lần thử lấy POI mở rộng từ Overpass ngày 2026-10-02 trả 504/timeout, nên grid hiện tại được tính từ sample OSM đã lưu ngày 2026-09-26. TomTom Search trả 289 ứng viên (school/mall chạm giới hạn), được giữ local-only trong `data/raw/tomtom_search/` vì quyền cache/chia sẻ chưa xác minh. Cờ `--include-local-tomtom-candidates` thêm chúng vào ETL cục bộ; đừng chia sẻ snapshot đó trước khi kiểm tra terms. TomTom Traffic JSON cũng local-only trong `data/raw/tomtom/`. Xem [`../docs/05_DATA_SOURCES_TO_VERIFY.md`](../docs/05_DATA_SOURCES_TO_VERIFY.md) để biết tình trạng nguồn.
