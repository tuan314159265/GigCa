# Driver Decision Engine — Đặc tả thiết kế cho đội code

*Tài liệu bàn giao cho AI/dev khác triển khai. Người viết đặc tả không code phần này; tài liệu này là toàn bộ "hợp đồng" về kiến trúc, thuật toán, xử lý thiếu dữ liệu và cách giải thích.*

---

## 0. Tóm tắt một câu

Khi tài xế đang rảnh (vừa trả khách hoặc đang chờ), hệ thống gợi ý nên làm gì tiếp theo theo **4 trục mục tiêu tách biệt** — (1) tối đa giá trị/cuốc, (2) giữ vị trí tốt, (3) điểm chờ/nghỉ, (4) an toàn & đỡ mệt — mỗi trục có **trạng thái dữ liệu riêng, điểm số riêng, giải thích riêng**; không gộp thành một con số duy nhất; tài xế tự quyết theo ưu tiên của mình.

Đây **không phải** một scoring engine gộp 1 điểm "vị trí tốt nhất". Nó là 4 lăng kính độc lập nhìn vào cùng một tập điểm ứng viên xung quanh tài xế.

---

## 1. Bối cảnh dữ liệu — điều quan trọng nhất cần hiểu trước khi code

Dự án có một "Data Overall Info" catalog rất nghiêm ngặt về việc không được bịa dữ liệu. Trước khi thiết kế thuật toán, đây là sự thật cần chấp nhận:

| Mục tiêu | Dữ liệu cần | Trạng thái hiện tại | Engine được phép làm gì |
|---|---|---|---|
| `max_trip_value` | Giá cuốc, booking/destination distribution | `insufficient_data` | **Không xếp hạng theo giá trị/cuốc.** Không dùng POI hay traffic làm proxy. |
| `maintain_position` | Điểm trả khách/phân bố destination, routing xe máy đã xác nhận | `insufficient_data` | **Không khẳng định xác suất cuốc kế tiếp.** Route mẫu hiện là `driving`, không phải xe máy. |
| `rest_spot` | POI ứng viên, quyền dừng/đỗ, giờ mở cửa | `partial` | Có thể hiển thị POI như **ứng viên chưa xác minh** — không gọi là điểm dừng an toàn/hợp pháp. |
| `safety_comfort` | Mưa theo khu vực/giờ, mức chịu mưa tài xế chọn; traffic/incident nếu có | `partial` | Chỉ dùng forecast mưa trong đúng phạm vi/thời gian hợp lệ; phải báo thiếu traffic; **không tính mệt từ thời tiết** (không có dữ liệu nhiệt cảm nhận/UV). |

Hệ quả thiết kế bắt buộc: **engine phải có khả năng trả lời "chưa đủ dữ liệu" một cách trung thực cho 2/4 mục tiêu ngay ở bản demo hiện tại**, đồng thời phải kiến trúc sẵn để khi có dữ liệu thật (fare, booking, traffic), chỉ cần cắm dữ liệu vào mà không đổi lõi engine. Đây chính là điểm cộng cho tiêu chí "đổi mới dữ liệu và AI" — thể hiện kỷ luật dữ liệu, không phải chỉ ra một con số đẹp.

**Luật vàng, áp dụng toàn bộ codebase:** thiếu dữ liệu ≠ 0. `missing`/`insufficient_data` phải là một giá trị/trạng thái tường minh trong kiểu dữ liệu, không bao giờ được để trống rồi mặc định tính là 0 hay trung tính.

---

## 2. Bảy nguyên tắc thiết kế bất biến

