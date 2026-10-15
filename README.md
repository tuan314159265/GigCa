# GigCa — gợi ý khu vực chờ cho tài xế

GigCa kết hợp bản đồ, thời tiết, giao thông và mô hình học máy để gợi ý khu vực chờ/nghỉ.
Frontend Next.js 16 / React 19; backend Python 3.12; tài khoản và lịch sử riêng lưu SQLite.
Bản này sử dụng **model chung huấn luyện trên dữ liệu mô phỏng**, chưa cá nhân hóa theo lịch sử tài xế.
POI và LLM hỗ trợ diễn giải; chưa tham gia xếp hạng của model.

## Chạy từ bản clone bằng Docker

Cần Git, Python 3.12 (chỉ thư viện chuẩn cho bước khôi phục), Docker Desktop đang chạy Linux containers.
Chạy trong thư mục chứa README này:

```powershell
git clone --branch feat/gigca-integrated-v1 https://github.com/tuan314159265/GigCa.git
cd GigCa
python scripts/restore_release.py
Copy-Item .env.example .env
```

Mở `.env`, điền `API_TOMTOM`. Không cần key LLM để chạy engine.
Model mở rộng đã được cấu hình mặc định, không cần sinh dữ liệu hay train lại.

```powershell
docker compose -f compose.app.yaml -f compose.research.yaml up -d --build
docker compose -f compose.app.yaml -f compose.research.yaml ps
```

Mở http://127.0.0.1:3000/auth/register tạo tài khoản; đăng nhập tại `/auth/login`;
ứng dụng chính tại `/dashboard/gigca`. Cho phép quyền vị trí hoặc tìm địa chỉ/nhập tọa độ,
nhập tùy chọn rồi bấm **Tính gợi ý**, sau đó chọn một trong bốn mục tiêu.
`compose.research.yaml` chỉ bật API nghiên cứu với dataset riêng; không nhập dữ liệu mô phỏng vào tài khoản.
Có thể bỏ override này nếu chỉ cần dashboard thông thường.

Camera là tùy chọn, tải catalog công khai khi cần (không cần TomTom key):

```powershell
python scripts/fetch_public_cameras.py
```

Nguồn camera có thể thay đổi hoặc từ chối truy cập. Không có camera không chặn luồng gợi ý.
Không lưu ảnh camera vào repo. Không có key TomTom thì tìm địa điểm, tuyến và traffic trực tiếp
không đầy đủ; app báo thiếu dữ liệu, không tự tạo tuyến hoặc giao thông thông thoáng.

## Cấu hình

| Biến | Vai trò |
|---|---|
| `API_TOMTOM` | Search/geocoding, routing, nền bản đồ và traffic |
| `GIGCA_DATA_MODE=live` | Dữ liệu provider, không tự thay bằng fixture |
| `GIGCA_MAIN_MODEL_DIR` | Thư mục model khi chạy Python local |
| `GIGCA_MODEL_HOST_DIR` | Thư mục model bind readonly vào Docker |
| `GIGCA_SESSION_DB` | SQLite local; Docker dùng named volume riêng |
| `GIGCA_LLM_EXPLANATIONS` | Bật/tắt diễn giải bằng LLM |
| `GIGCA_LLM_BASE_URL`, `GIGCA_LLM_API_KEY`, `GIGCA_LLM_MODEL` | Provider tương thích OpenAI, tùy chọn |
| `GIGCA_FRONTEND_PORT` | Cổng web, mặc định 3000 |

Thời tiết dùng Open-Meteo không cần key trong adapter hiện tại. Các dịch vụ ngoài có quota,
điều kiện sử dụng và giới hạn vùng phủ riêng. Không đưa key vào frontend hoặc commit `.env`.
Sau đổi key/cấu hình backend: `docker compose -f compose.app.yaml -f compose.research.yaml up -d --force-recreate backend`.
Sau sửa source: thêm `--build`. Frontend build flag cần build lại frontend.

## Dữ liệu và trọng số đã đóng gói

