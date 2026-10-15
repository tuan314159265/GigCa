# GigCa frontend

Frontend chính của GigCa, dựa trên StudioAdmin Logistics. Giữ component shadcn/UI và LICENSE template.

- FE: thư mục này; chạy `npm ci`, rồi `npm run dev -- --hostname 127.0.0.1 --port 3000`.
- BE: `../api/`; chạy `python -m api.v1_server` từ root repo.
- Đặt NEXT_PUBLIC_GIGCA_PREVIEW=false trong .env.local để nhận dữ liệu theo GPS; true để preview.
- Cấu hình key provider trong .env ở root repo, không đặt trong frontend.

Xem [hướng dẫn repo](../docs/REPOSITORY_GUIDE.md), [luồng live](../docs/LIVE_RUN.md). Các trang demo upstream đã được xóa; chỉ giữ trang GigCa và thư viện component/layout dùng chung. Bản gốc nằm ngoài repo tại studio-admin-original.
