# Đồng bộ nhánh tích hợp — 14/10/2026

Nhánh đích: `feat/gigca-integrated-v1`. Engine, data, config và contract được đồng bộ từ `feat/data-engine-traffic-integration`, commit `4320a69`.

- `web/`: dashboard Next.js hiện có, giữ giao diện và các thay đổi local tìm địa điểm, mô tả input, chọn hướng.
- `api/`: backend dashboard/session hiện có; giữ proxy và collector live, trả thêm các trường mới từ engine.
- `engine/`: engine cá nhân hóa, ML, phân tích đánh đổi và test từ nhánh data.
- `data/`: pipeline, PostGIS, bridge, mẫu nhập và importer nhật ký tài xế.
- `config/`, `contracts/`: cấu hình và hợp đồng dữ liệu dùng chung.

## Chạy backend sau đồng bộ

Từ thư mục gốc repo, dùng môi trường Python riêng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api/requirements.txt
.\.venv\Scripts\python.exe -m api.v1_server
```

Docker backend nay cài cả dependency database và engine/ML:

```powershell
docker compose -f compose.app.yaml up --build
```

Kiểm thử riêng từng thư mục (không cần provider key):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s engine/tests -v
.\.venv\Scripts\python.exe -m unittest discover -s api/tests -v
```

## Phạm vi

Không thêm provider mới, không cấu hình key và không thu thập/train dữ liệu ML thực trong lần đồng bộ này. Không đưa `.env`, cache, dữ liệu cá nhân hoặc node_modules lên Git.

Fixture mô phỏng cũ đã bỏ theo engine mới. API mặc định dùng snapshot nguồn mẫu; tên mode `simulation` cũ vẫn được nhận để tương thích, nhưng nạp cùng snapshot nguồn mẫu và có cảnh báo. Hai hướng thu nhập/vị trí có thể chưa có đề xuất khi thiếu lịch sử thật. Không dùng fixture unit test làm dữ liệu demo sản phẩm.

Các vấn đề đã nhận diện nhưng chưa xử lý trong lần đồng bộ: missing-rain trong ML, điều kiện xác nhận khoảng thu nhập, contract lịch sử tài xế, routing origin và ghép traffic vào tuyến. Dashboard giữ giao diện hiện có; các trường phân tích mới chưa được xây màn hình riêng.
