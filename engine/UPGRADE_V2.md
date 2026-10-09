# Decision Engine v2 — nâng cấp từ "ngây thơ" lên có cơ sở

Tài liệu này ghi lại **cái gì đã đổi, vì sao, và chỉnh ở đâu**. Nguyên tắc dự án (`RULES.md`, `spec.md` §2) giữ nguyên:
4 hướng độc lập, không điểm tổng, thiếu dữ liệu ≠ 0, mọi con số phải truy vết được.

## 1. Các lỗi của bản cũ đã được sửa

| # | Bản cũ | Bản v2 |
|---|--------|--------|
| 1 | Thời tiết: lấy N phần tử **đầu danh sách** (snapshot demo → đánh giá 00:00–03:00 dù đang 17:20) | Neo theo `generated_at`; khung `[now, now+horizon]`; đo độ phủ dự báo (`weather.py`) |
| 2 | Giá trị mưa ở `T` coi như "từ T"; docs ghi Open-Meteo là **giờ trước T** | `weather.slot_convention` (mặc định `preceding_hour`, theo `docs/06_DATA_CATALOG`) |
| 3 | Không có dự báo phủ khung giờ ⇒ báo `THOI_TIET_THUAN_LOI` | Báo `KHONG_DU_DU_BAO`, không kết luận "thuận lợi" |
| 4 | Thiếu traffic ⇒ **bịa** hành lang "Lê Duẩn – Pasteur", "Võ Văn Kiệt" | Hành lang/vùng né chỉ lấy từ đoạn đường thật; thiếu dữ liệu ⇒ `None` + nói rõ |
| 5 | Traffic phân loại theo ngưỡng tuyệt đối 25/18 km/h, không lọc dữ liệu cũ | Tỷ lệ `current/free_flow`, lọc `observed_at` cũ (`traffic.max_age_min`) |
| 6 | Thiếu trường ⇒ tự điền `duration=25`, `demand=1.0`, `wait=10`, `favorable=70`, cước `6500đ/km` | Khu vực thiếu trường bắt buộc bị **loại kèm lý do** (`ObjectiveResult.excluded`) |
| 7 | Vị trí tài xế **không được dùng** (`current_lat/lng`, `max_reposition_km` bỏ không) | Chi phí/thời gian dịch chuyển ước tính, loại khu vực ngoài bán kính (`geo.py`) |
| 8 | Xếp hạng khu vực theo cước thô nhân hệ số tự chế | Năng suất ước tính **đ/giờ** = (cước ròng − chi phí dịch chuyển) / giờ (chạy + dịch chuyển + chờ) |
| 9 | FULL mode ⇒ **tự gán** `verified=True`, `parking_allowed=True` cho mọi POI | Chỉ theo cờ trong dữ liệu; POI đã xác minh luôn xếp trên chưa xác minh |
| 10 | Ghép mẫu routing của **bất kỳ** khu vực nào làm khoảng cách của tài xế | Chỉ dùng mẫu xuất phát trong `routing.origin_tolerance_m` quanh tài xế |
| 11 | Không kiểm tra giờ mở cửa | Loại điểm đóng cửa lúc tới nơi; giờ không đọc được ⇒ "không rõ", không đoán |
| 12 | Plan chứa khẳng định vô căn cứ ("surge", "20–25 km/h", "đã xác minh thực địa" cả khi chưa) | Câu chữ sinh từ số liệu thật; bỏ các khẳng định không có nguồn |
| 13 | Adapter tự chèn **POI mock** vào snapshot thật; POI thiếu tọa độ thành (0,0) | Không chèn ngầm; POI thiếu tọa độ bị bỏ và ghi lại |
| 14 | `assumptions` là 5 câu cố định (kể cả nói "chưa có traffic" khi có) | Sinh động theo `data_status` + lý do + tham số đang dùng; gắn nhãn dữ liệu demo |
| 15 | `goal_weights` khai báo nhưng không dùng | Dùng để sắp thứ tự (không thành điểm tổng) |
| 16 | Config lỗi ⇒ `except: pass`, lặng lẽ dùng mặc định | Lỗi JSON/tham số phi lý ⇒ báo lỗi rõ (`validate_config`) |

## 2. Thành phần mới

- **Độ vững (`robustness.py`)** — mọi bảng xếp hạng được thử lại khi từng tham số giả định dao động ±`robustness.perturbation_pct`
  (một tham số một lần, tất định, không random). Kết quả ở `ObjectiveResult.robustness`:
  `top1_share`, `margin_pct`, `stable`, `contested`, `flips_to`. Câu diễn giải được đưa vào `caveat`/`trade_offs`.
  *Confidence vẫn theo bảng trạng thái của spec §7; độ vững là thông tin bổ sung, không tự hạ confidence.*
