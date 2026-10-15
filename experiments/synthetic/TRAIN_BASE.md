# Train model chung từ dữ liệu mô phỏng

Chạy tại thư mục repo GigCa, không cần API key hoặc server đang chạy:

```powershell
.\.venv\Scripts\python.exe -m experiments.synthetic train-base .cache/synthetic/hcmc-expanded-32/contextual-seed7 --output .cache/models/synthetic-base-v1
```

Không ghi đè output đã tồn tại: chọn v2, v3 cho thí nghiệm tiếp theo.

## Biểu đồ cho báo cáo

Để cài đầy đủ backend, train/lưu model và biểu đồ trong môi trường local:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu chỉ cần train và biểu đồ, dùng requirements riêng bên dưới.

```powershell
.\.venv\Scripts\python.exe -m pip install -r experiments/synthetic/requirements-plots.txt
.\.venv\Scripts\python.exe -m experiments.synthetic train-base .cache/synthetic/hcmc-expanded-32/contextual-seed7 --output .cache/models/synthetic-base-v2 --plots
```

`plots/` chứa PNG 200 dpi, SVG, CSV và `curves.json`:

- `wait_learning_curve`: NLL train/validation theo 20–100% số đợt chờ train.
  Đây là các lần fit độc lập trên tập con lồng nhau có seed, không phải loss theo epoch.
- `cycle_boosting_loss`: pinball loss train/validation theo từng bước boosting, cho ba quantile.
- `wait_test_calibration`: xác suất dự đoán và quan sát Kaplan–Meier trên test.
- `cycle_test_intervals`: khoảng dự đoán và giá trị quan sát trên toàn bộ chu kỳ test.

Tùy chọn này fit thêm bốn model chờ phục vụ learning curve, nên chạy lâu hơn.
Model cuối được lưu vẫn học trên toàn bộ **split train**, không phải toàn bộ dataset.
Không dùng biểu đồ test để chọn hyperparameter. Xem `plots/README.md` để diễn giải giới hạn.

## Chia dữ liệu

Với 32 tài xế / 16 type, chọn ngẫu nhiên có seed một người mỗi type để train (16 người).
16 người còn lại chia thành validation (8) và test (8), không trùng tài xế với train.
Train và validation dùng ngày train trong manifest; calibration dùng tài xế validation
trên các ngày calibration muộn hơn; test dùng 8 người riêng trên các ngày test cuối.
Không chia ngẫu nhiên từng chuyến. Các bản ghi không thuộc các tổ hợp này được bỏ qua.
Không fit lại bằng test. Không thử nhiều seed rồi chọn theo kết quả test.

Validation chọn ứng viên: hazard phải tốt hơn Kaplan–Meier và model không ngữ cảnh
theo ngưỡng engine; cycle median phải tốt hơn baseline trung bình tập train.
Calibration chỉ hiệu chỉnh khoảng thu nhập. Test báo NLL, MAE, độ phủ và độ rộng khoảng;
độ phủ danh nghĩa là 80%, không phải bảo đảm trên dữ liệu thực.

## File được lưu

- `models.joblib`: tham số logistic, scaler, ba cây ensemble quantile, conformal correction,
  tọa độ tham chiếu, cấu hình và trạng thái development gate.
- `report.json`: phiên bản thư viện, hash dữ liệu/code/artifact, seed, danh sách tài xế/ngày,
  số mẫu, kết quả validation/test và giới hạn nghiên cứu.
- `splits.json`: driver ID, spell ID, thời điểm của từng đợt chờ được dùng.
  Cycle tái dựng từ input đã hash và logic ghép của engine; không lưu bản sao lịch sử.
- `matching.json`: trạng thái ghép từng chuyến (inferred/ambiguous/unmatched/invalid).
  Ghép bảo thủ 5 phút/500 m, duy nhất hai chiều; không thay đổi dữ liệu đầu vào.

Sau khi ghi, pipeline nạp lại model và kiểm tra dự đoán trùng trước/sau serialization.
Chỉ nạp joblib do chính mình tạo hoặc nguồn tin cậy; dùng cùng phiên bản thư viện/code.

## Phạm vi

Đây là model chung **synthetic research**, chưa tự bật cho tài khoản thật hoặc nối dashboard.
Gate không đạt thì vẫn lưu ứng viên để phân tích, không coi là model đủ điều kiện chạy.
Ngay cả gate đạt, cần kiểm tra dữ liệu thật, phạm vi vị trí/thời gian và dữ liệu thiếu trước
khi dùng ngoài demo. Không thêm lịch sử giả vào tài khoản thật.

Giữ logistic survival + quantile boosting làm mốc đầu tiên; thay kiến trúc chỉ sau khi có
bằng chứng lỗi trên holdout. Ưu tiên cải thiện ghép wait→pickup→trip, biểu diễn vùng và
thiếu mưa trước. Bandit cá nhân không được gộp thành kinh nghiệm thực của tài xế mới.
