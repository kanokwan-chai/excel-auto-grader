"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileSpreadsheet } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/components/ui/toast";
import { Button, Card, ErrorBanner, Input } from "@/components/ui/primitives";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [schoolName, setSchoolName] = useState("");
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
      const res = await apiRequest<{ access_token: string }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          full_name: fullName,
          school_name: schoolName || undefined,
        }),
      });
      await loginWithToken(res.access_token);
      toast("สมัครสมาชิกสำเร็จ ยินดีต้อนรับสู่ Excel Auto Grader");
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "สมัครสมาชิกไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#E0F2FE] via-[#FFFDF9] to-[#F3EEFF] p-4">
      <Card className="w-full max-w-md p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-3xl bg-gradient-to-br from-violet-600 to-sky-500 text-white shadow-soft">
            <FileSpreadsheet className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold text-violet-950">สร้างบัญชีครูผู้สอน</h1>
          <p className="mt-1 text-sm text-slate-500">ข้อมูลชั้นเรียนและคะแนนของคุณจะถูกแยกเป็นส่วนตัว 100%</p>
        </div>

        {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-violet-900">ชื่อ-นามสกุล</label>
            <Input required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="ครูสมชาย ใจดี" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-violet-900">โรงเรียน / สถานศึกษา (ไม่บังคับ)</label>
            <Input value={schoolName} onChange={(e) => setSchoolName(e.target.value)} placeholder="โรงเรียนสาธิต..." />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-violet-900">อีเมล</label>
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teacher@school.ac.th" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-violet-900">รหัสผ่าน (อย่างน้อย 8 ตัวอักษร)</label>
            <Input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>

          <Button type="submit" className="w-full" size="lg" loading={loading}>
            สมัครสมาชิก
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          มีบัญชีอยู่แล้ว?{" "}
          <Link href="/login" className="font-semibold text-violet-600 hover:underline">
            เข้าสู่ระบบ
          </Link>
        </p>
      </Card>
    </div>
  );
}