1. **Bốn lăng kính, không phải một điểm.** Không bao giờ gộp 4 mục tiêu thành một `overallScore`. Giao diện hiển thị 4 khối riêng.
2. **Tôn trọng `data_status` và `objective_readiness` tuyệt đối.** Đây là cổng kiểm soát đầu vào cho mọi scorer — xem Mục 4.
3. **Giải thích ghép từ số, không có câu chung chung.** Mọi lý do hiển thị phải trace được ngược về một trường dữ liệu cụ thể trong input.
4. **Không suy diễn chéo nhóm dữ liệu.** Không dùng mật độ POI để đoán nhu cầu cuốc; không dùng tỷ lệ đường đông xung quanh để đoán traffic một cạnh cụ thể.
5. **Ngưỡng và mapping phải là tham số, không hard-code ẩn.** Ví dụ mapping `rain_tolerance_level` → ngưỡng %/mm phải nằm trong một file config, có thể chỉnh, có ghi chú "đề xuất, chưa hiệu chỉnh".
6. **Engine là hàm thuần, tất định.** Cùng input → luôn cùng output. Không gọi API bên ngoài trong lõi tính điểm; input đã được chuẩn hóa từ trước (Data role lo phần đó).
7. **Tài xế quyết định cuối.** Mọi output là gợi ý + độ tin cậy, không phải mệnh lệnh.

---

## 3. Kiến trúc phân tầng

```
┌─────────────────────────────────────────────────────────┐
│ 1. Input Layer                                           │
│    EngineInput (đã chuẩn hóa theo hcmc_demo_snapshot)    │
│    + DriverContext (vị trí hiện tại, giờ, ca, idle_min)  │
│    + DriverPreferences (rain_tolerance, goal_weights…)   │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│ 2. Readiness Gate                                        │
│    Đọc data_status + objective_readiness                │
│    → quyết định mỗi objective chạy ở mode nào:           │
│      FULL / PARTIAL / INSUFFICIENT                       │
└─────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                ▼
┌───────────────┐┌───────────────┐┌───────────────┐┌───────────────┐
│ Scorer:       ││ Scorer:       ││ Scorer:       ││ Scorer:       │
│ max_trip_value││ maintain_     ││ rest_spot     ││ safety_       │
│               ││ position      ││               ││ comfort       │
└───────────────┘└───────────────┘└───────────────┘└───────────────┘
        │                │                │                │
        └────────────────┴────────────────┴────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│ 3. Explanation Layer                                     │
│    Với mỗi objective: build lý do từ đúng số vừa tính,   │
│    hoặc build câu "thiếu dữ liệu vì…" nếu INSUFFICIENT    │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│ 4. Uncertainty Layer                                      │
│    Gắn confidence (none/low/medium) theo data_status,     │
│    liệt kê giả định đã dùng, câu chốt "bạn quyết định"     │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│ 5. Output: DriverRecommendationOutput (4 khối độc lập)    │
└─────────────────────────────────────────────────────────┘
```

Điểm vào duy nhất cho giao diện: `runDriverEngine(input: EngineInput, ctx: DriverContext, prefs: DriverPreferences): DriverRecommendationOutput`.

---

## 4. Readiness Gate — cổng kiểm soát trước khi tính bất cứ điều gì

Mỗi objective phải đi qua gate này trước khi scorer chạy:

```ts
type ReadinessMode = "FULL" | "PARTIAL" | "INSUFFICIENT";

function resolveReadiness(
  objective: ObjectiveKey,
  dataStatus: DataStatusMap,
  objectiveReadiness: ObjectiveReadinessMap
): ReadinessMode {
  const declared = objectiveReadiness[objective]; // "insufficient_data" | "partial" | ...
  if (declared === "insufficient_data") return "INSUFFICIENT";
  if (declared === "partial") return "PARTIAL";
  // Ngay cả khi declared là "available", vẫn phải soi từng nhóm dữ liệu
  // cụ thể objective đó phụ thuộc — nếu bất kỳ nhóm nào missing/stale => hạ cấp.
  const requiredGroups = OBJECTIVE_DATA_DEPENDENCIES[objective];
  const anyMissing = requiredGroups.some(
    (g) => dataStatus[g] === "missing" || dataStatus[g] === "stale" || dataStatus[g] === "not_integrated"
  );
  return anyMissing ? "PARTIAL" : "FULL";
}
```