- **Thứ tự xem xét 4 hướng (`priority.py`)** — `DriverRecommendationOutput.direction_priority`, luật rõ ràng, mỗi dòng có `reason`:
  mưa vượt ngưỡng sắp tới (≤ `priority.rain_lead_min`) → nghỉ khi chờ ≥ `priority.fatigue_idle_min` → mưa còn xa trong horizon →
  hai hướng kiếm tiền theo `goal_weights` → còn lại. Hướng thiếu dữ liệu không xếp hạng. **Đây là thứ tự, không phải điểm tổng.**
- **Kiểm tra đầu vào (`validation.py`)** — context sai (tọa độ, horizon ≤ 0, weight âm) ⇒ `ValueError`; dữ liệu xấu
  (trùng id, tọa độ sai, `available` nhưng rỗng…) ⇒ `data_quality_warnings`.
- **Pareto (max_trip_value)** — `pareto_optimal` cho biết khu vực có bị khu vực khác vượt trội đồng thời về năng suất **và** P10 của năng suất (v4; trước đây dùng `demand_index` của sàn, đã bỏ vì không kiểm chứng được).

## 3. Chỉnh tham số ở đâu

Tất cả ở `config/engine_config.json` (deep-merge lên mặc định trong `engine/src/config.py`; chỉ cần ghi khóa muốn đổi).
Mọi số đều là **đề xuất tạm, chưa hiệu chỉnh** — cần đối chiếu dữ liệu thực trước khi tin.

| Nhóm | Khóa chính |
|------|-----------|
| Dịch chuyển | `geo.detour_factor`, `geo.reposition_speed_kmh`, `geo.reposition_cost_vnd_per_km`, `geo.at_area_radius_m` |
| Routing | `routing.origin_tolerance_m` |
| Thời tiết | `weather.slot_convention`, `weather.min_coverage_ratio`, `weather.heavy_mm_ratio`, `weather.pre_rain_buffer_min`, `weather.area_scope_km` |
| Giao thông | `traffic.smooth_ratio`, `traffic.congested_ratio`, `traffic.max_age_min` |
| Hướng 1/2 | `max_trip_value.*`, `maintain_position.wait_penalty_per_min`, `maintain_position.reposition_penalty_per_km` |
| Điểm nghỉ | `rest_spot.weights`, `travel_time_ref_s`, `category_fit_*`, `tier_cutoffs`, `rest_duration_min_by_idle`, `category_aliases`, `amenity_tags` |
| Độ vững / thứ tự | `robustness.*`, `priority.*` |

## 4. Tương thích ngược & thay đổi hành vi cần biết

- Chỉ **thêm** trường có mặc định vào các dataclass; chữ ký hàm chỉ thêm tham số tùy chọn. Code gọi cũ vẫn chạy.
- `rest_spot` không còn ứng viên nào ⇒ `insufficient_data` (trước: `available/partial` với danh sách rỗng).
- `load_engine_input_from_dict` không còn chèn POI mock khi snapshot không có `pois`.
- `weather_hourly` cấp snapshot (nếu có) được ưu tiên; nếu không, dùng điểm mẫu khu vực **gần tài xế nhất trong `area_scope_km`**.
- Một test cũ (`test_safety_plan_immediate_heavy_rain`) được đổi mốc `14:00 → 15:00` vì ngữ nghĩa "giờ trước" của Open-Meteo (xem mục 1 #2).
- (v4) Hướng 1/2 chỉ dùng `driver_profile`, `trip_log`, `wait_spells` do tài xế cung cấp; các trường thị trường (`net_value_vnd`, `demand_index`, `favorable_dropoff_pct`, `avg_next_wait_min`…) bị adapter xóa.

## 5. Giới hạn còn lại (nói thẳng)

- Ngưỡng/trọng số vẫn là giả định; v2 làm chúng **hiển thị và kiểm được độ nhạy**, chưa hiệu chỉnh được (cần log cuốc thật).
- Dịch chuyển giữa các khu vực là ước tính đường chim bay × hệ số, không phải routing thật.
- Không dự báo xác suất có cuốc; không có dữ liệu gió/nhiệt/ngập/sự cố.
- Thời gian chờ tính từ đợt chờ thật của tài xế (survival); cần app companion/GPS để ghi `wait_spells`.

## 6. Chạy kiểm tra

```bash
python -m pytest engine/tests -q          # hoặc: python -m unittest discover -s engine/tests -t .
python scripts/verify_engine.py           # 4 kịch bản, gồm phản ứng theo vị trí / thời gian chờ
```
