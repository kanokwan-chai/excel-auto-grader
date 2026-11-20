"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileSpreadsheet, Lock, Mail } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/components/ui/toast";
import { Button, Card, ErrorBanner, Input } from "@/components/ui/primitives";

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
      toast(`ยินดีต้อนรับคุณครู ${res.full_name}`);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#F3EEFF] via-[#FFFDF9] to-[#FCE7F3] p-4">
      <Card className="w-full max-w-md p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-3xl bg-gradient-to-br from-violet-600 to-pink-500 text-white shadow-soft">
            <FileSpreadsheet className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold text-violet-950">Excel Auto Grader</h1>
          <p className="mt-1 text-sm text-slate-500">เข้าสู่ระบบสำหรับครูผู้สอน</p>
        </div>

        {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-violet-900">อีเมลครูผู้สอน</label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-violet-400" />
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="teacher@school.ac.th"
                className="pl-9"
              />
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-xs font-semibold text-violet-900">รหัสผ่าน</label>
              <Link href="/forgot-password" className="text-xs text-violet-600 hover:underline">
                ลืมรหัสผ่าน?
              </Link>
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-3 h-4 w-4 text-violet-400" />
              <Input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="pl-9"
              />
            </div>
          </div>

          <Button type="submit" className="w-full" size="lg" loading={loading}>
            เข้าสู่ระบบ
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          ยังไม่มีบัญชีครู?{" "}
          <Link href="/register" className="font-semibold text-violet-600 hover:underline">
            สมัครสมาชิกใหม่
          </Link>
        </p>
      </Card>
    </div>
  );
}