`artifacts/research/` chứa hai archive khoảng 11 MB tổng cộng và manifest SHA256:

- `hcmc-expanded-32.zip`: đúng dataset mở rộng đã chốt, 32 tài xế ảo / 16 nhóm hành vi,
  120 ngày đến 14/10/2026, 47 điểm neo thuộc TP.HCM trước sáp nhập; không Dĩ An.
  Có 25.235 chuyến, 37.098 đợt chờ; nhật ký JSON/CSV, personas, kế hoạch ca,
  coverage, checksum, prompt và phản hồi LLM được chấp nhận.
- `logistic-hazard-quantile-gb-hcmc.zip`: `models.joblib`, catalog, report, split,
  kết quả ghép và biểu đồ PNG/SVG/CSV. Không chứa model cũ hay kết quả search thử.

`python scripts/restore_release.py` xác minh hash rồi giải nén vào `.cache/`.
Không ghi đè file khác nội dung. `--verify-only` kiểm tra bản đã khôi phục.
Dữ liệu trong archive hoàn toàn mô phỏng, không phải lịch sử người dùng.
Không kèm SQLite tài khoản, API key, log cá nhân, `.venv`, `node_modules`, cache build.

Polygon GADM dùng kiểm tra phạm vi không được phân phối lại trong repo; nguồn và điều kiện
ở [docs/EXPANDED_GEOGRAPHY.md](docs/EXPANDED_GEOGRAPHY.md). Không cần polygon để chạy
model hoặc train lại trên dataset đã xuất; cần lấy hợp lệ từ nguồn khi sinh lại có kiểm tra biên.
Tọa độ điểm neo lấy từ TomTom, không xác nhận vị trí đỗ xe; dữ liệu bên thứ ba vẫn chịu điều kiện nguồn.

## Bốn mục tiêu và cơ chế

| Mục tiêu | Cơ chế thực tế |
|---|---|
| Cuốc giá trị cao | Chọn năng suất trung vị đồng/giờ cao nhất từ quantile Gradient Boosting, trong phạm vi di chuyển |
| Giữ vị trí tốt | Logistic Hazard dự đoán xác suất nhận cuốc và chờ; điểm = P(nhận trong 10 phút)% − 1,5 × phút chờ − 2 × km di chuyển, giới hạn 0–100 |
| Nghỉ ngơi | Điểm nghỉ có routing hợp lệ; ưu tiên đã xác minh, tới nhanh, loại điểm phù hợp |
| Né mưa & kẹt xe | Quy tắc dựa trên dự báo mưa, mức chịu mưa và traffic có dữ liệu |

Nhãn năng suất = (tiền sau phí nền tảng − nhiên liệu chuyến) / (giờ chờ + giờ chở khách).
Đây là năng suất một chu kỳ, không phải báo giá cuốc tiếp theo; chưa tính đầy đủ đi đón/chuyển vùng.
Khoảng cách chuyển vùng trong xếp hạng ML là ước tính địa lý; tuyến TomTom hiển thị sau đó
không phải đầu vào chi phí chính của model hiện tại.
Model chờ dùng horizon giới hạn 30 phút, không phải thời gian chờ còn lại sau số phút đã chờ.

Features hiện tại: thời điểm, cuối tuần, tọa độ tương đối và mưa. POI chưa là feature.
Bản mở rộng vẫn giới hạn vị trí trong 2 km quanh điểm neo, giờ train 06–22 và miền mưa 0–8 mm;
47 điểm neo không có nghĩa phủ liên tục toàn thành phố. Thiếu điều kiện thì trả lý do, không ép dự đoán.

Model gồm Logistic Hazard và ba Gradient Boosting quantile (10/50/90%), hiệu chỉnh conformal.
Chia theo tài xế và thời gian: train, validation, calibration, test; không trộn ngẫu nhiên từng chuyến.
Test mô phỏng: cycle MAE khoảng 21.508 đ/giờ, độ phủ khoảng 79,36% cho khoảng danh nghĩa 80%;
không suy ra độ chính xác với tài xế thật. Xem report đã đóng gói và [docs/MAIN_MODEL.md](docs/MAIN_MODEL.md).

