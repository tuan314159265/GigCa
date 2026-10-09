# Dữ liệu và cách sử dụng

Thư mục này chuẩn hóa dữ liệu đầu vào cho luồng gợi ý vị trí. Snapshot dùng chung theo [contract v0.1](../contracts/engine_input.schema.json); ví dụ đã chuẩn hóa nằm ở [`samples/engine_input/hcmc_demo_snapshot.json`](samples/engine_input/hcmc_demo_snapshot.json). Dữ liệu hiện là mẫu quanh một điểm ở TP.HCM, chưa đại diện toàn thành phố.

## Khởi chạy cơ sở dữ liệu

Repo đã có cấu hình PostgreSQL + PostGIS tại [`compose.yaml`](../compose.yaml). Từ thư mục gốc repo, với Fish:

```fish
python3 -m venv .venv
.venv/bin/python -m pip install -r data/db/requirements.txt
set -gx POSTGRES_PASSWORD 'mat-khau-cuc-bo'
docker compose up -d postgis
set -gx GIGCA_DATABASE_URL "postgresql://gigca:$POSTGRES_PASSWORD@localhost:5432/gigca"
.venv/bin/python -m data.db.migrate
.venv/bin/python -m data.db.load_samples
```

Với Bash/Zsh, thay hai lệnh `set -gx` bằng:

```sh
export POSTGRES_PASSWORD='mat-khau-cuc-bo'
export GIGCA_DATABASE_URL="postgresql://gigca:${POSTGRES_PASSWORD}@localhost:5432/gigca"
```

Mật khẩu chỉ dùng ở máy local, không commit vào repo. Database được giữ trong Docker volume `gigca_postgis_data`. Hướng dẫn bảng, xuất snapshot và chính sách lưu/xóa lịch sử nằm trong [`db/README.md`](db/README.md).

## Lấy dữ liệu đã chuẩn hóa

Sau khi database đã khởi tạo, có thể lấy snapshot theo `area_id`:

```python
from data.engine_interface import EngineDataInterface

source = EngineDataInterface.from_env()  # đọc GIGCA_DATABASE_URL
snapshot = source.get_engine_input(
    "hcmc_demo_point_01",
    rain_tolerance_level="medium",  # low, medium, high; có thể bỏ qua
    forecast_hours=48,
)
```

`snapshot` là Python `dict` theo contract v0.1, có thể chuyển thành JSON hoặc đưa cho adapter của Engine. Interface chỉ đọc dữ liệu đã lưu trong DB; nó không tự gọi nhà cung cấp, tính điểm hay tạo dữ liệu nhu cầu. Có thể xuất cùng cấu trúc ra file để xem thủ công:

```sh
.venv/bin/python -m data.db.export_snapshot \
  --area-id hcmc_demo_point_01 \
  --output data/processed/db_engine_input_snapshot.json
```

## Các trường hiện có

