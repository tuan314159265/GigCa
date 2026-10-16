# Synthetic research pipeline

Dữ liệu mô phỏng, không phải người thật hay dự báo nhu cầu TP.HCM. LLM hỗ trợ tạo personas;
Python sinh chuỗi ca/chờ/chuyến/tiền theo ràng buộc. Không nhập output vào database tài khoản.

## Bộ đã đóng gói

Từ root chạy python scripts/restore_release.py. Dataset ở
.cache/synthetic/hcmc-expanded-32/contextual-seed7; model ở .cache/models/logistic-hazard-quantile-gb-hcmc.

32 tài xế / 16 nhóm, 120 ngày, 47 neo. Prompt/phản hồi API được chấp nhận, provenance,
lịch ca, coverage và checksum giữ trong archive. Không kèm các lần thử bị loại hay dataset trung gian.

## Train lại

Python 3.12, dependency đúng phiên bản artifact:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m experiments.synthetic train-base .cache/synthetic/hcmc-expanded-32/contextual-seed7 --output .cache/models/retrained-v1 --plots
~~~

Dùng output mới, không ghi đè model chính. Lệnh train không cần API.
Chi tiết split/output/biểu đồ: [TRAIN_BASE.md](TRAIN_BASE.md).

## Sinh bộ nhỏ tham chiếu

~~~powershell
python -m experiments.synthetic generate --drivers 12 --days 42 --world contextual --seed 7 --output .cache/synthetic/reference-v1
~~~

Đây là reference design xác định, không phải đã gọi LLM. Muốn personas API mới dùng cohort:

~~~powershell
python -m experiments.synthetic.cohort --help
python -m experiments.synthetic.expanded_dataset --help
python -m experiments.synthetic prompt --count 12 --output .cache/synthetic/persona-prompt.json
~~~

Chọn provider/model/key hợp lệ tại máy; đọc tùy chọn và kế hoạch trước khi gọi dịch vụ có phí.
Giữ personas đã được chấp nhận để tái lập; không kỳ vọng output LLM bit-for-bit qua các runtime khác.

## Đánh giá

Chia theo tài xế/thời gian: train, validation, calibration, test. Không trộn ngẫu nhiên từng dòng.
Ghép chờ–chuyến bảo thủ, duy nhất hai chiều, tối đa 5 phút/500 m. Nhãn chưa đủ chi phí đi đón/chuyển vùng.
Test mô phỏng: MAE ~21.508 đồng/giờ; coverage ~79,36% cho khoảng danh nghĩa 80%.
Không suy ra độ chính xác/tăng thu nhập thực tế.

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s experiments/synthetic/tests -q
~~~

## Địa lý và điều kiện nguồn

TP.HCM trước sáp nhập, không Dĩ An. GADM 4.1 dùng kiểm tra biên, không phân phối polygon trong repo.
Nguồn: https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VNM_1.json.zip
Điều kiện: https://gadm.org/license.html (academic/non-commercial; không mặc định có quyền phân phối lại).
Tọa độ neo TomTom có điều kiện provider riêng. Chạy/train bộ đã xuất không cần tải polygon.

Neo là miền hỗ trợ dữ liệu mô phỏng, không phải chỗ đỗ đã xác minh. API live không làm mô hình
tự động có dữ liệu thật hoặc phủ liên tục toàn thành phố.
