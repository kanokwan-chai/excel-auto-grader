"use client";

import React, { useEffect, useState } from "react";
import { BookOpen, Plus, Trash2, Users } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { TeacherClassItem } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  Input,
  Modal,
  Select,
  Skeleton,
} from "@/components/ui/primitives";

const COLOR_MAP: Record<string, string> = {
  lavender: "bg-violet-100 text-violet-700",
  pink: "bg-pink-100 text-pink-700",
  mint: "bg-emerald-100 text-emerald-700",
  sky: "bg-sky-100 text-sky-700",
};

export default function ClassesPage() {
  const [classes, setClasses] = useState<TeacherClassItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openCreate, setOpenCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TeacherClassItem | null>(null);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    name: "",
    subject_code: "",
    subject_name: "",
    semester: "1",
    academic_year: "2569",
    room: "",
    color_tag: "lavender",
  });
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setClasses(await apiRequest<TeacherClassItem[]>("/classes"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดชั้นเรียนไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiRequest("/classes", { method: "POST", body: JSON.stringify(form) });
      toast("สร้างชั้นเรียนใหม่เรียบร้อยแล้ว");
      setOpenCreate(false);
      setForm({ name: "", subject_code: "", subject_name: "", semester: "1", academic_year: "2569", room: "", color_tag: "lavender" });
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "สร้างชั้นเรียนไม่สำเร็จ", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await apiRequest(`/classes/${deleteTarget.id}`, { method: "DELETE" });
      toast("ลบชั้นเรียนเรียบร้อยแล้ว");
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ลบชั้นเรียนไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">ชั้นเรียนของฉัน</h1>
          <p className="text-sm text-slate-500">จัดการห้องเรียน รหัสวิชา ภาคเรียน และจำนวนนักเรียน</p>
        </div>
        <Button onClick={() => setOpenCreate(true)}>
          <Plus className="h-4 w-4" /> เพิ่มชั้นเรียนใหม่
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-44" />)}
        </div>
      ) : classes.length === 0 ? (
        <EmptyState
          title="ยังไม่มีชั้นเรียน"
          description="เพิ่มชั้นเรียนแรกของคุณเพื่อจัดการรายชื่อนักเรียนและมอบหมายงาน Excel"
          action={<Button onClick={() => setOpenCreate(true)}>เพิ่มชั้นเรียน</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {classes.map((c) => (
            <Card key={c.id} className="flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-start justify-between">
                  <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${COLOR_MAP[c.color_tag] || COLOR_MAP.lavender}`}>
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <button
                    onClick={() => setDeleteTarget(c)}
                    className="rounded-xl p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <h3 className="mt-3 text-base font-bold text-violet-950">{c.name}</h3>
                <p className="text-xs text-slate-500">
                  {c.subject_code ? `${c.subject_code} ` : ""}{c.subject_name || "วิชาคอมพิวเตอร์"}
                </p>
              </div>
              <div className="flex items-center justify-between border-t border-violet-50 pt-3">
                <Badge tone="lavender">
                  เทอม {c.semester || "-"}/{c.academic_year || "-"}
                </Badge>
                <span className="flex items-center gap-1 text-xs font-medium text-slate-600">
                  <Users className="h-3.5 w-3.5 text-violet-500" />
                  {c.student_count} คน
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={openCreate} onClose={() => setOpenCreate(false)} title="เพิ่มชั้นเรียนใหม่">
        <form onSubmit={handleCreate} className="space-y-3.5">
          <div>
            <label className="mb-1 block text-xs font-semibold">ชื่อชั้นเรียน *</label>
            <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="ม.4/1 เทคโนโลยีสารสนเทศ" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">รหัสวิชา</label>
              <Input value={form.subject_code} onChange={(e) => setForm({ ...form, subject_code: e.target.value })} placeholder="ว31101" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">ชื่อวิชา</label>
              <Input value={form.subject_name} onChange={(e) => setForm({ ...form, subject_name: e.target.value })} placeholder="วิทยาการคำนวณ" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">ภาคเรียน</label>
              <Input value={form.semester} onChange={(e) => setForm({ ...form, semester: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">ปีการศึกษา</label>
              <Input value={form.academic_year} onChange={(e) => setForm({ ...form, academic_year: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">สีป้าย</label>
              <Select value={form.color_tag} onChange={(e) => setForm({ ...form, color_tag: e.target.value })}>
                <option value="lavender">ม่วงลาเวนเดอร์</option>
                <option value="pink">ชมพูพาสเทล</option>
                <option value="mint">เขียวมิ้นต์</option>
                <option value="sky">ฟ้าอ่อน</option>
              </Select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-3">
            <Button type="button" variant="outline" onClick={() => setOpenCreate(false)}>ยกเลิก</Button>
            <Button type="submit" loading={saving}>บันทึกชั้นเรียน</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="ลบชั้นเรียน"
        description={`ยืนยันการลบชั้นเรียน "${deleteTarget?.name}"?`}
        confirmLabel="ลบชั้นเรียน"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
