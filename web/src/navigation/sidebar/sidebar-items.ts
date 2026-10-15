import { CloudRain, Database, LayoutDashboard, MapPinned, type LucideIcon } from "lucide-react";

export type NavBadge = "new" | "soon";

export interface NavSubItem {
  id: string;
  title: string;
  url: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
}

interface NavItemBase {
  id: string;
  title: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
}

export interface NavMainLinkItem extends NavItemBase {
  url: string;
  subItems?: never;
}

export interface NavMainParentItem extends NavItemBase {
  subItems: NavSubItem[];
}

export type NavMainItem = NavMainLinkItem | NavMainParentItem;

export interface NavGroup {
  id: number;
  label?: string;
  items: NavMainItem[];
}

export const sidebarItems: NavGroup[] = [
  {
    id: 1,
    label: "GigCa",
    items: [
      { id: "gigca", title: "Gợi ý cho tôi", url: "/dashboard/gigca", icon: LayoutDashboard },
      { id: "gigca-map", title: "Bản đồ & điểm chờ", url: "/dashboard/gigca/map", icon: MapPinned },
      { id: "gigca-conditions", title: "Mưa & giao thông", url: "/dashboard/gigca/conditions", icon: CloudRain },
      { id: "gigca-sources", title: "Nguồn dữ liệu", url: "/dashboard/gigca/sources", icon: Database },
    ],
  },
];
