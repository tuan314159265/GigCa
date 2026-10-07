import type { Metadata } from "next";
import { GigcaDashboard } from "./_components/gigca-dashboard";
export const metadata: Metadata = {
  title: "Gợi ý cho tôi | GigCa",
  description: "Gợi ý điểm chờ, nghỉ ngơi và di chuyển cho tài xế.",
  alternates: { canonical: "/dashboard/gigca" },
};
export default function Page() { return <GigcaDashboard />; }
