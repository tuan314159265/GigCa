# Nguồn dữ liệu cần kiểm chứng

Ghi nhận các nguồn nhóm đề xuất để đánh giá sau. Link tài liệu là điểm bắt đầu, không phải xác nhận rằng GigCa đã gọi API, có tài khoản/quota, được phép lưu cache, hoặc dữ liệu phủ đủ TP.HCM. Người phụ trách Data cập nhật trạng thái/ngày kiểm tra và kết quả thử nghiệm tại đây.

## Danh sách

| Nhà cung cấp | Dùng để đánh giá | Tài liệu/website | Trạng thái và việc cần kiểm chứng | JSON mẫu đã cào |
|---|---|---|---|---|
| Goong | Bản đồ/tiles, địa điểm/POI, directions và ma trận khoảng cách/thời gian | [Goong REST docs](https://docs.goong.io/rest/), [Distance Matrix](https://docs.goong.io/rest/distance_matrix/) | **Ứng viên routing nội địa.** Xác minh coverage TP.HCM, lựa chọn `vehicle` phù hợp xe máy (`bike`/`hd` nếu có), API key/quota/giá, traffic-aware hay không, quyền cache và attribution. API docs có tham số vehicle nhưng cần thử request thật trên các khu vực/đường đã biết. | Chưa cào: cần API key/quota và chọn endpoint. |
| OSRM | Routing/ma trận thời gian-khoảng cách trên dữ liệu OpenStreetMap | [OSRM API docs](https://project-osrm.org/docs/v5.24.0/api/), [Profiles](https://project-osrm.org/docs/v26.4.0/profiles) | **Đã cào mẫu route.** Public sample dùng profile `driving`, không xác nhận tuyến xe máy/live traffic. Kiểm tra server/profile, điều khoản public endpoint, giới hạn sử dụng, coverage, one-way/barrier và sai khác thực địa. | [Route mẫu (driving)](../data/samples/osrm_route_hcmc.json). |
| OpenWeather | Xác suất/lượng mưa hiện tại hoặc forecast theo thời gian | [Current Weather API](https://openweathermap.org/api/current), [API plans](https://openweathermap.org/api) | **Ứng viên thời tiết; chưa tích hợp.** Chỉ đánh giá dữ liệu mưa theo định hướng hiện tại. Cần API key; xác minh endpoint/plan, forecast horizon, quota/giá, coverage/độ trễ, attribution và quyền lưu/chia sẻ dữ liệu. | Chưa cào: cần API key và chốt plan. |
| Open-Meteo | Forecast theo giờ: lượng mưa và xác suất mưa | [Forecast API docs](https://open-meteo.com/en/docs), [Terms](https://open-meteo.com/en/terms) | **Đã cào forecast mẫu.** Free API không cần key nhưng chỉ dành cho non-commercial use theo terms; dữ liệu CC BY 4.0 cần attribution. Nếu sản phẩm thương mại, cần xác nhận gói/quyền dùng trước khi tiếp tục. Kiểm tra độ phù hợp của mô hình/khu vực, giờ cập nhật và sai số địa phương. | [Weather mẫu (48 giờ)](../data/samples/open_meteo_weather_hcmc.json). |
| TomTom | Traffic Flow/Incidents: tốc độ hiện tại, tốc độ thông thoáng, thời gian/độ trễ, sự cố | [TomTom Traffic API](https://developer.tomtom.com/traffic-api/documentation/product-information/introduction), [Market coverage](https://developer.tomtom.com/traffic-api/documentation/product-information/market-coverage) | **Ứng viên traffic realtime; chưa tích hợp.** Xác minh endpoint/credential, coverage đúng tại TP.HCM, road classes, quota/giá, độ mới, license và quyền cache/hiển thị. Không suy ra booking demand từ tốc độ đường. | Chưa cào: cần API key và xác minh coverage/điều khoản. |
| Cổng Giao thông TP.HCM | Tin điều tiết, tình trạng giao thông, camera và dữ liệu hiển thị trên cổng | [giaothong.hochiminhcity.gov.vn](https://giaothong.hochiminhcity.gov.vn/) | **Nguồn địa phương cần khảo sát.** Website công khai hiển thị trạng thái/tin/camera nhưng repo chưa xác định API công khai, định dạng máy đọc, quyền tự động thu thập/lưu trữ hay SLA. Không scrape/crawl trước khi tìm được API/chính sách rõ ràng; có thể liên hệ đơn vị quản lý. | Chưa cào: chưa xác định API/quyền crawl. |
| OpenStreetMap + Overpass | POI/map features; dữ liệu đường nền để chuẩn bị graph | [Overpass API guide](https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide), [Overpass usage guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html), [OSM license FAQ](https://osmfoundation.org/wiki/Licence_and_Legal_FAQ) | **Đã cào mẫu POI.** OSM data theo ODbL; giữ attribution và đánh giá nghĩa vụ share-alike nếu phân phối database dẫn xuất. Overpass public instance phù hợp request vừa phải, không làm backend realtime/khối lượng lớn. Map tiles có chính sách riêng; không mặc định dùng tile server của OSM làm tile production. | [POI mẫu (920 kết quả)](../data/samples/osm_overpass_pois_hcmc.json). |

## Tiêu chí chốt provider

1. Coverage TP.HCM và tính đúng cho xe máy: đường một chiều, cấm/rào chắn, cầu/hầm và điểm quay đầu.
2. Có trường dữ liệu cần thiết, timestamp/độ mới, mô tả confidence và phân biệt forecast với observation.
3. Phí, quota, rate limits, API key, SLA, cache/retention, attribution, hiển thị và quyền sử dụng trong bài demo/sản phẩm.
4. Kiểm tra bằng một bộ tọa độ/đoạn đường mẫu tại nhiều khu vực, giờ cao điểm và thấp điểm; ghi lại response đã loại bí mật, lỗi và kết quả so với quan sát.
5. Có phương án khi API lỗi: snapshot còn hạn hoặc đánh dấu thiếu dữ liệu. Không thay traffic observation bằng routing duration rồi gọi là traffic realtime.

## Trạng thái hiện tại

- **Đã có JSON theo nguồn:** Open-Meteo weather, OSM/Overpass POI và OSRM route; link trực tiếp ở cột cuối.
- **Chưa có:** Goong, OpenWeather, TomTom, cổng giao thông, sự kiện và nguồn booking/giá/mật độ xe.
- Các nguồn chưa cào được ghi lý do tại cột cuối; không tạo fixture giả thay cho dữ liệu provider.
- Snapshot mẫu là ảnh chụp tại một điểm và bán kính nhỏ, không đại diện toàn TP.HCM, không phải kiểm định độ chính xác hay khuyến nghị vận hành.
