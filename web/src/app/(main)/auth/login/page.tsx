import type { Metadata } from "next";
import { AuthScreen } from "../_components/auth-screen";

export const metadata: Metadata = { title: "Đăng nhập | GigCa" };

export default function LoginPage() {
  return <AuthScreen mode="login" />;
}
