"use client";
import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Command, LayoutGrid, MapPin, CloudRain, Database, UserRound } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { usePreferencesStore } from "@/stores/preferences/preferences-provider";

const links = [
  { title: "Gợi ý", href: "/dashboard/gigca", icon: LayoutGrid },
  { title: "Bản đồ", href: "/dashboard/gigca/map", icon: MapPin },
  { title: "Điều kiện", href: "/dashboard/gigca/conditions", icon: CloudRain },
  { title: "Dữ liệu", href: "/dashboard/gigca/sources", icon: Database },
];
export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const path = usePathname();
  const setPreference = usePreferencesStore((state) => state.setPreference);
  const synced = usePreferencesStore((state) => state.isSynced);
  useEffect(() => {
    if (!synced || localStorage.getItem("gigca-navy-layout-v2")) return;
    setPreference("theme_preset", "navy");
    setPreference("theme_mode", "light");
    localStorage.setItem("gigca-navy-layout-v2", "true");
  }, [synced, setPreference]);
  return (
    <Sidebar {...props} variant="sidebar" collapsible="offcanvas" className="gigca-rail">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="h-auto flex-col gap-1 py-3">
              <Link href="/dashboard/gigca" aria-label="GigCa">
                <Command />
                <span>GigCa</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu className="gap-3 px-2 py-3">
          {links.map(({ title, href, icon: Icon }) => (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton asChild isActive={path === href} className="h-auto flex-col gap-2 py-3">
                <Link href={href}>
                  <Icon />
                  <span>{title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="h-auto flex-col gap-2 py-3">
              <Link href="/dashboard/gigca">
                <UserRound />
                <span>Tài xế</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
