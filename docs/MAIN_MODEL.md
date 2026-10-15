# Model chính của dashboard

Model được chốt: logistic hazard + quantile gradient boosting, artifact local
`.cache/models/logistic-hazard-quantile-gb/models.joblib` (bản đã chốt trước search).
Không dùng thư mục `-tuned`. Không train theo request hoặc fallback sang model cá nhân.
Lịch sử tài khoản vẫn lưu riêng, chưa được dùng cho cá nhân hóa luồng chính.

API recommend dùng model này cho hai hướng kiếm cuốc/giữ vị trí. Sáu điểm neo từ
kịch bản mô phỏng và vị trí hiện tại là ứng viên, không phải hotspot/điểm chờ đã xác minh.
Ứng viên được lọc theo max_reposition_km (đường chim bay x detour cấu hình).
Cuốc giá trị cao được xếp theo trung vị năng suất chu kỳ, không tự suy ra giá/cuốc,
quãng đường chuyến hoặc nhu cầu thị trường. Giữ vị trí dùng xác suất chờ và phạt
chờ/dịch chuyển đã công bố trong engine config.

Đầu vào dự đoán: thời điểm snapshot, tọa độ, lượng mưa giờ hiện tại; không dùng
giao thông làm feature. Thiếu mưa được cảnh báo là 0 mm theo đặc trưng cũ.
Ngoài 2 km từ các điểm neo hoặc ngoài giờ train thì trả lý do không dùng được.
Phạm vi này chỉ là chặn ngoại suy thô, không phải bằng chứng chất lượng địa phương.

Khoảng thu nhập là khoảng mô phỏng danh nghĩa 80%, độ phủ test ~75,8%; calibrated=false
vẫn được giữ đúng, UI cho xem kèm nhãn mô phỏng, không giả vờ đạt 80%.
Năng suất chưa tính đầy đủ đi đón/chuyển vùng/offline. Thời tiết, rest POI, routing,
traffic vẫn theo provider và có thể thiếu độc lập với model.

API bổ sung ml_insights.source=synthetic_base_model, model_name, artifact_sha256,
status, areas; personal_model=null. Các mốc backtest là kết quả offline của model chung.
Main API không đưa nhật ký synthetic vào database hoặc history tài khoản.
Chế độ research riêng vẫn là công cụ đánh giá tài xế mô phỏng, không phải luồng chính.

Local: mặc định đọc thư mục trên, có thể đặt GIGCA_MAIN_MODEL_DIR ở môi trường tiến trình.
Model cần models.joblib, report.json, catalog.json. Chỉ đọc artifact do quản trị viên
tin cậy cung cấp. Kiểm tra SHA256 và phiên bản sklearn trước khi nạp; cache trong process,
cần restart backend khi thay artifact. Không ghi đè model từ client.

Docker: compose.app.yaml mount thư mục model vào /app/main-model, chỉ đọc.
Artifact không commit vào Git/image; khi chuyển máy cần mang đủ thư mục model.
Thư viện backend pin theo môi trường train trong api/model-requirements.txt.

```powershell
docker compose -f compose.app.yaml -f compose.research.yaml up -d --build
```

Nếu cần tái tạo catalog từ đúng input đã hash (không train lại):

```powershell
.\.venv\Scripts\python.exe -m experiments.synthetic.export_catalog .cache/synthetic/gigca-drivers-32-v2/contextual-seed7 .cache/models/logistic-hazard-quantile-gb
```


## Expanded HCMC model — 15 October 2026

New artifact `.cache/models/logistic-hazard-quantile-gb-hcmc/models.joblib` trained from
`.cache/synthetic/hcmc-expanded-32/contextual-seed7` (32 API personas, 120 simulated days,
47 historical HCMC anchors). Same model families/default parameters; no parameter search.
The earlier six-anchor model remains unchanged in its original directory.

Validation gates both passed. Test: wait NLL 1.9941 vs KM 2.1510;
cycle MAE 21,508 VND/hour vs mean baseline 24,872; nominal 80% coverage observed 79.36%.
Model remains synthetic research only; these results do not establish real-world accuracy.
Report, catalog, split/matching metadata and four PNG/SVG figures accompany the artifact.
SHA256: `2804e216dda2a421f73bfe282ad65b06a3c028cd119b9afaafcfd7ee855716f0`.

Local `.env` selects `GIGCA_MAIN_MODEL_DIR=.cache/models/logistic-hazard-quantile-gb-hcmc`
and `GIGCA_MODEL_HOST_DIR=./.cache/models/logistic-hazard-quantile-gb-hcmc` for the Docker bind.
Compose keeps `/app/main-model` as the container path. Restart/rebuild is required to load it.
Both earning objectives passed artifact inference smoke checks at Bach Khoa Ly Thuong Kiet,
An Nhon Tay (Cu Chi) and Hang Duong (Can Gio). 58 API tests passed.
The 2 km geographic support rule is retained around the new anchors; this is not continuous
coverage of every point in the city. Historical account data/volumes are unaffected.

```powershell
docker compose -f compose.app.yaml -f compose.research.yaml up -d --build
```

To roll back, set both model variables back to the original `logistic-hazard-quantile-gb`
directory and recreate the backend. Never delete the session volume for a model switch.
