# Sinh dữ liệu tài xế tổng hợp cho nghiên cứu GigCa

**Không phải dữ liệu thật, không phải dự báo nhu cầu TP.HCM và không được nạp vào database tài xế.** Bộ nghiên cứu không được backend/collector import. Không sửa nhãn thành `real_driver_log`.

## Luồng

Persona JSON → kiểm tra schema/range → môi trường chung → chuỗi ca hoạt động → kiểm tra thời gian/vị trí/tiền → CSV/JSON → backtest engine offline.

LLM tạo persona/thuộc tính hành vi; Python thực thi chuỗi có ràng buộc và tính nhãn. Không yêu cầu LLM bịa hàng nghìn cuốc độc lập. Persona là giả thuyết, không phải người thật. Có ba nguồn persona:

- `personas.assistant.json`: 12 hồ sơ do trợ lý LLM soạn trong phiên làm việc 14/10/2026; ghi rõ `assistant_authored`, không giả danh output Ollama hoặc khảo sát tài xế.
- `reference_design`: thiết kế tham chiếu xác định, chạy không cần LLM/API.
- Ollama: gọi model đã cài trên máy, yêu cầu structured JSON theo schema rồi kiểm tra lại. Không tự tải model và không gửi dữ liệu tài xế thật.

## Chạy ngay không cần key

Từ thư mục gốc repo, sinh dữ liệu chỉ cần Python standard library:

```powershell
python -m experiments.synthetic generate --personas experiments/synthetic/personas.assistant.json --days 42 --end-date 2026-10-13 --world contextual --seed 7 --output .cache/synthetic/20261014-llm-contextual-v1
```

Để dùng persona tham chiếu: bỏ `--personas`, thêm `--drivers 12`. Không ghi đè output đã tồn tại; chọn tên thư mục mới.

Output:

```text
manifest.json              # seed, world, giả thuyết, hash code/persona, biểu cước, ngày split, báo cáo hợp lệ
D01/research_log.json       # persona, profile, trips, waits, timeline liên tục, liên kết ID
D01/trips.csv               # các cột engine cần + source_kind=synthetic
D01/waits.csv               # đợt chờ gồm trip/moved/offline + source_kind=synthetic
...
```

Toàn bộ output mặc định đặt dưới `.cache/`, đã git-ignore. Bộ dữ liệu có schema riêng `gigca_synthetic_driver_log_v1`. Importer lịch sử thật từ chối các dòng mang `source_kind=synthetic`; việc xóa marker không biến dữ liệu thành thật và không được làm để bỏ qua kiểm tra.

## Dùng LLM tạo persona mới

Lấy prompt + JSON schema để dùng trong giao diện LLM bất kỳ:

```powershell
python -m experiments.synthetic prompt --count 12 --output .cache/synthetic/persona-prompt.json
```

Lưu JSON LLM trả về (object có `personas`) vào một file, truyền qua `generate --personas <file>`. Dữ liệu thiếu trường, ID trùng/không an toàn, vùng không có trong catalog, giá trị NaN hoặc vượt miền sẽ bị từ chối, không tự sửa.

Nếu đã có Ollama chạy trên localhost và model đã được cài:

```powershell
python -m experiments.synthetic personas --model <ten-model-da-cai> --count 12 --seed 7 --output .cache/synthetic/personas-ollama.json
python -m experiments.synthetic generate --personas .cache/synthetic/personas-ollama.json --world contextual --output .cache/synthetic/ollama-run-01
```

Adapter dùng `POST /api/chat`, `stream=false`, JSON schema ở `format`, có timeout; không chạy code từ LLM. Metadata lưu model, seed và hash prompt. Seed không bảo đảm output LLM giống bit-for-bit giữa các runtime/model; giữ file persona đã nhận để tái lập bộ mô phỏng. Bản mẫu hiện có không chứng minh đã gọi Ollama.

## Các kịch bản

| `--world` | Cơ chế |
| --- | --- |
| `contextual` | Thời gian chờ Weibull, scale thay đổi theo giờ/vùng/cuối tuần/mưa; hệ số là giả thuyết nghiên cứu. |
| `null` | Thời gian tới cuốc không phụ thuộc ngữ cảnh. Thời điểm đổi chỗ/nghỉ vẫn có thể phụ thuộc mưa, nên censoring có thể tạo thiên lệch. Không bảo đảm model gate luôn thất bại. |
| `drift` | 80% ngày đầu giống cơ chế contextual; giai đoạn test đảo hiệu ứng vùng và đổi ảnh hưởng mưa. |

Sinh cả ba bằng output riêng để so độ nhạy, không chỉnh tham số tới khi ML thắng. Đây chưa phải thử nghiệm đối chiếu LLM-only/AttrPrompt đầy đủ.

Môi trường thời tiết/giao thông được chia sẻ theo ngày/giờ/vùng giữa tài xế. Mỗi tài xế có RNG riêng nên không đổi lịch sử chỉ vì đổi thứ tự persona. Khi tài xế đổi vùng, nghỉ hay đi đón đều tiêu tốn thời gian. Giữa hai ca có sự kiện off-shift giải thích vị trí đầu ca mới. Cuốc cuối có thể làm tăng ca.

### Giới hạn địa lý và tiền