| Trường | Nội dung | Cách hiểu |
|---|---|---|
| `areas[].representative_point` | Tọa độ đại diện và `spatial_scope` của vùng | Sample hiện là `point_sample`, không phải lưới phủ thành phố. |
| `areas[].weather.hourly[]` | `valid_time`, xác suất mưa (%) và lượng mưa (mm) | Dự báo theo giờ tại một vị trí lưới của provider; giá trị thiếu là `null`. |
| `areas[].poi_counts_by_category` | Số POI theo nhóm | Phụ thuộc phạm vi và độ phủ OSM; không phải số cuốc/nhu cầu. |
| `areas[].poi_density_grid.cells[]` | Ô lưới, số quán cafe, mật độ/km², số quán trong 500 m và hình học ô | Sample lưới 250 m chỉ phủ vùng demo. |
| `areas[].waiting_location_candidates[]` | Tọa độ và loại địa điểm có thể cân nhắc chờ | Chỉ là ứng viên chưa xác minh; `permission_to_wait` là `unknown`. |
| `areas[].routing_samples[]` | Profile, khoảng cách và thời gian tuyến mẫu | Profile `driving` chưa được xác nhận phù hợp xe máy, không phải traffic trực tiếp. |
| `traffic[]` | Segment giao thông, tốc độ hiện tại/tự do và `observed_at` | Có thể thiếu hoặc chỉ phủ một phần; segment chưa chắc đã khớp cạnh đường trong graph. |
| `data_status[]` | Tình trạng từng nhóm: `available`, `partial`, `missing`, `stale`, `not_integrated` | Luôn kiểm tra trước khi dùng; thiếu dữ liệu không đồng nghĩa giá trị bằng 0. |
| `objective_readiness[]` | Mức sẵn sàng của bốn hướng gợi ý | Cho biết dữ liệu có đủ để đánh giá mục tiêu hay chưa, không phải điểm xếp hạng. |
| `driver_preferences` | Tùy chọn được truyền vào, hiện có mức chịu mưa | Đây là input lựa chọn, không phải dữ liệu quan sát. |

Contract là nguồn chuẩn về tên trường, kiểu và cấu trúc lồng nhau. JSON mẫu là nguồn tham khảo về giá trị cụ thể. Fixture mô phỏng đầy đủ tại [`fixtures/hcmc_full_simulated_snapshot.json`](fixtures/hcmc_full_simulated_snapshot.json) chỉ dùng cho demo/test logic; không nạp lẫn với dữ liệu provider vào DB.

## Cập nhật dữ liệu

- Sample đã lưu: `.venv/bin/python -m data.etl.pipeline` tạo JSON offline; `python -m data.db.load_samples` nạp các sample đã kiểm tra vào DB.
- Dự báo mưa: `.venv/bin/python -m data.etl.refresh_weather --area-id hcmc_demo_point_01` lấy và lưu một forecast vintage. Job chưa được cài lịch tự chạy; lịch chạy thuộc môi trường triển khai.
- Traffic: dashboard lấy khi cần; nếu DB được cấu hình, lần fetch từ provider sẽ lưu observation đã chuẩn hóa. Đây là polling theo request, không phải stream liên tục.

## Các nhóm dữ liệu còn thiếu hoặc chỉ có một phần

`missing` nghĩa là chưa có dữ liệu được kiểm chứng cho phạm vi cần dùng, không phải giá trị đo bằng 0. Các tên bên dưới mô tả dữ liệu có thể cần bổ sung; chúng chưa mặc nhiên là trường của contract v0.1.

