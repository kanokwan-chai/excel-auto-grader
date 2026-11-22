"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock, Mail } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/components/ui/toast";
import { Button, Card, ErrorBanner, Excel3DLogo, Input } from "@/components/ui/primitives";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { loginWithToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await apiRequest<{ access_token: string; full_name: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      await loginWithToken(res.access_token);
      toast(`ยินดีต้อนรับคุณครู ${res.full_name} ✨`);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-[#F2FCEB] via-[#FFFDF7] to-[#EBF7FF] p-4">
      <div className="pointer-events-none absolute -top-24 -left-24 h-80 w-80 rounded-full bg-[#B9F29B]/45 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-[#FFF099]/50 blur-3xl" />

      <Card className="relative z-10 w-full max-w-md p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 animate-float-slow">
            <Excel3DLogo size="lg" />
          </div>
          <h1 className="text-2xl font-extrabold text-[#172B1C]">Excel Auto Grader ✨</h1>
          <p className="mt-1 text-sm font-medium text-[#5C7061]">เข้าสู่ระบบสำหรับครูผู้สอน 🧑‍🏫</p>
        </div>

        {error && (
          <div className="mb-4">
            <ErrorBanner message={error} />
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-bold text-[#26462E]">อีเมลครูผู้สอน</label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-3 h-4 w-4 text-[#5CB83C]" />
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="teacher@school.ac.th"
                className="pl-10"
              />
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-xs font-bold text-[#26462E]">รหัสผ่าน</label>
              <Link href="/forgot-password" className="text-xs font-semibold text-[#3C9E24] hover:underline">
                ลืมรหัสผ่าน?
              </Link>
            </div>
            <div className="relative">
              <Lock className="absolute left-3.5 top-3 h-4 w-4 text-[#5CB83C]" />
              <Input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="pl-10"
              />
            </div>
          </div>

          <Button type="submit" className="w-full" size="lg" loading={loading}>
            🚀 เข้าสู่ระบบ
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-[#5C7061]">
          ยังไม่มีบัญชีครู?{" "}
          <Link href="/register" className="font-bold text-[#3C9E24] hover:underline">
            สมัครสมาชิกใหม่ ✨
          </Link>
        </p>
      </Card>
    </div>
  );
}
