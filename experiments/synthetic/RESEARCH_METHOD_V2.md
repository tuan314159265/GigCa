# Thiết kế sinh dữ liệu GigCa v2 — 14/10/2026

## Phạm vi và cơ sở

Đây là mô phỏng giả thuyết có persona do LLM đề xuất và simulator tuần tự. Không phải tái lập đầy đủ ba nghiên cứu, không phải dữ liệu đại diện dân số tài xế TP.HCM. Prompt tiếng Anh giúp ghi rõ yêu cầu; chưa có thí nghiệm chứng minh tiếng Anh tốt hơn tiếng Việt.

1. [Wang et al., LLMob, NeurIPS 2024](https://arxiv.org/html/2402.14744v3): mục 3.1–3.2 tách thói quen và động cơ, lấy lịch sử làm căn cứ và chọn pattern qua self-consistency; phụ lục B trình bày prompt, C.4 persona. GigCa mượn ý tưởng điều kiện theo routine/persona. Hiện không có lịch sử thật để căn chỉnh, không thực hiện retrieval hay lựa chọn pattern như bài. Mục 4.1 so sánh phân bố khoảng cách, thời gian và lượt thăm không gian-thời gian bằng JSD; có thể áp dụng khi có tập tham chiếu thật.

2. [Park et al., Generative Agents, UIST 2023](https://arxiv.org/html/2304.03442v2): mục 4 mô tả memory retrieval, reflection và planning. GigCa yêu cầu persona có routine/motivation nhất quán với tham số. Câu mô tả motivation hiện chỉ là metadata, chưa tác động simulator; không gọi đó là bộ nhớ hoặc phản tư đã triển khai.

3. [Why LLMs Are Bad at Synthetic Table Generation, arXiv:2406.14541v3](https://arxiv.org/html/2406.14541v3): mục 4 sử dụng functional dependencies để thiết kế permutation-aided fine-tuning (PAFT). GigCa lấy bài học phải kiểm tra phụ thuộc giữa trường và giao phép tính tiền/thời gian cho simulator. Không huấn luyện PAFT, không suy diễn rằng validator tương đương PAFT hoặc bảo đảm fidelity.

Các bài trên không cung cấp các ngưỡng tham số tài xế TP.HCM dưới đây. Tất cả bounds vẫn là giả định nghiên cứu.

## Thiết kế phủ nhóm

Thiết kế factorial 2×2×2×2 = 16 cell:

| Trục | Nhóm 1 | Nhóm 2 |
|---|---|---|
| Ca | Sáng, bắt đầu 6–8h | Chiều, bắt đầu 13–15h |
| Thời lượng | Bán thời gian 3–4,5h | Toàn thời gian 7–8h |
| Chính sách chờ | Kiên nhẫn 25–45 phút; xác suất chuyển .15–.35 | Chờ 7–15 phút; xác suất chuyển .65–.85 |
| Phản ứng mưa | Tránh mưa, ngưỡng .4–1.5mm | Chấp nhận mưa, ngưỡng 4–8mm |

Đơn vị ngưỡng mưa kế thừa simulator, không được xác thực như một ngưỡng an toàn. Hai tài xế mỗi cell → 32 tài xế. Bán kính đón luân phiên 100–300, 350–650, 750–1100m và home zone xoay qua 6 điểm neo. Đây là biến phụ, không tuyên bố phủ toàn bộ tích Descartes của mọi thuộc tính. Giá nhiên liệu/tỷ lệ chia tiền/đặc điểm xe không phải nhóm nhân khẩu học.

32 là số đủ phủ thiết kế này với hai biến thể, không phải kết quả power analysis. 16 là tối thiểu một người mỗi cell; 48 là ba người mỗi cell, có ích kiểm tra nhạy hơn. Không bảo đảm mỗi người đủ số event/chu kỳ cho engine. Nhiều cuốc của cùng một người không tương đương nhiều người độc lập.

## Prompt và kiểm tra

Prompt chuẩn được tạo bởi `cohort_prompt` trong cohort.py, lưu nguyên văn ở từng batch-XX.prompt.json. System yêu cầu giả thuyết rõ ràng, không tạo bằng chứng thực nghiệm; user cung cấp exact ID, home zone, bounds riêng từng cell, schema và các ràng buộc chéo.

Mỗi batch 4 người. Validator kiểm tra schema, ID/order, home/preferred zones, bounds và không trùng toàn bộ tham số giữa hai bản sao trong cell. Không dùng tự đánh giá LLM thay cho validator. Tính nhất quán ngữ nghĩa của description với số chỉ được prompt yêu cầu, chưa có phép đo độc lập; không báo là đã tự động xác minh đầy đủ.

Phản hồi có schema hợp lệ được lưu để audit; lỗi cell sẽ dừng, không tự gọi lại tốn phí hoặc âm thầm sửa số. Provenance lưu provider/model/usage/hash prompt và design; key không được ghi ra file. Giữ dữ liệu cũ, dataset mới có thư mục riêng.

## Sinh và đánh giá

```powershell
python -m experiments.synthetic.cohort --replicates 2 --output .cache/synthetic/my-v2
python -m experiments.synthetic generate --personas .cache/synthetic/my-v2/personas.json --days 42 --seed 7 --output .cache/synthetic/my-v2/contextual-seed7
python -m experiments.synthetic evaluate .cache/synthetic/my-v2/contextual-seed7
```

`--plan-only` xuất thiết kế và prompt, không gọi API. Sinh persona có phí provider; sinh nhật ký là offline. Không thêm persona vào DB thật; các record giữ source_kind=synthetic.

Đánh giá tiếp theo: cùng personas, chạy contextual/null/drift với nhiều seed; báo cả thiếu mẫu và model giữ baseline. So sánh persona thủ công/ngẫu nhiên/LLM để đo đóng góp của LLM. Các bản lặp seed phải được tổng hợp theo tài xế/cell, không coi mọi chuyến độc lập. Cần dữ liệu thật để kiểm tra phân bố và train-synthetic/test-real; không kết luận fidelity chỉ từ điểm ML trên simulator.

Simulator vẫn dùng weather giả lập, Weibull chưa fit từ chờ thật, routing haversine×1.3 và tariff cấu hình. Prompt mới không sửa các giới hạn này. Code khớp engine về cấu trúc; đi đón dài có thể không ghép được theo quy tắc hiện tại, phải báo tỷ lệ ghép thay vì làm sai timestamp để tăng mẫu.