| Nhóm | Trường dự kiến | Hiện trạng và cách dùng |
|---|---|---|
| Mạng đường | `edges[].{edge_id, from_node, to_node, length_m, one_way, access_modes, road_class, barrier}` | Chưa bàn giao graph đường trong snapshot. OSM/Overpass và OSRM là các hướng dữ liệu đã xem xét; OSRM hiện chỉ có route samples theo cặp điểm, profile `driving`, không đủ để khẳng định routing xe máy hoặc phân tích mọi nhánh đường. |
| Traffic theo đoạn | `current_speed_kmh`, `free_flow_speed_kmh`, `congestion_level`, `incident_type`, `closure`, `observed_at` | Có thể có observation TomTom Flow khi được fetch; dữ liệu là tốc độ của segment provider và có giới hạn vùng phủ, chưa map-match vào graph. Engine tính tỷ số tốc độ và congestion index liên tục; không dùng tỷ lệ đường đông lân cận làm xác suất khách đi qua đoạn đó. Incident được lưu nhưng chưa bàn giao trong contract Engine hiện tại. |
| Điểm chờ/nghỉ | `candidate_id`, `source_provider`, `poi_type`, `candidate_status`, `permission_to_wait`, `verification_needed`, `area_m2` | OSM candidates đã có trong một phần sample; đều là ứng viên chưa xác minh quyền vào/dừng/đỗ. TomTom Search bổ sung local-only ở `data/raw/tomtom_search/`; chỉ dùng sau khi kiểm tra điều khoản lưu/chia sẻ. |
| POI và mật độ theo ô | `poi_count_by_category`, `cell_id`, `cell_size_m`, `cafe_poi_count`, `cafe_density_per_km2`, `cafe_poi_count_within_500m`, `geometry` | Cafe grid 250 m hiện có cho vùng mẫu, dựng từ OSM. Đây là mật độ địa điểm bản đồ để mô tả bối cảnh/tìm điểm chờ, không phải booking rate hay xác suất có cuốc. |
| Sự kiện | `event_id`, `event_type`, `venue_location`, `starts_at`, `ends_at`, `expected_attendance` | Chưa có nguồn đã kiểm chứng. Nếu bổ sung, chỉ dùng làm ngữ cảnh địa điểm/thời gian; không tự suy ra lượng cuốc hoặc doanh thu. |
| Nguồn cung xe | `available_vehicle_count`, `vehicle_density`, `observed_at` | Chưa có feed được cấp phép/xác nhận. Không có API Grab/Xanh SM đã xác nhận để đưa vào snapshot. |
| Booking và điểm trả | `booking_rate`, `request_count`, `dropoff_count`, `favorable_dropoff_pct`, `avg_next_wait_min` | KHÔNG dùng: số tổng hợp do sàn định nghĩa, không kiểm chứng được; engine xóa các trường này. Thời gian chờ được tính từ đợt chờ (`wait_spells`) do chính tài xế ghi. |
| Giá trị chuyến | `net_value_vnd`, `gross_fare_vnd`, `avg_duration_min`, `avg_trip_distance_km`, `long_trip_rate_pct` | KHÔNG dùng ở cấp thị trường. Thay bằng `driver_profile` (biểu cước a + b·km, xăng, mục tiêu đ/giờ), `trip_log` và `wait_spells` do chính tài xế cung cấp; cự ly/tốc độ theo vùng tính từ nhật ký. |
| Ngữ cảnh phiên tài xế | `origin`, `idle_duration_min`, `horizon_min`, `max_reposition_km`, `rain_tolerance_level`, `goal_weights` | Là input theo phiên/cài đặt tài xế truyền vào lúc gọi Engine, không phải dữ liệu API hay snapshot nguồn. Hiện snapshot có thể kèm `rain_tolerance_level`; các trường ngữ cảnh còn lại thuộc input runtime. |

Chi tiết nhà cung cấp và điều cần kiểm chứng xem tại [`docs/05_DATA_SOURCES_TO_VERIFY.md`](../docs/05_DATA_SOURCES_TO_VERIFY.md); mẫu OSM cafe grid xem tại [`samples/osm_poi_grid_hcmc.json`](samples/osm_poi_grid_hcmc.json). Việc fetch API thành công tại một thời điểm không xác nhận coverage, quyền sử dụng hay độ phù hợp production.

## Engine đang tính gì từ các trường này

Engine có thể chạy công thức khi được đưa dữ liệu đầy đủ, nhưng database/contract Data hiện tại chưa cấp fare hay booking. Vì vậy hai hướng đầu chỉ chạy bằng dữ liệu do chính tài xế cung cấp (biểu cước, nhật ký chuyến, đợt chờ); không có thì trả `insufficient_data`. Fixture mô phỏng chứa dữ liệu của MỘT tài xế giả lập (sinh bởi `scripts/make_demo_driver_log.py`), không chứa dữ liệu thị trường.