- Điểm neo có tọa độ quanh TP.HCM nhưng chưa xác minh là điểm đỗ/đón hợp pháp, không snap vào đường.
- Routing hiện là **đường chim bay × hệ số vòng đường**, không phải TomTom/OSRM. Timeline kiểm tra cự ly không nhỏ hơn đường chim bay và tốc độ không vượt 80 km/h trong kịch bản thiết kế. Muốn nghiên cứu đường thật cần thay hàm `route` bằng mạng đường hoặc route catalog có nguồn và thời điểm.
- Tiền tính từ biểu cước hiện có trong `config/engine_config.json`, tỷ lệ tài xế và biến thiên lognormal nhỏ. Nguồn biểu cước trong config còn cần hoàn thiện, không coi đây là giá sàn thực đã xác minh. `net_vnd` sau phí nền tảng, trước nhiên liệu; không gồm tip/thưởng.
- Thu nhập chu kỳ engine không tính đầy đủ chi phí/time pickup, chuyển vùng và nghỉ. Raw timeline lưu riêng các khoản thời gian/cự ly này để nghiên cứu sau.

### Ghép chờ–cuốc

`wait.end=request_accepted_at`; `trip.started_at=pickup_at`, có chặng đi đón ở giữa. ID liên kết rõ trong timeline. Engine hiện vẫn ghép bằng ±120 giây và ±0,003 độ mỗi trục. Evaluator báo tỷ lệ ghép được và số bị loại; không sửa timestamp/tọa độ để ép ghép. Dataset bị chọn lọc theo chặng đón gần là một giới hạn model, không phải lỗi được giấu.

## Đánh giá bằng model engine

Cài dependency ML trong venv (không cần API key):

```powershell
.\.venv\Scripts\python.exe -m pip install -r engine/requirements.txt
.\.venv\Scripts\python.exe -m experiments.synthetic evaluate .cache/synthetic/20261014-llm-contextual-v1 --driver D02
```

Bỏ `--driver` để đánh giá từng tài xế; model được fit riêng, không pool tài xế. File `evaluation_D02.json` chứa:

- Gate model chờ so với KM baseline và model không ngữ cảnh trên development history.
- NLL trên các ngày test cuối chưa được dùng để fit/gate.
- Tỷ lệ ghép được wait–trip.
- MAE năng suất chu kỳ so với trung bình train; độ phủ và độ rộng khoảng quantile/conformal trên test.
- Khi test ít hơn 30 chu kỳ, ghi rõ chưa đủ mẫu để đánh giá độ phủ; không gọi là calibrated/đạt chuẩn.

Split theo ngày: 55% train / 25% calibration / 20% test. Model chờ dùng train+calibration làm development và giữ gate thời gian nội bộ của engine; chỉ sau đó mới fit development và đo test cuối. Model chu kỳ dùng train/calibration/test riêng theo ngày, không chia ngẫu nhiên các dòng person-period. Chu kỳ được gán nhóm theo ngày bắt đầu đợt chờ, không tách chuyến khỏi đợt chờ.

Model học từ dữ liệu tổng hợp chỉ phản ánh giả thuyết của bộ sinh. Gate vượt qua không cho phép bật model cho người thật. Model chờ hiện chưa có traffic feature và dùng mưa hiện thực tổng hợp, chưa mô phỏng sai số forecast. Thiếu mưa/điều kiện calibration trong engine sản phẩm vẫn là vấn đề riêng, chưa sửa trong bộ nghiên cứu này. Trước khi triển khai cần tập kiểm tra nhật ký thật độc lập.

## Kiểm thử

```powershell
python -m unittest discover -s experiments/synthetic/tests -v
```

Kiểm tra tái lập, tính liên tục, kiểm duyệt, phân chia ngày, LLM schema, export và chặn import dữ liệu tổng hợp vào lịch sử thật.

## Tài liệu phương pháp

- [AttrPrompt](https://arxiv.org/abs/2306.15895): đa dạng thuộc tính trong prompt.
- [Persona Hub](https://arxiv.org/abs/2406.20094): điều kiện theo persona.
- [Generation/Curation/Evaluation survey](https://arxiv.org/abs/2406.15126): tách sinh, làm sạch, đánh giá.
- [Synthetic Data, Real Errors](https://proceedings.mlr.press/v202/van-breugel23a.html): giới hạn suy luận khi coi synthetic là dữ liệu thật.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs): adapter JSON theo schema.

### ShopAIKey / OpenAI-compatible

Thiết kế phủ nhóm mới: xem [RESEARCH_METHOD_V2.md](RESEARCH_METHOD_V2.md). Lệnh `python -m experiments.synthetic.cohort --replicates 2 --output .cache/synthetic/my-v2` tạo 32 persona theo 16 tổ hợp; prompt tiếng Anh và thiết kế được lưu để báo cáo. `--plan-only` không gọi API. Nếu bị dừng, kiểm tra lỗi rồi dùng cùng lệnh thêm `--resume` để tái sử dụng batch hợp lệ; batch chưa đạt được yêu cầu sinh lại, có tính phí, bản bị loại được giữ để audit. Không ghi đè dataset cũ.

Đặt GIGCA_LLM_BASE_URL=https://api.shopaikey.com/v1, GIGCA_LLM_API_KEY và GIGCA_LLM_MODEL trong .env tại gốc repo. Không commit key. Chọn model ID được tài khoản hỗ trợ.

```powershell
python -m experiments.synthetic personas --provider compatible --count 3 --output .cache/synthetic/shopai-personas-test.json
python -m experiments.synthetic generate --personas .cache/synthetic/shopai-personas-test.json --days 42 --seed 7 --output .cache/synthetic/shopai-dataset-test
```

Lệnh đầu gọi API có thể tính phí, dùng prompt/schema có sẵn; lệnh thứ hai chạy simulator offline. Không tự retry khi lỗi hoặc tự thay bằng persona tham chiếu. File/thư mục output phải chưa tồn tại. Mỗi bản ghi là synthetic, không import vào lịch sử tài xế thật. Adapter lưu model, provider, usage và hash prompt; không lưu key. Không yêu cầu JSON mode chưa được provider xác nhận. Kết quả phải là JSON hợp lệ và finish_reason=stop.
