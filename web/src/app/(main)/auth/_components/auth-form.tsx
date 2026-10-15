"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const registering = mode === "register";
  const [error, setError] = useState("");
  const schema = z.object({
    username: z.string().regex(/^[a-zA-Z0-9_.-]{3,64}$/, "Dùng 3–64 chữ, số hoặc ký tự _ . -"),
    password: z.string().min(12, "Mật khẩu cần ít nhất 12 ký tự.").max(128, "Tối đa 128 ký tự."),
    display_name: z.string().max(100, "Tối đa 100 ký tự."),
    confirm_password: z.string(),
  }).superRefine((value, context) => {
    if (!registering) return;
    if (!value.display_name.trim()) {
      context.addIssue({ code: "custom", path: ["display_name"], message: "Nhập tên hiển thị của bạn." });
    }
    if (value.password !== value.confirm_password) {
      context.addIssue({ code: "custom", path: ["confirm_password"], message: "Mật khẩu nhập lại chưa khớp." });
    }
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", display_name: "", confirm_password: "" },
  });
  async function submit(value: z.infer<typeof schema>) {
    setError("");
    try {
      const response = await fetch(`/api/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: value.username, password: value.password,
          ...(registering ? { display_name: value.display_name.trim() } : {}) }),
        signal: AbortSignal.timeout(20000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || "Chưa thể đăng nhập. Vui lòng thử lại.");
      // Full navigation clears previous driver's in-memory dashboard/session data.
      window.location.replace("/dashboard/gigca");
    } catch (cause) {
      setError(cause instanceof Error && cause.name !== "TimeoutError"
        ? cause.message : "Kết nối bị gián đoạn. Vui lòng thử lại.");
    }
  }
  const fields = [
    ...(registering ? [{ name: "display_name" as const, label: "Tên hiển thị", type: "text", autocomplete: "nickname", placeholder: "Tên của bạn" }] : []),
    { name: "username" as const, label: "Tên đăng nhập", type: "text", autocomplete: "username", placeholder: "Ví dụ: taixe01" },
    { name: "password" as const, label: "Mật khẩu", type: "password", autocomplete: registering ? "new-password" : "current-password", placeholder: "Nhập mật khẩu" },
    ...(registering ? [{ name: "confirm_password" as const, label: "Nhập lại mật khẩu", type: "password", autocomplete: "new-password", placeholder: "Nhập lại mật khẩu" }] : []),
  ];
  return (
    <form noValidate onSubmit={form.handleSubmit(submit)} className="flex flex-col gap-6">
      <FieldGroup className="gap-5">
        {fields.map((item) => (
          <Controller key={item.name} control={form.control} name={item.name} render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid} data-disabled={form.formState.isSubmitting}>
              <FieldLabel htmlFor={`auth-${item.name}`}>{item.label}</FieldLabel>
              <Input {...field} id={`auth-${item.name}`} type={item.type} autoComplete={item.autocomplete}
                placeholder={item.placeholder} aria-invalid={fieldState.invalid} className="h-11"
                disabled={form.formState.isSubmitting} maxLength={item.name === "username" ? 64 : item.name === "display_name" ? 100 : 128}
                autoCapitalize="none" spellCheck={false} />
              {registering && item.name === "password" && <FieldDescription>Từ 12 đến 128 ký tự.</FieldDescription>}
              {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
            </Field>
          )} />
        ))}
      </FieldGroup>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <Button type="submit" size="lg" className="h-11 w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? "Đang xử lý…" : registering ? "Tạo tài khoản" : "Đăng nhập"}
      </Button>
    </form>
  );
}
