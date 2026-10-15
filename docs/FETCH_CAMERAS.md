# Xuất danh mục camera công khai TP.HCM

Chạy từ root GigCa, chỉ cần Python standard library:

```powershell
python scripts/fetch_public_cameras.py
```

File mặc định: `data/raw/cameras/hcmc-public-cameras.json` (gitignored).

```powershell
python scripts/fetch_public_cameras.py --output data/raw/cameras/catalog.json
```

Script mở Map.aspx để nhận cookie phiên công khai, rồi gọi đúng SearchQuery mà public/global.js dùng: lớp CAMERA, Publish:true, limit=-1. Không đăng nhập, đoán ID hay vượt xác thực. Response AjaxPro được đọc bằng parser dữ liệu, không eval JavaScript. Nếu bị chặn, trả lỗi hoặc không tìm thấy bản ghi, script thoát với mã 1 và không ghi đè file cũ.

File gồm ID camera, node/data ID, tên, tọa độ WGS84 từ Location.Shape, trạng thái do nguồn báo và bản ghi gốc. Giữ bản ghi thiếu tọa độ với null; không tự geocode đoán vị trí. File có count, with_coordinates và reported_up_count. CamStatus=UP chỉ là trạng thái nguồn công bố; script không kiểm tra ảnh và không khẳng định camera đang phát ảnh mới. Chưa xác minh danh sách bao phủ toàn bộ camera TP.HCM.

Nếu Python MSYS trên máy này thiếu CA, dùng file trust local đã thiết lập trước:

```powershell
$env:SSL_CERT_FILE='D:/HCMUT/STUDY/261/Gigca/GigCa/.cache/windows-roots.pem'
python scripts/fetch_public_cameras.py
```

Không tắt xác minh TLS. Máy khác/Docker dùng CA phù hợp môi trường đó. Dữ liệu camera chưa được nối vào dashboard; script này chỉ xuất danh mục để làm bước tích hợp tiếp theo. Điều kiện sử dụng/lưu/chia sẻ dữ liệu cần kiểm tra trước khi triển khai sản phẩm.
