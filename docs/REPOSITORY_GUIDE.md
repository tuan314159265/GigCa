# Cấu trúc repo GigCa và cách chạy

## Folder chính

```
GigCa/
  web/    FE chính: Next.js + StudioAdmin, dashboard GigCa
  api/         BE: phiên, input, gọi Engine, kết quả/lịch sử, HTTP v1
  data/        Data: collector live, ETL, nguồn mẫu, PostGIS/migrations
  engine/      Decision Engine: bốn hướng và danh sách ứng viên
  config/      Tham số Engine
  contracts/   Contract dữ liệu giữa Data và Engine
  docs/legacy-data-explorer/  Data Explorer cũ, chỉ tham khảo
  docs/        Thiết kế, giới hạn dữ liệu, hướng dẫn chạy
  compose.yaml PostGIS
  .env.example Mẫu cấu hình BE; .env thật không commit
```

Không đổi tên api thành backend vì import/các test đang dùng package api. Chạy backend từ root repo; frontend chạy từ web/. Không chạy api.provider_proxy hoặc api.dashboard đồng thời api.v1_server cùng port 8000.

## Chạy lần đầu — PowerShell

Terminal BE từ root repo:

```powershell
Copy-Item .env.example .env # chỉ khi chưa có .env, không ghi đè key đã có
python -m api.v1_server
```

Điền API_TOMTOM trong .env cho POI, tuyến và giao thông. GIGCA_DATA_MODE=live là nguồn theo GPS; simulation chỉ để demo. Weather Open-Meteo không cần key. Backend session hiện dùng SQLite .cache/backend.sqlite3; collector live trực tiếp không yêu cầu PostGIS. PostGIS cho mode database/ETL xem data/db/README.md.

Terminal FE:

```powershell
cd web
npm ci
Copy-Item .env.example .env.local # chỉ khi chưa có file
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Đặt NEXT_PUBLIC_GIGCA_PREVIEW=false trong web/.env.local để dùng API. True để preview cố định. Truy cập http://127.0.0.1:3000/dashboard/gigca. FE proxy /api tới backend 8000; API key không đưa vào NEXT_PUBLIC biến.

Lấy GPS hoặc nhập hai tọa độ → Tính gợi ý. Không tự nhận vị trí demo là vị trí tài xế. Dữ liệu cuốc/booking chưa có nên hai hướng đầu có thể thiếu dữ liệu thật. Thiếu key/nguồn lỗi không âm thầm thay bằng fixture. Hướng dẫn chi tiết docs/LIVE_RUN.md; đường dẫn FE hiện là web/ thay cho gigca-studio/ trong hướng dẫn cũ.

## Kiểm tra

```powershell
python -B -m unittest discover -s api/tests -q
python -B -m unittest discover -s engine/tests -q
cd web
npx tsc --noEmit
```

Không commit .env, .env.local, .cache, node_modules, .next hoặc token phiên. Repo giữ LICENSE upstream frontend. Component UI được giữ nguyên; thay đổi trong screen/theme.

## Các thư mục ngoài repo

studio-admin-original/: bản template gốc giữ nguyên.
gigca-studio/: bản làm việc trước khi gom; không còn là FE chính.
free-react-tailwind-admin-dashboard/: prototype TailAdmin cũ, không cần để chạy bản mới.
TMA/: đề bài/code mẫu, không phải runtime.

Các thư mục này được giữ làm tham chiếu, không được nhúng vào repo GigCa. Mọi chỉnh sửa tiếp theo thực hiện trong repo GigCa/frontend và các folder BE/Data/Engine tương ứng.

## Giới hạn còn lại

Backend phiên SQLite cục bộ; chưa triển khai production auth/rate limit/scheduler hoặc chọn ứng viên thay thế tạo plan mới. TomTom cần key và smoke test. Hai hướng fare/dropoff thiếu nguồn nghiệp vụ. Việc gom repo không có nghĩa các phần này đã hoàn tất. GitHub chưa được push trong tác vụ này.
