# Snapshot mẫu đã crawl

Các JSON được tách theo nguồn để xem response từng phần; file tổng hợp vẫn giữ để thử tích hợp.

| File | Nội dung |
|---|---|
| [`open_meteo_weather_hcmc.json`](open_meteo_weather_hcmc.json) | Forecast lượng mưa và xác suất mưa theo giờ từ Open-Meteo, kèm đơn vị, attribution và vị trí grid provider trả về. |
| [`osm_overpass_pois_hcmc.json`](osm_overpass_pois_hcmc.json) | POI OpenStreetMap trong bán kính mẫu, kèm tags và provenance. |
| [`osrm_route_hcmc.json`](osrm_route_hcmc.json) | Một route OSRM với profile `driving`, chỉ để xem schema/API. |
| [`engine_input/hcmc_demo_snapshot.json`](engine_input/hcmc_demo_snapshot.json) | Dữ liệu ba nguồn đã chuẩn hóa thành bản input draft cho Decision Engine; có `data_status` cho cả nhóm đã có và chưa có data, một sample point chứ chưa phải các ô khu vực thật. |
| [`hcmc_demo_snapshot.json`](hcmc_demo_snapshot.json) | Weather + POI đã chuẩn hóa trong một snapshot để thử trao đổi giữa Data/Engine/Backend. |

Tạo/cập nhật bằng:

```bash
python3 scripts/fetch_sample_data.py
```

Chạy ETL offline trên ba JSON theo nguồn:

```bash
.venv/bin/python -m etl.pipeline
```

Để chỉ cập nhật forecast thời tiết qua Open-Meteo client (cache/retry), tạo `.venv`, cài `.venv/bin/python -m pip install -r etl/requirements.txt`, rồi chạy `.venv/bin/python -m etl.pipeline --refresh-weather`. Xem [ETL README](../../etl/README.md) để biết tình trạng kiểm chứng từng API; Overpass hiện có thể quá tải nên ETL mặc định dùng sample đã lưu.

Mặc định script lấy forecast xác suất/lượng mưa theo giờ từ Open-Meteo, POI OSM trong bán kính 1 km, và một route OSRM `driving` giữa hai điểm demo ở TP.HCM. Script tạo từng file theo nguồn, engine-input sample và snapshot kết hợp. Có thể đổi tâm/bán kính qua `--lat`, `--lon`, `--radius-m`; xem `python3 scripts/fetch_sample_data.py --help`.

Mỗi JSON lưu `generated_at`, vị trí/phạm vi, nguồn, attribution/license, thời gian dự báo và giới hạn. Đây chỉ là sample để kiểm tra luồng data/schema; không phải phủ toàn thành phố, không xác nhận POI được dừng/đỗ, route `driving` không xác nhận tuyến xe máy, không phải traffic realtime và không thể hiện xác suất/giá trị cuốc. Dữ liệu thay đổi theo thời gian.

## Attribution và điều kiện nguồn

- Weather forecast: [Open-Meteo](https://open-meteo.com/), dữ liệu CC BY 4.0 cần attribution. Free API hiện dành cho non-commercial use theo [terms](https://open-meteo.com/en/terms); xác nhận gói phù hợp trước khi dùng thương mại.
- POI: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), dữ liệu theo ODbL. Tôn trọng attribution, điều kiện share-alike áp dụng cho database dẫn xuất và giới hạn của public Overpass instance.
- Lưu URL docs, thời điểm thu thập và giới hạn trong chính JSON để giữ provenance.
