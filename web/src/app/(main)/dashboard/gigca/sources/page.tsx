import { SourcesPanel } from "../../_components/gigca/sources-panel";
export const metadata = { title: "Nguồn dữ liệu | GigCa" };
export default function Page() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-medium text-xl">Nguồn dữ liệu</h1>
      <SourcesPanel />
    </div>
  );
}
