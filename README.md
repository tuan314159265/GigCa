# GigCa

**Choose the best way to drive.** Web hỗ trợ tài xế cân nhắc nơi chờ, di chuyển, nghỉ và điều kiện mưa/giao thông tại TP.HCM.

Next.js/React · Python 3.12 · SQLite · Docker Compose · TomTom · Open-Meteo.
ML chung học trên **dữ liệu mô phỏng**, chưa cá nhân hóa theo lịch sử tài xế. LLM chỉ diễn giải, không thay kết quả engine.

## Chạy bằng Docker

Yêu cầu: Git, Python 3.12 (khôi phục artifact chỉ cần thư viện chuẩn), Docker Desktop với Linux containers.

~~~powershell
git clone --branch feat/gigca-integrated-v1 https://github.com/tuan314159265/GigCa.git
cd GigCa
python scripts/restore_release.py
Copy-Item .env.example .env
~~~

Điền API_TOMTOM trong .env rồi chạy:

~~~powershell
docker compose -f compose.app.yaml up -d --build
docker compose -f compose.app.yaml ps
~~~

Mở [đăng ký](http://127.0.0.1:3000/auth/register), đăng nhập, vào
[/dashboard/gigca](http://127.0.0.1:3000/dashboard/gigca).
Chọn GPS hoặc nhập địa chỉ/tọa độ, đặt tùy chọn, bấm **Tính gợi ý** rồi chọn một trong bốn hướng.
Không cần sinh dữ liệu hoặc train lại model.

Bật thêm API nghiên cứu với dataset riêng:

~~~powershell
docker compose -f compose.app.yaml -f compose.research.yaml up -d --build
~~~

Research không nhập nhật ký mô phỏng vào tài khoản. compose.yaml là PostGIS/ETL tùy chọn,
**không phải** file khởi động web app.

## Bốn hướng

| Hướng | Ưu tiên thực tế |
|---|---|
| Cuốc giá trị cao | Trung vị năng suất chu kỳ ML cao nhất trong phạm vi di chuyển |
| Giữ vị trí tốt | P(nhận trong 10 phút)% − 1,5 × phút chờ − 2 × km chuyển vùng; giới hạn 0–100 |
| Nghỉ ngơi | POI nghỉ có routing hợp lệ; mức xác minh, thời gian tới và loại điểm |
| Né mưa & kẹt xe | Quy tắc theo dự báo, mức chịu mưa và traffic có dữ liệu |

### Điểm đến live

- Lấy ứng viên theo GPS/địa chỉ đã chọn. Điểm neo chỉ kiểm tra miền model, không là điểm đến mặc định.
- Ưu tiên đại học/cao đẳng, trung tâm thương mại, chợ công cộng, bệnh viện, tòa nhà thương mại/công nghiệp.
  Phân loại từ TomTom; quy tắc ưu tiên do engine đặt, không phải điểm “nổi tiếng”.
- Không có công trình phù hợp thì dùng POI địa phương dự phòng. Provider có thể phân loại sai;
  có bộ lọc bổ sung cho các cửa hàng bị gắn nhầm thành mall/tòa nhà.
- Lấy mẫu ở tâm và bốn hướng; tối đa 24 ứng viên phân bố theo hướng/khoảng cách, cache 5 phút.
  Tối đa 5 request tìm công trình, thêm tối đa 5 request khi cần tìm địa điểm dự phòng.
- Lọc tọa độ, trùng lặp, ngân sách di chuyển và miền ML. Đây là mẫu giới hạn, không phải kiểm kê
  toàn bộ địa điểm hay dữ liệu nhu cầu hành khách trực tiếp.
- Provider lỗi thì chỉ đánh giá vị trí hiện tại và báo thiếu nguồn; không âm thầm về điểm neo.
- POI live cách vài trăm mét vẫn có khoảng cách/thời gian/chi phí ước tính; chính vị trí hiện tại là 0 km.

POI–thời điểm chỉ điều chỉnh gần hòa: hướng thu nhập xét trong 1% baseline, bonus utility tối đa 0,5%;
hướng giữ vị trí xét trong 1 điểm, điều chỉnh tối đa ±0,5 điểm. Không thay tiền/xác suất/khoảng ML.
Các cửa sổ giờ đi lại là giả thuyết thủ công, không phải lịch tan học/tan ca được xác minh.

### Giao thông, camera, diễn giải

Khi chọn ở lại, app hiện các đường lấy mẫu quanh GPS. Chi tiết traffic/camera cập nhật khoảng
30 giây khi đang hiển thị. Mẫu giao thông không chứng minh trạng thái toàn tuyến.

Camera tùy chọn, tải catalog công khai bằng:

~~~powershell
python scripts/fetch_public_cameras.py
~~~

Ảnh là snapshot, không phải live video; thời điểm tải không xác nhận thời điểm chụp.
Nguồn có thể gián đoạn; không có camera không chặn engine. Không lưu ảnh vào Git.

Giải thích dùng provider tương thích OpenAI → Google Gemini → lý do engine.
Chỉ diễn giải loại POI, dự báo và traffic có bằng chứng; không khẳng định đông khách hoặc lịch tan học.
Không cần key LLM để tính gợi ý.

## Cấu hình

Sao chép .env.example; không commit .env/key thật.

| Biến | Vai trò |
|---|---|
| API_TOMTOM | Search, POI, routing, tiles, traffic |
| GIGCA_DATA_MODE | Mặc định live; thiếu dữ liệu không tự thay bằng fixture |
| GIGCA_LIVE_CANDIDATES | true: điểm đến API; false: catalog cũ để đối chiếu |
| GIGCA_POI_RANKING | Bật/tắt điều chỉnh POI–thời điểm nhỏ |
| GIGCA_LLM_EXPLANATIONS | Bật/tắt diễn giải LLM |
| GIGCA_LLM_BASE_URL / GIGCA_LLM_API_KEY / GIGCA_LLM_MODEL | Provider tương thích OpenAI; đặt model được hỗ trợ |
| GIGCA_GEMINI_API_KEY / GIGCA_GEMINI_MODEL | Google dự phòng; chọn model khả dụng cho tài khoản |
| GIGCA_MAIN_MODEL_DIR | Model khi chạy Python native |
| GIGCA_MODEL_HOST_DIR | Thư mục model mount readonly vào Docker |
| GIGCA_SESSION_DB | SQLite native; Docker dùng volume riêng |
| GIGCA_FRONTEND_PORT | Cổng web, mặc định 3000 |
| NEXT_PUBLIC_GIGCA_PREVIEW | false cho live; thay đổi cần build frontend lại |

Open-Meteo không cần key trong adapter. Quota/chi phí/quyền sử dụng theo từng provider.
Key nằm ở backend, không đưa vào frontend. Gemini có tích hợp dự phòng; khả dụng phụ thuộc key/model của bạn.

## Model và dữ liệu đi kèm

[artifacts/research](artifacts/research/README.md) chứa dataset/model (~11 MB) và manifest SHA256.
Script restore xác minh archive và từng member, giải nén vào .cache, không ghi đè file khác nội dung.

- 32 tài xế ảo / 16 nhóm hành vi, 120 ngày đến 14/10/2026, 47 neo TP.HCM trước sáp nhập; không Dĩ An.
- 25.235 chuyến, 37.098 đợt chờ; personas, lịch ca, audit và provenance đi kèm.
- Logistic Hazard cho chờ; Quantile Gradient Boosting P10/P50/P90 và split conformal cho năng suất.
- Split theo tài xế/thời gian. Test mô phỏng: MAE ~21.508 đ/giờ so baseline ~24.872;
  độ phủ khoảng danh nghĩa 80% đạt ~79,36%. Chưa chứng minh hiệu quả với tài xế thật.

~~~powershell
python scripts/restore_release.py --verify-only
~~~

**Giới hạn:** ML hỗ trợ trong 2 km quanh neo, giờ 06–22 và mưa 0–8 mm; không phủ liên tục toàn thành phố.
Năng suất = (tiền sau phí nền tảng − nhiên liệu chuyến) / (giờ chờ + giờ chở khách), chưa đủ đi đón/chuyển vùng.
Không phải giá cuốc tiếp theo hoặc lợi nhuận toàn ca. Chờ giới hạn 30 phút, chưa phải thời gian còn lại
có điều kiện sau số phút đã chờ. Khoảng cách xếp hạng là ước tính địa lý; tuyến TomTom có thể khác.
POI/traffic chưa là features đã học. POI/neo không xác nhận chỗ đỗ hợp pháp hay chắc chắn có cuốc.

Polygon GADM không phân phối lại; chạy/train dataset có sẵn không cần polygon.
Xem điều kiện nguồn ở [artifact README](artifacts/research/README.md).

## Phát triển native

Python 3.12, Node.js 22; restore artifact và tạo .env trước.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m api.v1_server
~~~

Terminal thứ hai:

~~~powershell
cd web
Copy-Item .env.example .env.local
npm ci
npm run dev
~~~

BFF trỏ backend http://127.0.0.1:8000. Linux/macOS dùng cp và .venv/bin/python.
Train/sinh dữ liệu: [experiments/synthetic](experiments/synthetic/README.md).

## Kiểm tra

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s api/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s engine/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s experiments/synthetic/tests -q
cd web
npx tsc --noEmit
npm run build
node scripts/test-route-presentation.cjs
node scripts/test-visible-poll.cjs
node scripts/test-weather-timeline.cjs
~~~

Unit tests dùng mock/fixture. Provider thật kiểm tra riêng bằng python scripts/check_demo_providers.py;
không công khai thông tin cấu hình/key từ máy cá nhân.

## Cập nhật, dừng, lưu dữ liệu

Sau sửa source: docker compose -f compose.app.yaml up -d --build.
Sau chỉ đổi key/cấu hình: docker compose -f compose.app.yaml up -d --force-recreate backend.
Nếu bật research, thêm -f compose.research.yaml vào các lệnh tương ứng.

~~~powershell
docker compose -f compose.app.yaml stop
docker compose -f compose.app.yaml start
# Xóa container nhưng giữ dữ liệu:
docker compose -f compose.app.yaml down
~~~

**Không thêm -v nếu muốn giữ tài khoản/lịch sử.** SQLite ở volume gigca_sessions, tách model/dataset readonly.
Volume không thay thế backup; sao lưu riêng trước khi chuyển máy.
BFF giữ token trong cookie HttpOnly, API kiểm tra chủ sở hữu lịch sử.
SQLite/ThreadingHTTPServer hiện phù hợp demo một backend, chưa có benchmark production.

## Cấu trúc

~~~text
api/                    API, auth, provider, inference, điểm đến live, camera, LLM
web/                    Next.js, BFF, dashboard, bản đồ và theme
engine/                 ML, scorers, quy tắc, kiểm thử
data/                   Collector, adapter, importer, fixture, PostGIS/ETL tùy chọn
config/                 Tham số engine và POI policy
contracts/              Schema đầu vào
experiments/synthetic/  Sinh, audit, train, đánh giá mô phỏng
artifacts/research/     Dataset/model đóng gói, manifest hash
scripts/                Restore, fetch, công cụ kiểm tra
~~~

Hướng dẫn module: [API](api/README.md), [Engine](engine/README.md), [Data](data/README.md),
[Frontend](web/README.md). Giữ LICENSE frontend và attribution bản đồ.
Không đưa report/pitch, ghi chú agent, secrets, database tài khoản hoặc build output vào repo.