| Hướng | Đầu vào và phép tính trong Engine | Trạng thái với dữ liệu Data hiện tại |
|---|---|---|
| `max_trip_value` — tối đa giá trị/cuốc | Biểu cước a + b·km (fit từ nhật ký hoặc tài xế nhập), xăng c, cự ly/tốc độ/chờ theo vùng từ nhật ký: yield = [a + (b − c)·d̄ − c·r] / [d̄/v + r/v_rep + w/60]. Dịch chuyển r là ước tính đường chim bay × hệ số. | `partial`/độ tin cậy thấp khi tài xế có ≥ 20 chuyến; không có nhật ký thì `insufficient_data` (chỉ có bảng what-if). |
| `maintain_position` — giữ vị trí tốt | `100·P(chờ ≤ 10 phút) − 1.5 × chờ kỳ vọng − 2.0 × reposition_km` (0–100); P và chờ kỳ vọng từ survival trên đợt chờ của tài xế (offline/đổi chỗ là bị kiểm duyệt). Hệ số tạm, chưa hiệu chỉnh. | `partial`/thấp khi có ≥ 20 đợt chờ; nếu không `insufficient_data`. |
| `rest_spot` — gợi ý điểm chờ/nghỉ | Dùng POI phù hợp, routing distance/time từ vị trí tài xế, giờ mở cửa nếu có và thời gian rảnh. Xếp fit theo thời gian đi + độ phù hợp loại địa điểm; ứng viên không có route phù hợp sẽ bị loại, không thay bằng Haversine. | `partial`: có thể đưa ứng viên chưa xác minh ra xem xét; sample hiện không xác nhận quyền dừng/đỗ, giờ mở cửa hay suitability cho xe máy. |
| `safety_comfort` — an toàn, đỡ mệt | So dự báo xác suất/lượng mưa với `rain_tolerance_level`; traffic dùng tốc độ hiện tại so với tốc độ free-flow, lọc observation quá 30 phút, tạo congestion index/nhãn segment. Không tính mật độ xe và không định tuyến tránh kẹt. | `partial`: mưa là forecast theo vùng/giờ mẫu; traffic có thể thiếu hoặc chỉ có một vài segment. Chưa có gió, nhiệt, UV để đánh giá thời tiết ngoài mưa; tín hiệu mệt (nếu dùng) đến từ ngữ cảnh phiên tài xế như thời gian rảnh, không suy ra từ thời tiết. |

Các ngưỡng mưa, hệ số phạt, mốc phân loại traffic và cấu hình điểm nghỉ là tham số hiện có của Engine, chưa phải hiệu chỉnh từ dữ liệu vận hành TP.HCM. Xem [đặc tả đầu vào và giới hạn](../engine/spec.md), [công thức/biến cấu hình](../engine/FORMULAS_AND_DATA.md), [danh sách cấu hình Engine](../engine/UPGRADE_V2.md) và contract JSON để biết chính xác phiên bản được dùng.

## Cách đọc trạng thái

- `data_status` mô tả tình trạng từng nguồn; `partial` phải được hiểu theo phạm vi trong `reason`, còn `stale`, `missing` và `not_integrated` không được dùng như số 0.
- `objective_readiness` là cổng trước khi xếp hạng: `max_trip_value` và `maintain_position` thiếu dữ liệu cốt lõi; `rest_spot` là `partial` khi chỉ có ứng viên chưa xác minh; `safety_comfort` là `partial` khi còn ít nhất một feed mưa/traffic dùng được, nếu không sẽ thiếu dữ liệu.
- `position_score`, `yield_vnd_per_hour`, `fit_score`, rain flags và congestion index là kết quả Engine, không phải trường crawl từ nhà cung cấp. Trong đó các giá trị của hai scorer đầu chỉ có ý nghĩa khi đầu vào cần thiết có thật; fixture mô phỏng phải giữ nhãn mô phỏng.
- Bốn hướng là bốn góc nhìn độc lập, không gộp thành một điểm chung. Tài xế vẫn là người quyết định cuối cùng.

Chi tiết pipeline và trạng thái kiểm tra API xem tại [`etl/README.md`](etl/README.md). Lịch chạy job chưa được cài trong repo; cấu hình lịch thuộc môi trường triển khai.
