import Link from "next/link";
import { CloudRain, Command, History, Navigation } from "lucide-react";
import { redirect } from "next/navigation";

import { currentDriver } from "@/server/auth";

import { AuthForm } from "./auth-form";

export async function AuthScreen({ mode }: { mode: "login" | "register" }) {
  if (await currentDriver()) redirect("/dashboard/gigca");
  const registering = mode === "register";
  return (
    <main className="flex min-h-dvh bg-background">
      <aside className="hidden flex-col justify-between bg-sidebar p-10 text-sidebar-foreground lg:flex lg:w-1/3 xl:p-14">
        <Link href="/auth/login" className="flex items-center gap-3 font-semibold text-2xl" aria-label="GigCa">
          <Command className="size-8" aria-hidden="true" />GigCa
        </Link>
        <div className="flex flex-col gap-10 py-16">
          <div className="flex flex-col gap-5">
            <p className="font-medium text-sidebar-foreground/70">BẠN ĐỒNG HÀNH CỦA TÀI XẾ</p>
            <h2 className="text-balance font-semibold text-4xl leading-tight xl:text-5xl">
              Chọn điểm chờ.<br />Chủ động hành trình.
            </h2>
          </div>
          <ul className="flex flex-col gap-5 text-sidebar-foreground/90">
            <li className="flex items-center gap-3"><Navigation className="size-5" aria-hidden="true" />Gợi ý theo vị trí của bạn</li>
            <li className="flex items-center gap-3"><CloudRain className="size-5" aria-hidden="true" />Theo dõi mưa và giao thông</li>
            <li className="flex items-center gap-3"><History className="size-5" aria-hidden="true" />Lịch sử riêng cho mỗi tài xế</li>
          </ul>
        </div>
        <p className="text-sm text-sidebar-foreground/70">GigCa · Đồng hành trên mỗi chặng đường</p>
      </aside>
      <section className="flex w-full items-center justify-center p-6 sm:p-10 lg:w-2/3">
        <div className="flex w-full max-w-md flex-col gap-8 py-10">
          <Link href="/auth/login" className="flex items-center gap-2 font-semibold text-2xl lg:hidden">
            <Command className="size-7 text-primary" aria-hidden="true" />GigCa
          </Link>
          <div className="flex flex-col gap-3">
            <h1 className="font-semibold text-3xl tracking-tight">{registering ? "Tạo tài khoản GigCa" : "Chào mừng trở lại"}</h1>
            <p className="text-muted-foreground">{registering ? "Bắt đầu với hồ sơ tài xế của riêng bạn." : "Đăng nhập để tiếp tục hành trình của bạn."}</p>
          </div>
          <AuthForm mode={mode} />
          <p className="text-center text-sm">
            {registering ? "Đã có tài khoản? " : "Chưa có tài khoản? "}
            <Link href={registering ? "/auth/login" : "/auth/register"} className="font-medium text-primary underline-offset-4 hover:underline">
              {registering ? "Đăng nhập" : "Tạo tài khoản"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