## Train lại và biểu đồ

Không cần gọi API khi train lại dataset đã khôi phục. Python phải khớp dependency của artifact:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m experiments.synthetic train-base .cache/synthetic/hcmc-expanded-32/contextual-seed7 --output .cache/models/logistic-hazard-quantile-gb-hcmc-retrained --plots
```

Chọn output mới để giữ bản chính. Trọng số ở `models.joblib`, metrics ở `report.json`, biểu đồ ở `plots/`.
Đổi hai biến đường dẫn model trong `.env` nếu muốn kích hoạt bản train mới.
Learning curve của model chờ là các lần fit trên tập con, không phải loss theo epoch.
Chi tiết: [experiments/synthetic/TRAIN_BASE.md](experiments/synthetic/TRAIN_BASE.md),
[docs/CYCLE_MATCHING.md](docs/CYCLE_MATCHING.md), [experiments/synthetic/RESEARCH_METHOD_V2.md](experiments/synthetic/RESEARCH_METHOD_V2.md).

## Chạy native không dùng Docker

Khôi phục artifact, tạo `.env` và cài Python như trên. Mở hai terminal:

```powershell
.\.venv\Scripts\python.exe -m api.v1_server
```

```powershell
cd web
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Node.js 22; frontend trỏ backend `http://127.0.0.1:8000` qua BFF.
Linux/macOS dùng `cp`, `.venv/bin/python` tương ứng. Build frontend production: `npm run build`.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s api/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s engine/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s experiments/synthetic/tests -q
cd web
npx tsc --noEmit
npm run build
```

Các bài test dùng fixture/mock không cần key provider thật. Kiểm tra provider riêng:
`python scripts/check_demo_providers.py`; không đưa output có thông tin cấu hình lên Git.

## Lưu trữ và dừng app

SQLite tài khoản, hồ sơ, lịch sử cá nhân và phiên chạy nằm trong Docker volume `gigca_sessions`.
Model/dataset mount readonly, tách khỏi database. Mỗi tài khoản chỉ truy cập lịch sử của mình;
synthetic research API không thêm chuyến vào lịch sử cá nhân. Đăng ký mới tự lưu vào DB.

```powershell
docker compose -f compose.app.yaml -f compose.research.yaml stop
docker compose -f compose.app.yaml -f compose.research.yaml start
# Hoặc xóa container nhưng giữ volume:
docker compose -f compose.app.yaml -f compose.research.yaml down
```

Không thêm `-v` nếu cần giữ dữ liệu. SQLite hiện tại phù hợp demo một backend;
PostGIS trong `compose.yaml` là hạ tầng data riêng, chưa thay DB tài khoản bằng Neon/PostgreSQL.

## Kiến trúc và tài liệu

- `web/`: dashboard navy, auth, BFF giữ token trong cookie HttpOnly, bản đồ và chi tiết tuyến.
- `api/`: API v1, tài khoản/import, provider proxy, model đã lưu, camera, giải thích LLM.
- `engine/`: feature, ghép chu kỳ, model ML, scorers và quy tắc an toàn.
- `data/`: adapter/ETL, schema, import nhật ký; `contracts/`, `config/`: giao diện và tham số.
- `experiments/synthetic/`: sinh personas qua LLM, mô phỏng, audit, train và report.
- `scripts/`: restore release, thu thập catalog và công cụ kiểm tra.

API: [docs/DRIVER_ACCOUNTS_API.md](docs/DRIVER_ACCOUNTS_API.md).
Camera: [docs/TRAFFIC_CAMERAS.md](docs/TRAFFIC_CAMERAS.md).
LLM: [docs/LLM_EXPLANATIONS.md](docs/LLM_EXPLANATIONS.md).
Quy tắc và nguồn: [RULES.md](RULES.md), [data/README.md](data/README.md).
Các tài liệu v1/legacy được giữ để tham khảo; đường dẫn artifact và cách chạy hiện hành theo README này.
