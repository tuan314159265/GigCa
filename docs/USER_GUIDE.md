# User and contributor guide

Repo này hiện cung cấp cấu trúc và tài liệu phối hợp cho bốn role; chưa có lệnh khởi chạy ứng dụng vì nhóm chưa chốt scaffold/runtime và dependencies.

1. Đọc [`RULES.md`](../RULES.md) và tài liệu role trong [`00_PROJECT_STRUCTURE.md`](00_PROJECT_STRUCTURE.md).
2. Trước khi thêm nguồn, ghi provenance/điều kiện sử dụng và schema trong `docs/03_DATA_SCHEMA.md`.
3. Trước khi nối module, thống nhất request/response trong `docs/02_API_SPEC.md` và lưu ví dụ/schema trong `contracts/`.
4. Giữ secret và dữ liệu thô trong môi trường local; chỉ dùng fixture nhỏ, được phép chia sẻ trong Git.
5. Sau khi nhóm chọn công nghệ/phiên bản và lệnh chạy, cập nhật hướng dẫn cài đặt/chạy tại đây.

## Chạy và kiểm tra Decision Engine (`engine/`)

Decision Engine được triển khai bằng Python (hỗ trợ tích hợp FastAPI backend).

1. Chạy bộ kiểm tra tự động (unit tests theo Mục 9 của `engine/spec.md`):
   ```bash
   python -m pytest engine/tests
   ```

2. Chạy kịch bản kiểm tra độ phản ứng đầu vào (verification suite):
   ```bash
   python scripts/verify_engine.py
   ```

3. Chạy thử nghiệm tương tác với tham số tài xế tùy chỉnh (CLI Demo):
   ```bash
   # Chạy mặc định với dữ liệu mô phỏng Quận 1
   python scripts/run_demo.py

   # Chỉnh thời gian rảnh, mức chịu mưa, và khung giờ lập kế hoạch
   python scripts/run_demo.py --rain low --idle 45 --horizon 120

   # Chạy với file snapshot cụ thể
   python scripts/run_demo.py --snapshot data/samples/engine_input/hcmc_demo_snapshot.json
   ```


