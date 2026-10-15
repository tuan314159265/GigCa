# Logistic hazard + quantile gradient boosting

Bản được chốt trước search nằm trong `.cache/models/logistic-hazard-quantile-gb/`.
Đổi tên thư mục từ synthetic-base-v3, không huấn luyện lại hoặc đổi trọng số.

```powershell
.\.venv\Scripts\python.exe -m experiments.synthetic search-params .cache/synthetic/gigca-drivers-32-v2/contextual-seed7 --output .cache/models/logistic-hazard-quantile-gb-tuned --trials 30 --seed 7 --plots
```

Chạy tại repo GigCa. Không cần API key. Không ghi đè thư mục đã tồn tại.
Lệnh vừa search vừa fit/lưu các model được chọn, không cần chạy train-base sau đó.

Search trên train/validation giữ nguyên driver/date splits; không dùng calibration/test
để chọn tham số. Đây là single-holdout search, chưa phải nested/grouped CV nhiều fold.

- Logistic context và không context: thử C = .01, .1, .5, 1, 5 độc lập, chọn censored NLL.
  Scaler được fit trên train của từng ứng viên, không trên validation.
- Mỗi quantile: 30 cấu hình duy nhất (gồm cấu hình mặc định), thử learning_rate .02/.05/.1,
  max_depth 1/2/3, min_samples_leaf 8/20/40, subsample .7/.9/1, cùng default .06/2/8/.8.
  Fit 200 cây rồi đánh giá các mốc 40/80/120/160/200 bằng pinball loss validation.
  Không dùng validation_fraction ngẫu nhiên hoặc chia các bin của cùng wait giữa train/val.
- Sau chọn, fit lại bằng split train; calibration hiệu chỉnh khoảng, test chỉ báo cáo cuối.
  Không refit trên toàn bộ dữ liệu sau đánh giá; model lưu khớp model được đánh giá.
- Console in tiến độ, output có models.joblib, best_params.json, search_results.json,
  report.json, matching.json, splits.json và plots nếu bật.
- Tốt nhất là trong phạm vi ứng viên đã thử, không khẳng định tối ưu toàn cục.
- Gate không đạt vẫn lưu ứng viên kèm lý do, không tự bật dashboard hoặc ghi đè bản chính.
- Test đã được xem qua các thí nghiệm trước; kết quả tiếp theo là nghiên cứu phát triển,
  cần bộ kiểm tra cuối độc lập để có kết luận mạnh hơn. Tất cả vẫn là synthetic.
