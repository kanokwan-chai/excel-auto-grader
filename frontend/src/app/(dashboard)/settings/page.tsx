"use client";

import React, { useEffect, useState } from "react";
import { KeyRound, Save, UserCircle2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/components/ui/toast";
import { Button, Card, Input, Textarea } from "@/components/ui/primitives";

export default function SettingsPage() {
  const { teacher, refreshProfile } = useAuth();
  const { toast } = useToast();

  const [profile, setProfile] = useState({
    email: "",
    full_name: "",
    school_name: "",
    department: "",
    phone: "",
    bio: "",
  });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPass, setSavingPass] = useState(false);

  useEffect(() => {
    if (teacher) {
      setProfile({
        email: teacher.email || "",
        full_name: teacher.full_name || "",
        school_name: teacher.school_name || "",
        department: teacher.department || "",
        phone: teacher.phone || "",
        bio: teacher.bio || "",
      });
    }
  }, [teacher]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      await apiRequest("/auth/profile", { method: "PUT", body: JSON.stringify(profile) });
      await refreshProfile();
      toast("บันทึกข้อมูลโปรไฟล์เรียบร้อยแล้ว");
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ", "error");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleAvatarUpload = async (file: File | null) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await apiRequest("/auth/avatar", { method: "POST", body: fd });
      await refreshProfile();
      toast("อัปเดตรูปโปรไฟล์สำเร็จ");
    } catch (err) {
      toast(err instanceof Error ? err.message : "อัปโหลดรูปไม่สำเร็จ", "error");
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingPass(true);
    try {
      await apiRequest("/auth/password", { method: "PUT", body: JSON.stringify(passwords) });
      toast("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว");
      setPasswords({ current_password: "", new_password: "" });
    } catch (err) {
      toast(err instanceof Error ? err.message : "เปลี่ยนรหัสผ่านไม่สำเร็จ", "error");
    } finally {
      setSavingPass(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-violet-950">ตั้งค่าบัญชีครูผู้สอน</h1>
        <p className="text-sm text-slate-500">แก้ไขข้อมูลส่วนตัว เปลี่ยนรูปโปรไฟล์ และความปลอดภัยบัญชี</p>
      </div>

      <Card>
        <h2 className="mb-4 flex items-center gap-2 text-base font-semibold text-violet-950">
          <UserCircle2 className="h-5 w-5 text-violet-600" /> ข้อมูลโปรไฟล์ครู
        </h2>
        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-semibold">อีเมลเข้าสู่ระบบ</label>
              <Input type="email" required value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">ชื่อ-นามสกุล</label>
              <Input required value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">โรงเรียน / สถานศึกษา</label>
              <Input value={profile.school_name} onChange={(e) => setProfile({ ...profile, school_name: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">กลุ่มสาระ / แผนก</label>
              <Input value={profile.department} onChange={(e) => setProfile({ ...profile, department: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">เบอร์โทรศัพท์</label>
              <Input value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold">แนะนำตัว</label>
            <Textarea rows={2} value={profile.bio} onChange={(e) => setProfile({ ...profile, bio: e.target.value })} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold">เปลี่ยนรูปโปรไฟล์</label>
            <Input type="file" accept="image/*" onChange={(e) => handleAvatarUpload(e.target.files?.[0] || null)} />
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={savingProfile}>
              <Save className="h-4 w-4" /> บันทึกโปรไฟล์
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="mb-4 flex items-center gap-2 text-base font-semibold text-violet-950">
          <KeyRound className="h-5 w-5 text-pink-600" /> เปลี่ยนรหัสผ่าน
        </h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-semibold">รหัสผ่านปัจจุบัน</label>
              <Input
                type="password"
                required
                value={passwords.current_password}
                onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">รหัสผ่านใหม่ (อย่างน้อย 8 ตัวอักษร)</label>
              <Input
                type="password"
                required
                minLength={8}
                value={passwords.new_password}
                onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })}
              />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" loading={savingPass}>
              อัปเดตรหัสผ่าน
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