`OBJECTIVE_DATA_DEPENDENCIES` là bảng tường minh (không suy luận ngầm), ví dụ:

```ts
const OBJECTIVE_DATA_DEPENDENCIES: Record<ObjectiveKey, DataGroupKey[]> = {
  max_trip_value: ["trip_value", "demand_dropoff"],
  maintain_position: ["demand_dropoff", "routing"],
  rest_spot: ["poi", "verified_spots"],
  safety_comfort: ["weather", "traffic"],
};
```

Nguyên tắc: **scorer không bao giờ tự ý quyết định mode** — mode luôn do gate truyền vào, scorer chỉ hành xử theo mode được giao.

---

## 5. Thiết kế từng mục tiêu

### 5.1 `max_trip_value` — Tối đa giá trị/cuốc

**Mode hiện tại: INSUFFICIENT.**

```ts
function scoreMaxTripValue(mode: ReadinessMode, ...): ObjectiveResult {
  if (mode === "INSUFFICIENT") {
    return {
      objective: "max_trip_value",
      status: "insufficient_data",
      candidates: [],
      reasonForInsufficiency:
        "Chưa có dữ liệu giá cuốc/booking đã được cấp phép sử dụng; " +
        "không dùng POI hoặc traffic thay thế.",
      confidence: "none",
    };
  }
  // Nhánh FULL/PARTIAL: chỉ code khi có trip_fare_vnd, destination_distribution thật.
  // KHÔNG viết nhánh "tạm dùng proxy" — nếu làm vậy sẽ vi phạm luật vàng ở Mục 1.
  ...
}
```

**Việc engine ĐƯỢC làm ngay bây giờ dù thiếu dữ liệu:** định nghĩa sẵn interface đầu ra (`TripValueCandidate { areaId, expectedNetValueVnd, sourceConfidence }`) và một scorer stub có unit test khẳng định nó luôn trả `insufficient_data` cho tới khi input có trường `trip_fare_vnd` hoặc `booking_rate` không null. Việc này để khi Data role cắm nguồn thật vào, chỉ sửa 1 file adapter, không đổi contract.

### 5.2 `maintain_position` — Giữ vị trí tốt

**Mode hiện tại: INSUFFICIENT**, nhưng có thể cung cấp **context phụ trợ, gắn nhãn rõ ràng là không phải xác suất cuốc**:

```ts
function scoreMaintainPosition(mode, areas, routingSamples): ObjectiveResult {
  if (mode === "INSUFFICIENT") {
    return {
      objective: "maintain_position",
      status: "insufficient_data",
      // Context tham khảo, KHÔNG xếp hạng, KHÔNG gọi là "vị trí tốt"
      contextOnly: areas.map((a) => ({
        areaId: a.id,
        poiDensityContext: a.poi_counts_by_category, // chỉ để tài xế đọc, không rank
        routingCaveat: "Mẫu routing hiện là profile driving, chưa xác nhận xe máy.",
      })),
      reasonForInsufficiency:
        "Chưa có dữ liệu điểm trả khách/phân bố destination đã được cấp phép.",
      confidence: "none",
    };
  }
  ...
}
```

Giao diện hiển thị khối này ở dạng "thông tin nền", tách biệt trực quan (ví dụ màu xám, icon khác) khỏi các khối có gợi ý thật, để tài xế không hiểu nhầm là khuyến nghị.

### 5.3 `rest_spot` — Gợi ý điểm chờ/nghỉ

**Mode hiện tại: PARTIAL.** Đây là mục tiêu có thể tạo giá trị thật nhất ở bản demo.

Thuật toán:

