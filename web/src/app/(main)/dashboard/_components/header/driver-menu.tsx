"use client";

import { useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { Driver } from "@/lib/auth";

export function DriverMenu({ driver }: { driver: Driver }) {
  const [busy, setBusy] = useState(false);
  const initials = driver.display_name.split(/\s+/).slice(-2).map((word) => word[0]).join("").toUpperCase();
  async function logout() {
    setBusy(true);
    try {
      const response = await fetch("/api/v1/auth/logout", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok && response.status !== 503 && response.status !== 401) throw new Error();
      window.location.replace("/auth/login");
    } catch {
      toast.error("Chưa thể đăng xuất. Vui lòng thử lại.");
      setBusy(false);
    }
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" disabled={busy} aria-label="Tài khoản tài xế">
          <Avatar className="size-7"><AvatarFallback>{initials || "TX"}</AvatarFallback></Avatar>
          <span className="hidden max-w-32 truncate sm:inline">{driver.display_name}</span>
          <ChevronDown data-icon="inline-end" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{driver.username}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem onSelect={() => { void logout(); }} disabled={busy}>
            <LogOut />{busy ? "Đang đăng xuất…" : "Đăng xuất"}
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
