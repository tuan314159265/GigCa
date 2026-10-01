# GigCa

GigCa hỗ trợ tài xế chọn khu vực nên chờ hoặc nghỉ dựa trên mạng lưới đường, dữ liệu thời tiết và các nguồn dữ liệu được kiểm chứng. Kết quả là gợi ý có giải thích, không phải cam kết về cuốc xe hay thu nhập.

## Bốn role

| Role | Thư mục chính | Phạm vi |
|---|---|---|
| Data | `data/`, `scripts/` | Thu thập, chuẩn hóa, kiểm tra nguồn và phiên bản dữ liệu đường, thời tiết, POI/sự kiện nếu có nguồn phù hợp. |
| Decision model | `engine/`, `config/` | Tạo ứng viên, tính chi phí/tín hiệu trên đồ thị đường, xếp hạng và giải thích gợi ý. |
| Backend | `api/`, `contracts/` | API, xác thực đầu vào, nạp snapshot và trả kết quả theo contract chung. |
| Frontend | `web/` | Bản đồ, tùy chọn tài xế, danh sách gợi ý và giải thích/trạng thái dữ liệu. |

Chi tiết cấu trúc, quy ước, API và schema nằm trong [`RULES.md`](RULES.md) và [`docs/`](docs/).

Luồng ETL MVP đọc các JSON mẫu, kiểm tra, chuẩn hóa theo contract rồi ghi snapshot vào `data/processed/`. Tạo môi trường bằng `python3 -m venv .venv`, sau đó chạy `.venv/bin/python -m etl.pipeline`. Xem [`etl/README.md`](etl/README.md); trạng thái kiểm tra API và thứ tự nguồn/backup theo từng dataset nằm trong [`etl/config/source_registry.json`](etl/config/source_registry.json).

Web Data Explorer chưa có bản đồ, đọc snapshot và JSON mẫu để xem trạng thái mưa, POI, routing và provider. Chạy `.venv/bin/python -m http.server 8000` từ thư mục gốc rồi mở `http://localhost:8000/web/`; xem thêm [`web/README.md`](web/README.md).

Data dictionary và hướng dẫn bàn giao cho Decision Engine nằm trong [`data/README.md`](data/README.md); contract draft ở [`contracts/engine_input.schema.json`](contracts/engine_input.schema.json). Danh sách nguồn chờ kiểm chứng nằm trong `docs/05_DATA_SOURCES_TO_VERIFY.md`. Có thể tạo/cập nhật JSON mẫu bằng `python3 scripts/fetch_sample_data.py`; mục lục file mẫu ở [`data/samples/README.md`](data/samples/README.md).

## Bắt đầu

Repo hiện là bộ khung phối hợp; các ứng dụng chưa được scaffold. Khi chọn phiên bản runtime và lệnh chạy, cập nhật hướng dẫn tại [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

## Nguyên tắc sản phẩm

- Bốn hướng gợi ý: tối đa giá trị/cuốc (chỉ khi có dữ liệu đủ tin cậy), giữ vị trí tốt, gợi ý điểm dừng/nghỉ khi chạy rông, và an toàn/đỡ mệt.
- Dùng mật độ xe, thời tiết, tình trạng đường và sự kiện chỉ khi nguồn có phạm vi, thời điểm cập nhật và quyền sử dụng rõ ràng.
- Tỷ lệ đoạn đường đông quanh một vị trí không được diễn giải thành xác suất khách đặt cuốc đi qua đoạn đó.
- Luôn hiển thị thời điểm dữ liệu, nguồn, mức tin cậy, giả định và lý do loại trừ.