```ts
function scoreRestSpot(mode, poiCandidates, routingSamples, driverPos, prefs): ObjectiveResult {
  const REST_CATEGORIES = ["cafe", "gas_station", "parking", "rest_area", "toilet"]; // config, không hard-code rải rác

  const candidates = poiCandidates
    .filter((p) => REST_CATEGORIES.some((c) => p.categories.includes(c)))
    .map((p) => {
      const route = findRoutingSample(routingSamples, driverPos, p) ?? null;
      return {
        poiId: p.id,
        name: p.name,
        distanceM: route?.route_distance_m ?? null,
        durationS: route?.route_duration_s ?? null,
        verified: false, // luôn false cho tới khi có verified_at thật
      };
    })
    .filter((c) => c.distanceM !== null) // không xếp hạng ứng viên không có routing thật
    .sort((a, b) => a.durationS! - b.durationS!)
    .slice(0, 5);

  return {
    objective: "rest_spot",
    status: "partial",
    candidates,
    caveat:
      "Đây là ứng viên từ dữ liệu bản đồ (OSM/Overpass), CHƯA xác minh quyền dừng/đỗ, " +
      "giờ mở cửa hay phù hợp cho xe máy. Không phải điểm dừng an toàn/hợp pháp đã kiểm chứng.",
    confidence: "low",
  };
}
```

Lưu ý quan trọng: **loại bỏ, không giữ**, các POI không có `routing_sample` thật thay vì gán khoảng cách ước lượng bằng đường chim bay — vì catalog dữ liệu ghi rõ route mẫu chỉ có cho một số cặp điểm, không phải lưới đầy đủ. Nếu không có routing thật cho phần lớn ứng viên, `candidates` có thể rỗng hoặc rất ngắn — đó là hành vi đúng, không phải bug.

### 5.4 `safety_comfort` — An toàn, đỡ mệt (né mưa, kẹt xe)

**Mode hiện tại: PARTIAL** (chỉ có mưa; traffic `missing`).

```ts
// Config riêng, KHÔNG hard-code trong logic — để nhóm chỉnh sau khi có Engine/nhóm chốt
const RAIN_TOLERANCE_THRESHOLDS: Record<RainToleranceLevel, { probPct: number; mm: number }> = {
  low:    { probPct: 30, mm: 0.5 },  // [Đề xuất tạm — chưa hiệu chỉnh]
  medium: { probPct: 55, mm: 2.0 },  // [Đề xuất tạm — chưa hiệu chỉnh]
  high:   { probPct: 75, mm: 5.0 },  // [Đề xuất tạm — chưa hiệu chỉnh]
};

function scoreSafetyComfort(mode, hourlyWeather, driverPrefs, dataStatus): ObjectiveResult {
  const threshold = RAIN_TOLERANCE_THRESHOLDS[driverPrefs.rain_tolerance_level];
  const relevantHours = hourlyWeather.filter((h) => isWithinPlanningHorizon(h.valid_time));

  const rainFlags = relevantHours
    .filter((h) => h.precipitation_probability_pct !== null)
    .map((h) => ({
      validTime: h.valid_time,
      probPct: h.precipitation_probability_pct,
      mm: h.precipitation_mm,
      exceedsTolerance:
        (h.precipitation_probability_pct ?? 0) >= threshold.probPct ||
        (h.precipitation_mm ?? 0) >= threshold.mm,
    }));

  const trafficStatus = dataStatus["traffic"]; // "missing" hiện tại

  return {
    objective: "safety_comfort",
    status: "partial",
    rainFlags,
    trafficNote:
      trafficStatus === "missing"
        ? "Chưa có dữ liệu giao thông thời gian thực; không thể đánh giá kẹt xe."
        : undefined,
    caveat:
      "Chỉ dựa trên dự báo mưa theo khu vực/giờ, KHÔNG tính mệt từ nhiệt/UV/gió " +
      "vì các biến này chưa nằm trong input.",
    confidence: "low",
  };
}
```

---

## 6. Explanation Layer — quy tắc bắt buộc

Mỗi câu giải thích sinh ra phải theo khuôn: **[hành động/nhận định] + [con số cụ thể] + [nguồn số đó]**.

Ví dụ đúng:
> "Quán cà phê X cách vị trí hiện tại 850m (~4 phút theo mẫu routing), thuộc nhóm ứng viên nghỉ chưa xác minh quyền đỗ."

