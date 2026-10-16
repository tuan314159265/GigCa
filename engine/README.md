# GigCa decision engine

Python engine nhận [contract JSON](../contracts/engine_input.schema.json), đánh giá bốn hướng độc lập,
trả kết quả có cấu trúc. Tham số ở [engine_config.json](../config/engine_config.json).
Dashboard inference qua api/main_model.py; không train mỗi request.

## Cơ chế dashboard

- Cuốc giá trị cao: trung vị năng suất chu kỳ Quantile Gradient Boosting cao nhất.
- Giữ vị trí: clip(P(có cuốc trong 10 phút)% − 1,5 × phút chờ − 2 × km chuyển vùng, 0, 100).
- Chờ: discrete Logistic Hazard, bin 2 phút; restricted mean 30 phút, chưa điều kiện hóa thời gian đã chờ.
- Năng suất: (tiền sau phí nền tảng − nhiên liệu chuyến) / (giờ chờ + giờ có khách).
  Chưa đủ đi đón/chuyển vùng; không phải giá cuốc tiếp theo.
- P10/P50/P90 và split conformal; model hiện được đánh giá trên mô phỏng.
- Features: thời điểm, cuối tuần, tọa độ tương đối, mưa; POI/traffic chưa được học.

Live lấy điểm đến API, giữ neo để kiểm tra support. POI–thời điểm chỉ phân biệt gần hòa:
thu nhập trong 1% baseline, bonus tối đa 0,5%; giữ vị trí trong 1 điểm, bonus tối đa ±0,5 điểm.
Không sửa dự báo ML. Policy ở config/poi_time_policy.json, các hệ số là giả thuyết thủ công.

Nghỉ ngơi yêu cầu routing hợp lệ, xét xác minh/thời gian tới/loại điểm.
Né mưa/traffic dùng dữ liệu có nguồn, không có routing tối ưu tránh ngập.
Các mục tiêu khác đơn vị, không cộng thành một score chung.

## Khoảng cách và dữ liệu thiếu

Chuyển vùng là đường chim bay nhân detour; routing thật hiển thị sau có thể khác.
POI live cụ thể dùng arrival radius bằng 0; catalog vùng cũ giữ quy tắc 500 m là đã ở trong vùng.
Thiếu nguồn phải trả lý do, không bịa giao thông thông thoáng hay nhu cầu khách.

Các module personal/community/bandit phục vụ thí nghiệm riêng; dashboard chưa cá nhân hóa theo lịch sử.
Không đưa nhật ký synthetic vào tài khoản thật.

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s engine/tests -q
~~~

Model, dataset và cách chạy: [README chính](../README.md).
