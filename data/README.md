# GigCa data

## Luồng hiện tại

- live_collector.py: TomTom/Open-Meteo quanh GPS, nguồn và trạng thái thiếu dữ liệu.
- engine_bridge.py, engine_interface.py: chuẩn hóa sang [contract](../contracts/engine_input.schema.json).
- driver_log_import.py: kiểm tra và nhập nhật ký người dùng; templates ở driver_input/.
- samples/: fixture nhỏ cho kiểm thử/ETL, không phải dữ liệu nhu cầu live.
- raw/, processed/: dữ liệu máy cá nhân, không commit.
- db/, etl/: PostGIS/ETL tùy chọn, không thay SQLite tài khoản của web app.

Nhật ký/tài khoản riêng ở SQLite volume, không dùng dataset mô phỏng làm lịch sử tài xế.
Dataset nghiên cứu được đóng gói riêng tại [artifacts/research](../artifacts/research/README.md).

## Nguồn

TomTom cho tìm kiếm/POI/routing/traffic; Open-Meteo cho dự báo; camera thành phố là catalog/snapshot tùy chọn.
OSM và các sample OSRM/Overpass là nguồn fixture hoặc basemap fallback, không chứng minh routing xe máy
hay toàn tuyến thông thoáng. Fetch thành công không xác nhận quyền phân phối lại hoặc độ phủ production.

Thời tiết hourly theo quy ước trong config/engine_config.json. Không suy ra lượng mưa tức thời/ngập từ một
giá trị giờ. Các hệ số mưa/traffic/POI là tham số thiết kế, chưa hiệu chỉnh bằng nhật ký thật.

## Công cụ

~~~powershell
python scripts/fetch_public_cameras.py
python -m data.etl.pipeline
~~~

ETL mặc định đọc sample offline. Cách dùng hạ tầng riêng: [database](db/README.md), [ETL](etl/README.md).
API key, raw provider responses, dữ liệu cá nhân và snapshot camera không đưa vào Git.
