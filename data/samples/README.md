# Snapshot mẫu đã crawl

Các JSON được tách theo nguồn để xem response từng phần; file tổng hợp vẫn giữ để thử tích hợp.

| File | Nội dung |
|---|---|
| [`open_meteo_weather_hcmc.json`](open_meteo_weather_hcmc.json) | Forecast lượng mưa và xác suất mưa theo giờ từ Open-Meteo, kèm đơn vị, attribution và vị trí grid provider trả về. |
| [`osm_overpass_pois_hcmc.json`](osm_overpass_pois_hcmc.json) | POI OpenStreetMap trong bán kính mẫu, kèm tags và provenance. |
| [`osm_poi_spatial_hcmc.json`](osm_poi_spatial_hcmc.json) | Cafe và POI ứng viên đã phân loại từ tags OSM sample; giữ ID, tag, role, nguồn và cách ước lượng tọa độ. |
| [`osm_poi_grid_hcmc.json`](osm_poi_grid_hcmc.json) | 32 ô vuông 250 m nằm trọn trong vùng POI sample; có số cafe trong ô, mật độ/km² và số cafe trong 500 m quanh tâm ô. |
| [`osm_waiting_candidates_hcmc.json`](osm_waiting_candidates_hcmc.json) | Candidate có tag OSM như bãi đỗ, mall, cây xăng/điểm nghỉ; trạng thái đều `unverified_candidate`, quyền chờ `unknown`. |
| [`osrm_route_hcmc.json`](osrm_route_hcmc.json) | Một route OSRM với profile `driving`, chỉ để xem schema/API. |
| [`osrm_waiting_candidate_routes_hcmc.json`](osrm_waiting_candidate_routes_hcmc.json) | Ma trận distance/duration OSRM từ điểm demo tới 54 candidate IDs; profile `driving`, không xác minh xe máy hoặc quyền dừng. |
| [`engine_input/hcmc_demo_snapshot.json`](engine_input/hcmc_demo_snapshot.json) | Weather, POI, route, lưới cafe và 54 OSM waiting candidates đã chuẩn hóa cho Decision Engine; có `data_status`, phạm vi một điểm demo và chưa phải coverage TP.HCM. Không gồm TomTom Search local-only. |
| [`hcmc_demo_snapshot.json`](hcmc_demo_snapshot.json) | Weather + POI đã chuẩn hóa trong một snapshot để thử trao đổi giữa Data/Engine/Backend. |

Tạo/cập nhật bằng:

```bash
python3 scripts/fetch_sample_data.py
```

Tính lưới và OSM candidates từ POI JSON hiện có (offline):

```bash
python3 scripts/fetch_poi_spatial_data.py --input-json data/samples/osm_overpass_pois_hcmc.json --cell-size-m 250
```

Lấy lại vùng POI mở rộng từ Overpass rồi tính lưới 500 m:

```bash
python3 scripts/fetch_poi_spatial_data.py --extent-m 1500 --cell-size-m 500
```

Lệnh online dùng bbox vuông 3 × 3 km quanh tâm demo và cần Overpass hoạt động. Lần thử gần nhất bị HTTP 504/timeout; sample hiện tại vẫn được giữ nguyên. Khi endpoint hoạt động, truy vấn lấy cafe, parking, school, place of worship, mall, park, rest area và các landuse mở; chỉ polygon open land từ 2.500 m² mới được giữ làm ứng viên `open_land`.

TomTom Search đã trả dữ liệu ứng viên parking/school/church/mall trong lần thử trước, nhưng điều khoản lưu trữ/chia sẻ theo account plan chưa được xác nhận. JSON được giữ local trong `data/raw/tomtom_search/` (Git bỏ qua). Chạy `python3 scripts/fetch_tomtom_waiting_candidates.py` để lấy lại; không đưa dữ liệu này vào file chia sẻ nếu chưa kiểm tra terms.

Chạy ETL offline trên ba JSON theo nguồn:

```bash
.venv/bin/python -m data.etl.pipeline
```

Để đưa sample TomTom local vào ETL sau khi đã kiểm tra điều khoản account, thêm `--include-local-tomtom-candidates`. Đầu ra chứa dữ liệu TomTom không nên commit/chia sẻ khi chưa xác nhận quyền lưu trữ.

Để chỉ cập nhật forecast thời tiết qua Open-Meteo client (cache/retry), tạo `.venv`, cài `.venv/bin/python -m pip install -r data/etl/requirements.txt`, rồi chạy `.venv/bin/python -m data.etl.pipeline --refresh-weather`. Xem [ETL README](../etl/README.md) để biết tình trạng kiểm chứng từng API; Overpass hiện có thể quá tải nên ETL mặc định dùng sample đã lưu.

Mặc định script cũ lấy forecast theo giờ, POI OSM trong bán kính 1 km, và một route OSRM `driving`. Script `fetch_poi_spatial_data.py` tạo lưới cafe và danh sách địa điểm ứng viên; chạy ETL offline sau đó để thêm hai nhóm vào Engine input nếu các sample tương ứng tồn tại.

Mỗi JSON lưu `generated_at`, vị trí/phạm vi, nguồn, attribution/license và giới hạn. Grid dùng phép chiếu cục bộ xấp xỉ theo mét ở vĩ độ tâm HCMC; phù hợp demo nhỏ, không dùng làm khảo sát chính xác. Mật độ cafe không phải xác suất khách đặt cuốc. Candidate parking/school/church/mall/open land không chứng minh được quyền vào hoặc chờ; mọi candidate cần xác minh giờ mở cửa, tiếp cận xe máy, quyền chờ và điểm vào cụ thể trước khi gợi ý vận hành. TomTom Search sample ghi rõ loại query, số lượng trả về và category bị chạm trần; không hiểu danh sách là đầy đủ.

OSRM Table có thể làm mới bằng `.venv/bin/python scripts/fetch_osrm_waiting_candidate_routes.py`. Lệnh tạo một request ma trận duy nhất tới public demo server, không dùng fallback đường chim bay. Server là best-effort, không dùng làm dịch vụ production; route `driving` không đại diện tuyến xe máy đã xác minh.

## Attribution và điều kiện nguồn

- Weather forecast: [Open-Meteo](https://open-meteo.com/), dữ liệu CC BY 4.0 cần attribution. Free API hiện dành cho non-commercial use theo [terms](https://open-meteo.com/en/terms); xác nhận gói phù hợp trước khi dùng thương mại.
- POI: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), dữ liệu theo ODbL. Tôn trọng attribution, điều kiện share-alike áp dụng cho database dẫn xuất và giới hạn của public Overpass instance.
- Lưu URL docs, thời điểm thu thập và giới hạn trong chính JSON để giữ provenance.
