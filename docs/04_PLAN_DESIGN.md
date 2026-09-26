# Plan and design notes

## Product directions discussed

1. **Tối đa giá trị/cuốc:** đi xa hơn một chút để vào khu có cuốc dài/giá tốt hơn thay vì quay vòng nhiều cuốc ngắn. Giá/cuốc và dữ liệu booking hiện chưa có nguồn được xác nhận; giữ đây là hướng mục tiêu/giả thuyết, chưa dùng để chấm điểm vận hành.
2. **Giữ vị trí tốt:** ưu tiên vị trí mà sau khi trả khách tài xế vẫn có cơ hội ở khu thuận lợi; tránh bị đẩy xa. Cần dữ liệu phù hợp để ước lượng vị trí kế tiếp, không thay bằng tỷ lệ đường đông.
3. **Gợi ý điểm dừng/nghỉ khi chạy rông:** đề xuất điểm chờ hoặc nghỉ phù hợp khi tài xế chưa nhận cuốc trong một khoảng thời gian; định nghĩa khoảng thời gian và nguồn POI cần chốt.
4. **An toàn và đỡ mệt:** xét mưa, nắng/nhiệt cảm nhận, gió, kẹt xe và các điều kiện có nguồn dữ liệu tin cậy. Các ngưỡng cần do người dùng/nhóm sản phẩm xác nhận.

## Đồ thị mạng đường

Biểu diễn bản đồ đường thành đồ thị: giao lộ/điểm nối là node, đoạn đường có hướng là edge. Edge có thể mang khoảng cách, thời gian đi ước tính, điều kiện giao thông theo thời điểm và các cost đã được định nghĩa. Các thuật toán như Dijkstra có thể tìm đường ít cost nhất trên đồ thị; Bellman–Ford phù hợp với một số dạng trọng số âm nhưng không tự tính ra xác suất khách book.

Có thể tổng hợp tín hiệu giao thông trên các edge lân cận để mô tả mức thuận tiện của khu chờ hoặc chi phí di chuyển. Cách tổng hợp phải nêu rõ bán kính/thời gian/độ phủ và không gọi kết quả đó là xác suất nhận cuốc. Muốn dự báo booking cần dữ liệu booking/hành trình và kiểm định riêng.

## Điểm chờ và sự kiện

POI nghỉ/chờ và lịch sự kiện có thể được thêm làm context nếu có nguồn, quyền sử dụng, địa điểm và thời gian diễn ra rõ ràng. Event không đồng nghĩa với nhu cầu cuốc; UI cần cho tài xế biết đây là tín hiệu tham khảo và còn yếu tố nào chưa biết.

## Pipeline dự kiến

1. Data role chuẩn hóa lớp đường, quan sát giao thông/thời tiết và metadata nguồn vào snapshot có version.
2. Decision engine tạo các vị trí ứng viên, tính đặc trưng/cost theo các mục tiêu đã chốt, trả thứ hạng cùng thành phần điểm và độ phủ dữ liệu.
3. Backend kiểm tra request, chọn snapshot, gọi engine và trả kết quả theo API contract.
4. Frontend hiển thị ứng viên trên bản đồ, thời gian dữ liệu, lý do, độ tin cậy và cảnh báo.

## Cần chốt trong buổi làm việc

- Nguồn/API và quyền sử dụng cho đường, traffic, thời tiết, POI và event.
- So sánh nguồn đề xuất tại [`05_DATA_SOURCES_TO_VERIFY.md`](05_DATA_SOURCES_TO_VERIFY.md); chỉ chốt provider sau khi kiểm tra coverage TP.HCM, API/quota, giá, quyền cache/hiển thị và profile xe máy.
- Định nghĩa “chạy rông”, khu vực ứng viên, giới hạn quãng đường đến điểm chờ và tiêu chí gợi ý nghỉ.
- Cách cá nhân hóa mục tiêu an toàn/đỡ mệt; ngưỡng mưa, nhiệt, gió và kẹt xe.
- Tín hiệu nào khả dụng cho giữ vị trí tốt; nếu không có booking data thì giới hạn kết luận.
- Vai trò của mục tiêu “giá trị/cuốc” cho đến khi có dữ liệu hợp pháp, đủ tin cậy.
- Định dạng snapshot, schema/API response và cách biểu diễn độ tin cậy.
