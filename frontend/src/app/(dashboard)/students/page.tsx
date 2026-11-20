"use client";

import React, { useEffect, useState } from "react";
import { ArrowRightLeft, Plus, Search, Trash2, Upload } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { StudentItem, TeacherClassItem } from "@/types";
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
} from "@/components/ui/primitives";

export default function StudentsPage() {
  const [students, setStudents] = useState<StudentItem[]>([]);
  const [classes, setClasses] = useState<TeacherClassItem[]>([]);
  const [filterClass, setFilterClass] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [openAdd, setOpenAdd] = useState(false);
  const [openImport, setOpenImport] = useState(false);
  const [transferTarget, setTransferTarget] = useState<StudentItem | null>(null);
  const [transferToClassId, setTransferToClassId] = useState("");

  const [form, setForm] = useState({
    student_code: "",
    first_name: "",
    last_name: "",
    room: "",
    seat_number: "",
    email: "",
    class_id: "",
  });
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importClassId, setImportClassId] = useState("");
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filterClass) params.set("class_id", filterClass);
      if (search) params.set("search", search);
      const [st, cls] = await Promise.all([
        apiRequest<StudentItem[]>(`/students?${params.toString()}`),
        apiRequest<TeacherClassItem[]>("/classes"),
      ]);
      setStudents(st);
      setClasses(cls);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดรายชื่อนักเรียนไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filterClass]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiRequest("/students", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          seat_number: form.seat_number ? Number(form.seat_number) : null,
          class_id: form.class_id || null,
        }),
      });
      toast("เพิ่มนักเรียนสำเร็จ");
      setOpenAdd(false);
      setForm({ student_code: "", first_name: "", last_name: "", room: "", seat_number: "", email: "", class_id: "" });
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "เพิ่มนักเรียนไม่สำเร็จ", "error");
    }
  };

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFile) return;
    const fd = new FormData();
    fd.append("file", importFile);
    if (importClassId) fd.append("class_id", importClassId);
    try {
      const res = await apiRequest<{ imported: number; skipped: number }>("/students/import", {
        method: "POST",
        body: fd,
      });
      toast(`นำเข้าสำเร็จ ${res.imported} คน (ข้าม ${res.skipped} แถว)`);
      setOpenImport(false);
      setImportFile(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "นำเข้าไฟล์ไม่สำเร็จ", "error");
    }
  };

  const handleTransfer = async () => {
    if (!transferTarget || !transferToClassId) return;
    try {
      await apiRequest(`/students/${transferTarget.id}/transfer`, {
        method: "POST",
        body: JSON.stringify({
          from_class_id: transferTarget.classes[0]?.id || null,
          to_class_id: transferToClassId,
        }),
      });
      toast("ย้ายห้องเรียนสำเร็จ");
      setTransferTarget(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ย้ายห้องไม่สำเร็จ", "error");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiRequest(`/students/${id}`, { method: "DELETE" });
      toast("ลบนักเรียนแล้ว");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ลบไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">รายชื่อนักเรียน</h1>
          <p className="text-sm text-slate-500">รองรับการนำเข้ารายชื่อจาก Excel / CSV การค้นหา และการย้ายชั้นเรียน</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setOpenImport(true)}>
            <Upload className="h-4 w-4" /> นำเข้า CSV / Excel
          </Button>
          <Button onClick={() => setOpenAdd(true)}>
            <Plus className="h-4 w-4" /> เพิ่มนักเรียน
          </Button>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="ค้นหารหัส ชื่อ หรือห้อง..."
              className="pl-9"
            />
          </div>
          <Select value={filterClass} onChange={(e) => setFilterClass(e.target.value)} className="w-56">
            <option value="">ทุกชั้นเรียน</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
          <Button variant="outline" onClick={load}>ค้นหา</Button>
        </div>
      </Card>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <Skeleton className="h-64" />
      ) : students.length === 0 ? (
        <EmptyState title="ยังไม่มีรายชื่อนักเรียน" description="เพิ่มนักเรียนทีละคนหรือนำเข้าจากไฟล์ CSV / Excel" />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-violet-100 bg-violet-50/50 text-left text-xs text-violet-900">
                <th className="px-4 py-3">เลขที่</th>
                <th className="px-4 py-3">รหัสนักเรียน</th>
                <th className="px-4 py-3">ชื่อ-นามสกุล</th>
                <th className="px-4 py-3">ห้อง</th>
                <th className="px-4 py-3">ชั้นเรียน</th>
                <th className="px-4 py-3 text-right">จัดการ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-violet-50">
              {students.map((s) => (
                <tr key={s.id} className="hover:bg-violet-50/30">
                  <td className="px-4 py-3">{s.seat_number ?? "-"}</td>
                  <td className="px-4 py-3 font-mono text-xs">{s.student_code}</td>
                  <td className="px-4 py-3 font-medium text-violet-950">{s.full_name}</td>
                  <td className="px-4 py-3">{s.room || "-"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {s.classes.map((c) => <Badge key={c.id} tone="sky">{c.name}</Badge>)}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setTransferTarget(s);
                          setTransferToClassId(classes[0]?.id || "");
                        }}
                      >
                        <ArrowRightLeft className="h-3.5 w-3.5" /> ย้ายห้อง
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(s.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Add Modal */}
      <Modal open={openAdd} onClose={() => setOpenAdd(false)} title="เพิ่มรายชื่อนักเรียน">
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">รหัสนักเรียน *</label>
              <Input required value={form.student_code} onChange={(e) => setForm({ ...form, student_code: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">เลขที่</label>
              <Input type="number" value={form.seat_number} onChange={(e) => setForm({ ...form, seat_number: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">ชื่อ *</label>
              <Input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">นามสกุล *</label>
              <Input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold">ห้อง</label>
              <Input value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} placeholder="ม.4/1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">เข้าชั้นเรียน</label>
              <Select value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}>
                <option value="">-- ไม่ระบุ --</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-3">
            <Button type="button" variant="outline" onClick={() => setOpenAdd(false)}>ยกเลิก</Button>
            <Button type="submit">บันทึก</Button>
          </div>
        </form>
      </Modal>

      {/* Import Modal */}
      <Modal open={openImport} onClose={() => setOpenImport(false)} title="นำเข้ารายชื่อนักเรียน (CSV / Excel)">
        <form onSubmit={handleImport} className="space-y-4">
          <p className="text-xs text-slate-500">
            หัวคอลัมน์ที่รองรับ: <code>student_code, first_name, last_name, room, seat_number, email</code> (หรือภาษาไทย รหัสนักเรียน, ชื่อ, นามสกุล, ห้อง, เลขที่)
          </p>
          <Select value={importClassId} onChange={(e) => setImportClassId(e.target.value)}>
            <option value="">-- เลือกชั้นเรียน (ไม่บังคับ) --</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Input type="file" accept=".csv,.xlsx" required onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpenImport(false)}>ยกเลิก</Button>
            <Button type="submit" disabled={!importFile}>นำเข้าข้อมูล</Button>
          </div>
        </form>
      </Modal>

      {/* Transfer Modal */}
      <Modal open={Boolean(transferTarget)} onClose={() => setTransferTarget(null)} title="ย้ายชั้นเรียน">
        <div className="space-y-4">
          <p className="text-sm">นักเรียน: <strong>{transferTarget?.full_name}</strong></p>
          <Select value={transferToClassId} onChange={(e) => setTransferToClassId(e.target.value)}>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTransferTarget(null)}>ยกเลิก</Button>
            <Button onClick={handleTransfer}>ยืนยันการย้าย</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
