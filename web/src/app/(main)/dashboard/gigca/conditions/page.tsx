import { ConditionsPanel } from "../../_components/gigca/conditions-panel";
export const metadata = { title: "Mưa & giao thông | GigCa" };
export default function Page() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-medium text-xl">Mưa & giao thông</h1>
      <ConditionsPanel />
    </div>
  );
}
