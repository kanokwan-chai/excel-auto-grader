"use client";

import React, { useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api";
import { Button, Card, Input, SuccessBanner } from "@/components/ui/primitives";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sentMessage, setSentMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await apiRequest<{ message: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSentMessage(res.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#F3EEFF] via-[#FFFDF9] to-[#D1FAE5] p-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-xl font-bold text-violet-950">รีเซ็ตรหัสผ่าน</h1>
        <p className="mt-1 text-sm text-slate-500">กรอกอีเมลที่ใช้สมัครสมาชิกเพื่อรับลิงก์ตั้งรหัสผ่านใหม่</p>

        {sentMessage ? (
          <div className="mt-5 space-y-4">
            <SuccessBanner message={sentMessage} />
            <Link href="/login" className="block text-center text-sm font-semibold text-violet-600 hover:underline">
              กลับไปหน้าเข้าสู่ระบบ
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teacher@school.ac.th"
            />
            <Button type="submit" className="w-full" loading={loading}>
              ส่งลิงก์รีเซ็ตรหัสผ่าน
            </Button>
            <Link href="/login" className="block text-center text-sm text-slate-500 hover:text-violet-700">
              กลับหน้าเข้าสู่ระบบ
            </Link>
          </form>
        )}
      </Card>
    </div>
  );
}
