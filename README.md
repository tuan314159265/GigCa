# GigCa

Dashboard chính nằm trong **web/**. Backend chạy **python -m api.v1_server** từ root repo. Xem [hướng dẫn chạy chung](docs/REPOSITORY_GUIDE.md). `api/provider_proxy.py` giữ proxy provider; Data Explorer cũ nằm trong `docs/legacy-data-explorer/`.

GigCa hỗ trợ tài xế chọn khu vực nên chờ hoặc nghỉ dựa trên mạng lưới đường, dữ liệu thời tiết và các nguồn dữ liệu được kiểm chứng. Kết quả là gợi ý có giải thích, không phải cam kết về cuốc xe hay thu nhập.

## Bốn role

| Role | Thư mục chính | Phạm vi |
|---|---|---|
| Data | `data/`, `scripts/` | Thu thập, chuẩn hóa, kiểm tra nguồn và phiên bản dữ liệu đường, thời tiết, POI/sự kiện nếu có nguồn phù hợp. |
| Decision model | `engine/`, `config/` | Tạo ứng viên, tính chi phí/tín hiệu trên đồ thị đường, xếp hạng và giải thích gợi ý. |
| Backend | `api/`, `contracts/` | API, xác thực đầu vào, nạp snapshot và trả kết quả theo contract chung. |
| Frontend | `web/` | Bản đồ, tùy chọn tài xế, danh sách gợi ý và giải thích/trạng thái dữ liệu. |

Chi tiết cấu trúc, quy ước, API và schema nằm trong [`RULES.md`](RULES.md) và [`docs/`](docs/). Data có cấu hình PostGIS và migrations; kết nối live cần cấu hình môi trường. Phiên/kết quả API v1 hiện lưu SQLite cục bộ.

Luồng ETL MVP nằm trong `data/etl/`, đọc các JSON mẫu, kiểm tra, chuẩn hóa theo contract rồi ghi snapshot vào `data/processed/`. Tạo môi trường bằng `python3 -m venv .venv`, sau đó chạy `.venv/bin/python -m data.etl.pipeline`. Xem [`data/etl/README.md`](data/etl/README.md); trạng thái kiểm tra API và thứ tự nguồn/backup theo từng dataset nằm trong [`data/etl/config/source_registry.json`](data/etl/config/source_registry.json).

Frontend chính dùng Next.js trong `web/`. Proxy TomTom được chuyển sang `api/provider_proxy.py`; chạy chung bằng `python -m api.v1_server`. Data Explorer cũ được giữ trong `docs/legacy-data-explorer/` để tham khảo.

Data dictionary và hướng dẫn bàn giao cho Decision Engine nằm trong [`data/README.md`](data/README.md); tài liệu giải thích chi tiết kiến trúc và code Decision Engine nằm trong [`engine/README.md`](engine/README.md); contract draft ở [`contracts/engine_input.schema.json`](contracts/engine_input.schema.json). Danh sách nguồn chờ kiểm chứng nằm trong `docs/05_DATA_SOURCES_TO_VERIFY.md`. Có thể tạo/cập nhật JSON mẫu bằng `python3 scripts/fetch_sample_data.py`; mục lục file mẫu ở [`data/samples/README.md`](data/samples/README.md).

## Bắt đầu

Repo hiện là bộ khung phối hợp; các ứng dụng chưa được scaffold. Khi chọn phiên bản runtime và lệnh chạy, cập nhật hướng dẫn tại [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

## Nguyên tắc sản phẩm

- Bốn hướng gợi ý: tối đa giá trị/cuốc (chỉ khi có dữ liệu đủ tin cậy), giữ vị trí tốt, gợi ý điểm dừng/nghỉ khi chạy rông, và an toàn/đỡ mệt.
- Dùng mật độ xe, thời tiết, tình trạng đường và sự kiện chỉ khi nguồn có phạm vi, thời điểm cập nhật và quyền sử dụng rõ ràng.
- Tỷ lệ đoạn đường đông quanh một vị trí không được diễn giải thành xác suất khách đặt cuốc đi qua đoạn đó.
- Luôn hiển thị thời điểm dữ liệu, nguồn, mức tin cậy, giả định và lý do loại trừ.

## Docker cho frontend và backend

Chạy `docker compose -f compose.app.yaml up --build -d` từ thư mục repo, rồi mở http://127.0.0.1:3000/dashboard/gigca. Hướng dẫn cấu hình live/preview và lưu dữ liệu: [docs/DOCKER_RUN.md](docs/DOCKER_RUN.md). `compose.yaml` hiện có vẫn dành cho PostGIS.

## Build phiên bản tích hợp v1.0

Hướng dẫn mới được bổ sung tại [docs/BUILD_V1.md](docs/BUILD_V1.md), gồm Docker Compose, build frontend, chạy backend và phạm vi kiểm chứng. Trang chính: `/dashboard/gigca`.
