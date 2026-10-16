# GigCa frontend

Next.js 16 / React 19 / TypeScript / Tailwind 4, Leaflet, shadcn/Radix.
Theme xanh #00BF63, trắng và vàng #FFBD59. Kế thừa StudioAdmin; giữ [LICENSE](LICENSE) và attribution bản đồ.

Chạy backend theo [README chính](../README.md), rồi với Node.js 22:

~~~powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
~~~

GIGCA_API_URL mặc định http://127.0.0.1:8000. NEXT_PUBLIC_GIGCA_PREVIEW=false cho live;
preview chỉ dùng fixture, đăng nhập vẫn cần backend. Key provider chỉ nằm ở backend.

Routes: /auth/register, /auth/login, /dashboard/gigca; các trang chi tiết map, conditions, sources.
BFF giữ token trong cookie HttpOnly. Production Docker theo Compose ở root.

~~~powershell
npx tsc --noEmit
npm run build
node scripts/test-route-presentation.cjs
node scripts/test-visible-poll.cjs
node scripts/test-weather-timeline.cjs
~~~

Không commit .env.local, .next, node_modules hoặc tsbuildinfo.
