# Snapshot mẫu đã crawl

File JSON: [`hcmc_demo_snapshot.json`](hcmc_demo_snapshot.json)

Tạo/cập nhật bằng:

```bash
python3 scripts/fetch_sample_data.py
```

Mặc định script lấy forecast theo giờ của Open-Meteo và các POI OSM trong bán kính 1 km quanh tọa độ trung tâm demo tại TP.HCM. Có thể đổi tọa độ/bán kính qua `--lat`, `--lon`, `--radius-m`; xem `python3 scripts/fetch_sample_data.py --help`.

JSON lưu `generated_at`, vị trí/phạm vi, nguồn, attribution/license, thời gian dự báo và các trường chuẩn hóa. Đây chỉ là snapshot hẹp để kiểm tra luồng data/schema; không phải phủ toàn thành phố, không xác nhận POI được dừng/đỗ, không phải traffic realtime và không thể hiện xác suất/giá trị cuốc. Dữ liệu thay đổi theo thời gian.

## Attribution và điều kiện nguồn

- Weather forecast: [Open-Meteo](https://open-meteo.com/), dữ liệu CC BY 4.0 cần attribution. Free API hiện dành cho non-commercial use theo [terms](https://open-meteo.com/en/terms); xác nhận gói phù hợp trước khi dùng thương mại.
- POI: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), dữ liệu theo ODbL. Tôn trọng attribution, điều kiện share-alike áp dụng cho database dẫn xuất và giới hạn của public Overpass instance.
- Lưu URL docs, thời điểm thu thập và giới hạn trong chính JSON để giữ provenance.
