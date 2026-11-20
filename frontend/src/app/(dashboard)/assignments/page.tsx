"use client";

import React, { useEffect, useState } from "react";
import { Copy, FileSpreadsheet, Plus, Trash2, Upload } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatThaiDate } from "@/lib/utils";
import type { AssignmentItem, TeacherClassItem } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  Modal,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";

export default function AssignmentsPage() {
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [classes, setClasses] = useState<TeacherClassItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openCreate, setOpenCreate] = useState(false);
  const [refTarget, setRefTarget] = useState<AssignmentItem | null>(null);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const [form, setForm] = useState({
    title: "",
    description: "",
    subject_name: "",
    class_id: "",
    max_score: "20",
    pass_score: "10",
    max_files_allowed: "1",
    status: "published",
  });
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, c] = await Promise.all([
        apiRequest<AssignmentItem[]>("/assignments"),
        apiRequest<TeacherClassItem[]>("/classes"),
      ]);
      setAssignments(a);
      setClasses(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดรายการงานไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiRequest("/assignments", {
        method: "POST",
        body: JSON.stringify({
          title: form.title,
          description: form.description || null,
          subject_name: form.subject_name || null,
          class_id: form.class_id || null,
          max_score: Number(form.max_score),
          pass_score: Number(form.pass_score),
          max_files_allowed: Number(form.max_files_allowed),
          status: form.status,
        }),
      });
      toast("สร้างงานใหม่เรียบร้อยแล้ว");
      setOpenCreate(false);
      setForm({ title: "", description: "", subject_name: "", class_id: "", max_score: "20", pass_score: "10", max_files_allowed: "1", status: "published" });
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "สร้างงานไม่สำเร็จ", "error");
    }
  };

  const handleUploadReference = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refTarget || !refFile) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", refFile);
      await apiRequest(`/assignments/${refTarget.id}/reference-file`, { method: "POST", body: fd });
      toast("อัปโหลดและวิเคราะห์ไฟล์เฉลยต้นฉบับเรียบร้อยแล้ว");
      setRefTarget(null);
      setRefFile(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "อัปโหลดไฟล์เฉลยไม่สำเร็จ", "error");
    } finally {
      setUploading(false);
    }
  };

  const handleDuplicate = async (id: string) => {
    try {
      await apiRequest(`/assignments/${id}/duplicate`, { method: "POST" });
      toast("คัดลอกงานเป็นฉบับร่างแล้ว");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "คัดลอกไม่สำเร็จ", "error");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiRequest(`/assignments/${id}`, { method: "DELETE" });
      toast("ลบงานเรียบร้อยแล้ว");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ลบงานไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">งานที่มอบหมาย</h1>
          <p className="text-sm text-slate-500">สร้างงาน อัปโหลดไฟล์ Excel เฉลยต้นฉบับ และคัดลอกงานเดิม</p>
        </div>
        <Button onClick={() => setOpenCreate(true)}>
          <Plus className="h-4 w-4" /> สร้างงานใหม่
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : assignments.length === 0 ? (
        <EmptyState
          title="ยังไม่มีงานที่มอบหมาย"
          description="สร้างงานใหม่เพื่อกำหนดคะแนนเต็มและอัปโหลดไฟล์ Excel ต้นฉบับที่เป็นเฉลย"
          action={<Button onClick={() => setOpenCreate(true)}>สร้างงานแรก</Button>}
        />
      ) : (
        <div className="space-y-4">
          {assignments.map((a) => (
            <Card key={a.id} className="flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold text-violet-950">{a.title}</h3>
                  <Badge tone={a.status === "completed" ? "mint" : a.status === "draft" ? "slate" : "lavender"}>
                    {a.status}
                  </Badge>
                  {a.class_name && <Badge tone="sky">{a.class_name}</Badge>}
                </div>
                <p className="text-xs text-slate-500">
                  คะแนนเต็ม {a.max_score} • เกณฑ์ผ่าน {a.pass_score} • ส่งแล้ว {a.submission_count} • ตรวจแล้ว {a.graded_count}
                  {a.due_at ? ` • กำหนดส่ง ${formatThaiDate(a.due_at)}` : ""}
                </p>
                {a.reference_file ? (
                  <p className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                    <FileSpreadsheet className="h-3.5 w-3.5" />
                    ไฟล์เฉลย: {a.reference_file.filename}
                  </p>
                ) : (
                  <p className="text-xs text-amber-600">ยังไม่ได้อัปโหลดไฟล์เฉลยต้นฉบับ</p>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => setRefTarget(a)}>
                  <Upload className="h-3.5 w-3.5" /> อัปโหลดไฟล์เฉลย
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleDuplicate(a.id)}>
                  <Copy className="h-3.5 w-3.5" /> คัดลอก
                </Button>
                <Button size="sm" variant="danger" onClick={() => handleDelete(a.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={openCreate} onClose={() => setOpenCreate(false)} title="สร้างงานใหม่">
        <form onSubmit={handleCreate} className="space-y-3.5">
          <div>
            <label className="mb-1 block text-xs font-semibold">ชื่องาน *</label>
            <Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="ใบงานที่ 1 การใช้สูตร SUM และ IF" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold">รายละเอียดงาน</label>
            <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">ชั้นเรียน</label>
              <Select value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}>
                <option value="">-- ไม่ระบุ --</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">สถานะ</label>
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="draft">ฉบับร่าง (Draft)</option>
                <option value="published">เปิดรับงาน (Published)</option>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">คะแนนเต็ม</label>
              <Input type="number" step="0.5" value={form.max_score} onChange={(e) => setForm({ ...form, max_score: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">เกณฑ์ผ่าน</label>
              <Input type="number" step="0.5" value={form.pass_score} onChange={(e) => setForm({ ...form, pass_score: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">จำนวนไฟล์สูงสุด</label>
              <Input type="number" min="1" value={form.max_files_allowed} onChange={(e) => setForm({ ...form, max_files_allowed: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-3">
            <Button type="button" variant="outline" onClick={() => setOpenCreate(false)}>ยกเลิก</Button>
            <Button type="submit">บันทึกงาน</Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(refTarget)} onClose={() => setRefTarget(null)} title={`อัปโหลดไฟล์เฉลย: ${refTarget?.title || ""}`}>
        <form onSubmit={handleUploadReference} className="space-y-4">
          <p className="text-xs text-slate-500">
            รองรับ .xlsx, .xls, .xlsm (ระบบจะไม่อนุญาตให้รัน Macro และจะวิเคราะห์สูตร/แผ่นงานโดยอัตโนมัติ)
          </p>
          <Input type="file" accept=".xlsx,.xls,.xlsm" required onChange={(e) => setRefFile(e.target.files?.[0] || null)} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setRefTarget(null)}>ยกเลิก</Button>
            <Button type="submit" loading={uploading} disabled={!refFile}>อัปโหลดไฟล์เฉลย</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
