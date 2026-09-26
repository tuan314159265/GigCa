# RULES — quy tắc làm việc GigCa

Các quy tắc này điều chỉnh cách bốn role phối hợp. Nếu thay đổi contract hoặc quy tắc chung, cập nhật tài liệu liên quan cùng lúc và thông báo cho các role bị ảnh hưởng.

## 1. Quyền sở hữu theo role

- **Data:** sở hữu `data/` và `scripts/`; chịu trách nhiệm nguồn, giấy phép, thời điểm, phạm vi phủ, đơn vị đo, chuẩn hóa và phiên bản snapshot.
- **Decision model:** sở hữu `engine/` và cấu hình mô hình trong `config/`; nhận dữ liệu theo schema đã thống nhất, trả điểm/tín hiệu kèm giải thích và giả định.
- **Backend:** sở hữu `api/`; là lớp tích hợp giữa data, engine và frontend. Không tự đổi ý nghĩa trường trong contract.
- **Frontend:** sở hữu `web/`; đọc contract đã công bố, thể hiện trạng thái dữ liệu và giải thích mà backend cung cấp. Không tự suy diễn xác suất nhu cầu/cuốc.
- `contracts/` và các tài liệu API/schema là giao diện chung. Mọi role đề xuất thay đổi; người phụ trách contract cập nhật và báo các role liên quan trước khi merge.

## 2. Dữ liệu và giới hạn suy luận

- Không commit API key, token, `.env`, dữ liệu định danh tài xế/khách, lịch sử chuyến cá nhân hoặc dữ liệu không có quyền sử dụng.
- Mỗi bộ dữ liệu phải ghi nguồn, giấy phép/điều kiện sử dụng, vùng phủ, đơn vị, thời điểm thu thập/cập nhật và cách xử lý thiếu dữ liệu.
- Dữ liệu demo/fixture phải được gắn nhãn `demo`; không trình bày dữ liệu giả lập như dữ liệu trực tiếp.
- Không khẳng định dữ liệu Grab/Xanh SM, mật độ xe, nhu cầu đặt cuốc, giá cuốc hoặc sự kiện có sẵn nếu chưa xác nhận API/quyền truy cập.
- Mật độ đường đông quanh các node/edge chỉ là tín hiệu giao thông. Không dùng tỷ lệ edge đông để tuyên bố xác suất khách sẽ đặt chuyến qua edge đó nếu không có dữ liệu hành trình/booking phù hợp.
- Mô hình định tuyến phải mô tả rõ đồ thị, trọng số/cost, thời điểm giao thông và mục đích tối ưu. Thuật toán đường đi ngắn nhất chỉ tìm tuyến theo cost đã cho; không tự tạo ra xác suất nhu cầu.
- Nếu thiếu tín hiệu, trả `unknown`/cảnh báo hoặc giảm độ tin cậy; không âm thầm thay bằng giá trị chắc chắn.

## 3. Hợp đồng giữa các module

- Schema/API là nguồn sự thật cho tên trường, kiểu, đơn vị, nullability và ý nghĩa.
- Thay đổi phá vỡ tương thích cần tăng phiên bản API/schema và cập nhật ví dụ trong `contracts/` cùng tài liệu.
- Mọi điểm số phải có tên, chiều tốt/xấu, thang đo và giải thích. Không gộp điểm thành “tốt nhất” nếu không công bố trọng số/giả định.
- Frontend phải hiển thị `data_as_of`, cảnh báo nguồn/độ phủ và lý do gợi ý khi các trường này có trong response.

## 4. Git và đặt tên

- Nhánh chính: `main`; nhánh tích hợp: `dev`; nhánh công việc: `feat/<ten-ngan>`, `fix/<ten-ngan>`, `docs/<ten-ngan>`.
- Commit theo dạng `[feat] ...`, `[fix] ...`, `[docs] ...`, `[refactor] ...`, `[chore] ...`.
- Python dùng `snake_case`; class Python và React component dùng `PascalCase`; biến/hàm TypeScript dùng `camelCase`; hằng số cấu hình dùng `UPPER_SNAKE_CASE`.
- Tên file Python dùng `snake_case.py`; component React dùng `PascalCase.tsx`; biến môi trường chỉ ghi tên trong `.env.example`, không ghi giá trị bí mật.
- Không đưa dữ liệu lớn, sinh tự động, cache, build output, hoặc secret vào Git. Dữ liệu được phép lưu phải nhỏ, có nguồn và phục vụ fixture/tái lập.

## 5. Thay đổi và review

- PR cần nêu role/module bị ảnh hưởng, thay đổi contract (nếu có), nguồn dữ liệu mới (nếu có), giới hạn đã biết và cách kiểm tra thủ công.
- Không merge thay đổi làm lệch API/schema giữa backend và frontend.
- Quyết định còn mở được ghi vào `docs/04_PLAN_DESIGN.md` hoặc issue/biên bản phù hợp; tránh biến giả định thành yêu cầu đã chốt.

