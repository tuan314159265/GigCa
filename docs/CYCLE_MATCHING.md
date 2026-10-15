# Ghép chu kỳ chờ và chuyến — conservative v1

Giữ nguyên started_at là thời điểm đón khách. API/schema hiện không có liên kết
nhận cuốc–chuyến đã xác thực, nên tất cả cặp được ghép mang trạng thái inferred,
không tự coi ID giống nhau hoặc nhật ký synthetic là liên kết tin cậy.

build_cycles nhận lịch sử của MỘT tài xế; backend chịu trách nhiệm phân quyền và
tách tài xế trước khi gọi. Hàm không suy luận danh tính từ tiền tố ID.

Điều kiện: ended_by=trip; kết thúc chờ không muộn hơn started_at, cách tối đa
300 giây; khoảng cách Haversine đến điểm đón không quá 500 m. Chỉ ghép nếu duy nhất
theo cả hai chiều: một chuyến–một đợt chờ. Không greedy chọn ứng viên gần nhất.
ID trùng hoặc bản ghi không hợp lệ không được dùng. Không sửa hay xóa lịch sử.

Trạng thái: inferred / ambiguous / unmatched / invalid. confirmed luôn bằng 0
cho tới khi nguồn cung cấp liên kết xác thực và contract được bổ sung.
Ngoài ngưỡng không có nghĩa dữ liệu sai: cuốc đón xa/lâu vẫn được giữ trong lịch sử.
Routing chưa dùng làm bằng chứng ghép; đường đi khả thi không chứng minh cùng cuốc.

API thêm ml_insights.cycle_yield.matching với policy, ngưỡng và counts; không trả
chi tiết ID qua trường này. CLI train-base lưu matching.json chi tiết theo tài xế,
report.json có tóm tắt. Đây là trường bổ sung, không đổi schema bản ghi hiện hữu.

Nhãn năng suất hiện vẫn là (net - fuel_paid_leg)/(wait + paid_duration), không
tính chặng đi đón; tập chu kỳ thiên về cuốc đón gần. Chưa gọi đó là thu nhập cả ca.
Không sửa trọng số cũ; cần người dùng chủ động train một phiên bản mới để so sánh.
