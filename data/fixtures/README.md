# Fixtures

Thư mục này hiện **không chứa dữ liệu mô phỏng**. Bộ `hcmc_full_simulated_snapshot.json` (thời tiết/POI/giao thông mô phỏng + nhật ký chuyến của một tài xế giả lập) đã bị gỡ: không giải thích được nguồn khi trình bày.

- Dữ liệu chạy thật: snapshot ETL từ Open-Meteo / OSM / OSRM ở `data/samples/engine_input/hcmc_demo_snapshot.json` (`demo` ở đây là *điểm mẫu* quanh một vị trí TP.HCM, không phải dữ liệu giả).
- Biểu cước: bảng giá công bố trong `config/engine_config.json` (`tariff`, kèm `source`).
- Dữ liệu của tài xế: chỉ nhật ký THẬT, nhập bằng `data/driver_log_import.py` theo mẫu trong `data/driver_input/`, lưu ở `data/raw/` (git-ignore).
- Đầu vào kiểm thử của engine (đặt tay để kiểm từng nhánh logic) nằm ở `engine/tests/fixtures/`, gắn nhãn `_test_only`, không được code chạy thật hay database nạp.

Chỉ thêm fixture nhỏ có nguồn/giấy phép rõ ràng. Không đưa dữ liệu cá nhân hoặc dữ liệu chưa xác nhận quyền sử dụng vào đây.