Ví dụ sai (cấm):
> "Khu vực này thường có nhiều khách hơn." *(không truy được về số nào — cấm)*

Với các objective ở trạng thái `insufficient_data`, câu giải thích bắt buộc phải nói **rõ đang thiếu nhóm dữ liệu nào**, lấy nguyên văn từ `reasonForInsufficiency`, không được viết lại thành câu mơ hồ như "chưa tối ưu được".

---

## 7. Uncertainty & Confidence — bảng quy chiếu bắt buộc dùng trong UI

| `data_status` / `objective_readiness` | `confidence` hiển thị | Cách UI xử lý |
|---|---|---|
| `available` (đã qua kiểm tra valid_time/phạm vi) | `medium` | Hiển thị bình thường, có badge "dữ liệu forecast" |
| `partial` | `low` | Hiển thị kèm banner caveat màu vàng, không dùng ngôn từ khẳng định ("chắc chắn", "tốt nhất") |
| `missing` / `stale` / `not_integrated` / `insufficient_data` | `none` | Không hiển thị số liệu/ranking; chỉ hiển thị lý do thiếu + trạng thái xám |

Câu chốt bắt buộc ở cuối mỗi lần chạy: *"Đây là gợi ý dựa trên dữ liệu hiện có, không phải quyết định thay bạn — hãy tự kiểm tra trước khi hành động, đặc biệt với các mục còn đang thiếu dữ liệu."*

---

## 8. Interface tổng ("hợp đồng" cho AI code)

```ts
type ObjectiveKey = "max_trip_value" | "maintain_position" | "rest_spot" | "safety_comfort";
type Confidence = "none" | "low" | "medium";

interface EngineInput {
  weather: { hourly: WeatherHour[] };
  areas: AreaSample[];
  traffic: TrafficEdge[]; // rỗng ở bản hiện tại
  data_status: Record<DataGroupKey, "available" | "partial" | "missing" | "stale" | "not_integrated">;
  objective_readiness: Record<ObjectiveKey, "available" | "partial" | "insufficient_data">;
}

interface DriverContext {
  currentLat: number;
  currentLng: number;
  idleDurationMin: number;
  horizonMin: number;
  maxRepositionKm: number;
}

interface DriverPreferences {
  rain_tolerance_level: "low" | "medium" | "high";
  goal_weights?: Partial<Record<ObjectiveKey, number>>; // cá nhân hóa hiển thị, KHÔNG dùng để gộp điểm thành 1 số
}

interface ObjectiveResult {
  objective: ObjectiveKey;
  status: "available" | "partial" | "insufficient_data";
  confidence: Confidence;
  candidates?: unknown[]; // kiểu cụ thể theo từng objective, xem Mục 5
  caveat?: string;
  reasonForInsufficiency?: string;
}

interface DriverRecommendationOutput {
  generatedAt: string;
  objectives: Record<ObjectiveKey, ObjectiveResult>;
  assumptionsUsed: string[];
  finalNote: string; // câu chốt Mục 7
}

function runDriverEngine(
  input: EngineInput,
  ctx: DriverContext,
  prefs: DriverPreferences
): DriverRecommendationOutput;
```

---

## 9. Kế hoạch kiểm thử tự động (bắt buộc, giống tinh thần "engine tất định")

1. **Test tất định:** cùng input → gọi `runDriverEngine` 2 lần → output phải giống hệt (deep equal).
2. **Test phản ứng đầu vào:** đổi `rain_tolerance_level` từ `low` → `high` → số hour bị `exceedsTolerance=true` phải giảm hoặc bằng, không được tăng.
3. **Test luật vàng (không tự bù 0):** với mọi objective, nếu `objective_readiness` = `insufficient_data`, `candidates` phải rỗng và `status` phải đúng bằng `"insufficient_data"` — viết test snapshot cho từng objective.
4. **Test không suy diễn chéo:** nếu `data_status.traffic === "missing"`, `safety_comfort` không được chứa bất kỳ trường nào tên có "traffic" với giá trị số — chỉ được có `trafficNote` dạng string.
5. **Test rest_spot không ước lượng khoảng cách giả:** mọi candidate trong `rest_spot` phải có `distanceM` lấy từ `routing_samples` thật, không có fallback haversine ẩn.
6. **Test giải thích truy được về số:** parse chuỗi giải thích, đối chiếu con số xuất hiện trong câu với giá trị tương ứng trong input/tính toán — nếu lệch, test fail.

