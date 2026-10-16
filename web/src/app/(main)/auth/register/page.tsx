import type { Metadata } from "next";
import { AuthScreen } from "../_components/auth-screen";

export const metadata: Metadata = { title: "Tạo tài khoản | GigCa" };

export default function RegisterPage() {
  return <AuthScreen mode="register" />;
}
