# Báo cáo: biểu diễn mức ùn tắc bằng chỉ số liên tục

**Ngày:** 05/10/2026
**Phạm vi:** Data → Decision Engine, tín hiệu tốc độ TomTom Flow
**Trạng thái:** Data đã xuất tốc độ thô theo `traffic[]`; Engine implementation đã được làm trên branch `feat/traffic-ci-continuous` từ `origin/engine`.

## Kết luận

Dữ liệu traffic gốc không phải one-hot. TomTom Flow cung cấp tốc độ hiện tại và tốc độ tự do dưới dạng số; mẫu đã thử là 16 và 26 km/h. Engine hiện tính `speed_ratio = current_speed / free_flow_speed`, sau đó gán nhãn:

| Điều kiện hiện tại trong Engine | Nhãn |
|---|---|
| `speed_ratio >= 0.8` | Thông thoáng |
| `0.5 <= speed_ratio < 0.8` | Chậm |
| `speed_ratio < 0.5` | Ùn tắc |

Với mẫu `16/26`, tỷ lệ bằng khoảng `0.615`, nên Engine xếp nhãn **chậm**. Vì vậy phân loại rời rạc hiện nằm ở logic Engine; Data giữ tốc độ dạng số. Engine còn tính tốc độ/tỷ lệ trung bình, nhưng output chính hiện thiên về danh sách nhãn và chưa xuất CI riêng cho từng đoạn.

## Công thức đề xuất

Giữ một chỉ số liên tục trên mỗi đoạn:

```text
CI = max(0, (free_flow_speed_kmh - current_speed_kmh) / free_flow_speed_kmh)
```

Chỉ tính khi hai tốc độ có giá trị hợp lệ và `free_flow_speed_kmh > 0`; nếu thiếu thì CI là `null/unknown`, không thay bằng 0. Tốc độ hiện tại bằng hoặc cao hơn tốc độ tự do cho `CI = 0`. Với mẫu 16/26, `CI ≈ 0.385`.

Engine giữ CI cho xếp hạng/tổng hợp; các nhãn thông thoáng/chậm/ùn tắc chỉ là cách diễn đạt cho người dùng. Ngưỡng hiện có `speed_ratio=0.8/0.5` vẫn được giữ làm cấu hình ban đầu, chưa coi là ngưỡng đã hiệu chỉnh cho TP.HCM. Không chuyển ngay các ngưỡng trong bài báo thành ngưỡng production.

## Thay đổi Engine đã thực hiện

Trên branch `feat/traffic-ci-continuous`:

1. `engine/src/traffic.py` tính `congestion_index` liên tục cho từng segment đủ tốc độ; CI là `None` khi input thiếu/không hợp lệ.
2. Chi tiết segment được xếp CI giảm dần để tìm đoạn có CI cao; nhãn cũ vẫn tạo lời giải thích nhưng không thay CI.
3. Tổng hợp thêm `traffic_congestion_index_mean` và `traffic_congestion_index_aggregation` vào `key_metrics`. Chỉ dùng trung bình trọng số chiều dài nếu mọi segment có `length_m` hợp lệ; nếu không, ghi `segment_mean`.
4. `traffic_segments_by_congestion` xuất CI/tỷ lệ/tốc độ từng segment để UI/backend dùng giá trị liên tục.
5. Ngưỡng nhãn 0.8/0.5 chưa đổi, chưa được hiệu chỉnh ở TP.HCM. Không gọi một segment là hành lang an toàn, không suy ra traffic toàn vùng hay route né kẹt nếu chưa map-match và biết coverage.

Logic đặt ở traffic analysis (`engine/src/traffic.py`), không ở parser `engine/src/adapter.py`: parser tiếp tục chuẩn hóa input speed thô; analyzer áp cùng công thức cho cả dữ liệu qua JSON adapter lẫn `TrafficEdge` được tạo trực tiếp.

## Dữ liệu hiện có và giới hạn

- Data interface xuất `current_speed_kmh`, `free_flow_speed_kmh`, `observed_at` vào top-level `traffic[]`, tương thích với `TrafficEdge` Engine đã có. Snapshot DB mẫu hiện chưa có traffic observation nên mảng đang rỗng; phép thử trước đây với 16/26 là một segment thử runtime.
- Engine chỉ dùng các đoạn có timestamp trong 30 phút và tốc độ đủ dùng. Engine type hiện không nhận `confidence`, geometry hoặc incident trong `TrafficEdge`; Data không nên giả vờ các trường đó đã được Engine sử dụng.
- `edge_id` là ID segment provider khi chưa map-match, không phải tên đường hay cạnh mạng đường.
- Tốc độ tương đối không phải mật độ xe. Muốn ước lượng mật độ/lưu lượng cần dữ liệu flow (xe/giờ), occupancy hoặc feed/sensor phù hợp.
- Một điểm quan sát không đủ đại diện cho vùng/đường đi. Tổng hợp khu vực cần coverage và cách gộp được công bố; thiếu đoạn dữ liệu không được xem là đường thông thoáng.

## Nghiên cứu tham khảo

Stipancic và cộng sự tính Congestion Index từ tốc độ tự do và tốc độ quan sát, map-match GPS vào từng link đường, rồi tổng hợp theo thời gian. Nghiên cứu phân nhóm CI thành mức thấp/vừa/cao để trực quan hóa; nhóm tác giả cũng lọc số chuyến/quan sát tối thiểu trên mỗi link-hour để giảm nhiễu. Đây là cơ sở cho dạng chỉ số liên tục, không phải bằng chứng rằng các ngưỡng của nghiên cứu phù hợp với đường xe máy TP.HCM. [Bài báo, *Transportation Letters* (2019)](https://doi.org/10.1080/19427867.2017.1374022) · [Bản accepted manuscript](https://publications.polymtl.ca/2973/1/2019_Stipancic_Measuring_visualizing_space-time_congestion_patterns.pdf).

Geroliminis và Daganzo nghiên cứu Macroscopic Fundamental Diagram ở cấp mạng đô thị bằng dữ liệu flow/occupancy và chỉ ra phân bố không gian của mật độ ảnh hưởng đến quan hệ tổng hợp. Hướng này chỉ phù hợp nếu sau này có flow/occupancy đủ phủ; tốc độ TomTom đơn lẻ chưa đủ để áp dụng. [Bài báo, *Transportation Research Part B* (2011)](https://doi.org/10.1016/j.trb.2010.11.004).

## Phối hợp role

- **Data:** tiếp tục xuất giá trị tốc độ gốc, timestamp và provenance; không tự phân loại hay tính xác suất kẹt xe trong extractor. Khi nguồn cho phép và có dữ liệu, bổ sung coverage/map-match/confidence.
- **Decision model:** sở hữu công thức CI, ngưỡng hiển thị, cách xếp hạng và freshness handling.
- **Backend/Frontend:** khi Engine output được đổi, cập nhật API và UI để giữ giá trị số, nhãn, thời điểm dữ liệu và giới hạn coverage.

Theo `RULES.md`, Engine implementation thuộc role Decision model; tài liệu này ghi nhận quyết định và handoff, không sửa mã trong `engine/` trên branch Data.