Đề xuất: viết một script `npm run engine:verify` chạy toàn bộ input mẫu (`hcmc_demo_snapshot.json` + các biến thể) và in bảng kết quả, giống cách nhóm TDA đã làm — ban giám khảo rất thích bằng chứng "đổi input thì output đổi, không phải bảng tra cứng".

---

## 10. Lộ trình cắm dữ liệu thật (không đổi lõi engine)

| Giai đoạn | Việc cần làm | File cần sửa |
|---|---|---|
| Có traffic thật (Goong/TomTom) | Thêm adapter chuẩn hóa vào `TrafficEdge[]`, đổi `data_status.traffic` → `available`/`partial` | Chỉ file adapter + cập nhật `OBJECTIVE_DATA_DEPENDENCIES` nếu cần |
| Có booking/dropoff data hợp lệ | Bật nhánh FULL/PARTIAL cho `maintain_position`, `max_trip_value` | Chỉ 2 scorer tương ứng trong Mục 5.1/5.2 |
| Có fare/trip value data | Bật `TripValueCandidate` thật thay stub | Scorer 5.1 + interface `candidates` |
| Xác minh thực địa điểm chờ | Set `verified: true`, thêm `opening_hours`, `parking_allowed` | Data layer, không đụng scorer |

Nguyên tắc xuyên suốt: **layer 2–5 (Readiness Gate → Explanation → Uncertainty → Output) không bao giờ bị sửa khi thay nguồn dữ liệu** — chỉ Input Layer và từng scorer riêng lẻ thay đổi. Đây là bằng chứng kiến trúc tách nguồn dữ liệu khỏi engine, đúng tinh thần chấm điểm "chiến lược dữ liệu hợp lý".

---

## 11. Rủi ro cần lưu ý khi code

| Rủi ro | Biện pháp trong code |
|---|---|
| Dev vô tình dùng `?? 0` cho trường null (biến thiếu thành 0) | Bật `strictNullChecks`; lint rule cấm `?? 0` / `|| 0` trên các trường có type `number \| null` lấy từ `EngineInput` |
| Gộp nhầm 4 objective thành 1 điểm tổng | Không định nghĩa `overallScore` ở bất kỳ đâu trong type; review code phải từ chối PR nào thêm trường này |
| Ước lượng khoảng cách bằng haversine khi không có routing thật, rồi hiển thị như thật | Test ở Mục 9.5 chặn việc này |
| UI hiển thị `insufficient_data` như một kết quả "0 gợi ý" khiến tài xế tưởng là không có gì quanh đó | Copy UI phải phân biệt rõ "chưa đủ dữ liệu để nói" khác với "không có gì" |

---

## 12. Vì sao thiết kế này đáp ứng tiêu chí chấm (tiêu chí 4 — 20đ)

- **Chiến lược dữ liệu hợp lý (5đ):** Readiness Gate + bảng `OBJECTIVE_DATA_DEPENDENCIES` là chiến lược tường minh, không suy diễn ngầm.
- **Khai thác dữ liệu không gian/thời gian/bên thứ ba (5đ):** dùng đúng `valid_time`, tọa độ POI, routing sample theo đúng phạm vi được ghi trong catalog.
- **AI dùng phù hợp, có giải thích, nêu rõ giới hạn (10đ):** mỗi objective có scorer riêng, explanation truy được về số, và với 2/4 mục tiêu hiện chưa đủ dữ liệu, hệ thống **nói thẳng** thay vì giả vờ — đây là điểm khác biệt so với việc tô vẽ một demo "đẹp nhưng bịa".