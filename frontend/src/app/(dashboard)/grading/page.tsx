"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, FileSpreadsheet, Play, UploadCloud } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatBytes, formatThaiDate } from "@/lib/utils";
import type { AssignmentItem, Rubric } from "@/types";
import { useToast } from "@/components/ui/toast";
import { Badge, Button, Card, EmptyState, ErrorBanner, Select } from "@/components/ui/primitives";

interface SubmissionRow {
  id: string;
  student_display_name: string;
  student_code_matched?: string | null;
  submission_status: string;
  submitted_at?: string | null;
  files: {
    id: string;
    original_filename: string;
    file_size_bytes: number;
    is_primary: boolean;
    is_duplicate: boolean;
    security_status: string;
    security_note?: string | null;
    created_at?: string | null;
  }[];
}

export default function GradingUploadPage() {
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [assignmentId, setAssignmentId] = useState("");
  const [rubricId, setRubricId] = useState("");
  const [submissions, setSubmissions] = useState<SubmissionRow[]>([]);
  const [selectedSubIds, setSelectedSubIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [grading, setGrading] = useState(false);
  const [lastJob, setLastJob] = useState<{ processed_files: number; failed_files: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    Promise.all([apiRequest<AssignmentItem[]>("/assignments"), apiRequest<Rubric[]>("/rubrics")])
      .then(([a, r]) => {
        setAssignments(a);
        setRubrics(r);
        if (a.length > 0) setAssignmentId(a[0].id);
        if (r.length > 0) setRubricId(r[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ"));
  }, []);

  const loadSubmissions = async (aId: string) => {
    if (!aId) return;
    try {
      const list = await apiRequest<SubmissionRow[]>(`/submissions?assignment_id=${encodeURIComponent(aId)}`);
      setSubmissions(list);
      setSelectedSubIds(list.map((s) => s.id));
    } catch {
      setSubmissions([]);
      setSelectedSubIds([]);
    }
  };

  useEffect(() => {
    if (assignmentId) loadSubmissions(assignmentId);
  }, [assignmentId]);

  const handleFilesSelected = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0 || !assignmentId) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("assignment_id", assignmentId);
      Array.from(fileList).forEach((f) => fd.append("files", f));
      const res = await apiRequest<{ uploaded_count: number }>("/submissions/upload", {
        method: "POST",
        body: fd,
      });
      toast(`อัปโหลดไฟล์นักเรียนสำเร็จ ${res.uploaded_count} ไฟล์`);
      await loadSubmissions(assignmentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "อัปโหลดไฟล์ไม่สำเร็จ");
    } finally {
      setUploading(false);
    }
  };

  const toggleSelectSub = (id: string) => {
    setSelectedSubIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSetPrimaryFile = async (subId: string, fileId: string) => {
    try {
      await apiRequest(`/submissions/${subId}/primary-file/${fileId}`, { method: "PUT" });
      toast("เปลี่ยนไฟล์ที่จะใช้วิเคราะห์คะแนนแล้ว");
      await loadSubmissions(assignmentId);
    } catch (err) {
      toast(err instanceof Error ? err.message : "เปลี่ยนไฟล์ไม่สำเร็จ", "error");
    }
  };

  const handleRunGrading = async () => {
    if (!assignmentId || !rubricId) return;
    if (selectedSubIds.length === 0) {
      toast("กรุณาติ๊กเลือกอย่างน้อย 1 ไฟล์ที่ต้องการวิเคราะห์คะแนน", "error");
      return;
    }
    setGrading(true);
    setError(null);
    try {
      const res = await apiRequest<{ processed_files: number; failed_files: number }>("/grading/run", {
        method: "POST",
        body: JSON.stringify({
          assignment_id: assignmentId,
          rubric_id: rubricId,
          submission_ids: selectedSubIds,
        }),
      });
      setLastJob(res);
      toast(`วิเคราะห์คะแนนเสร็จสิ้น ${res.processed_files} รายการ`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "เริ่มตรวจงานไม่สำเร็จ");
    } finally {
      setGrading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-violet-950">ตรวจงาน Excel อัตโนมัติ</h1>
        <p className="text-sm text-slate-500">
          อัปโหลดไฟล์ Excel ของนักเรียนหลายไฟล์พร้อมกัน ตรวจสอบความปลอดภัย และสั่งตรวจสูตรอัตโนมัติ
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <Card className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-violet-900">1. เลือกงานที่ต้องการตรวจ</label>
          <Select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}>
            <option value="">-- เลือกงาน --</option>
            {assignments.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
          </Select>
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-violet-900">2. เลือกเกณฑ์การตรวจ (Rubric)</label>
          <Select value={rubricId} onChange={(e) => setRubricId(e.target.value)}>
            <option value="">-- เลือกเกณฑ์ --</option>
            {rubrics.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} ({r.total_points} คะแนน • v{r.current_version})
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {/* Drag & Drop Upload Zone */}
      <Card
        className="border-2 border-dashed border-violet-200 bg-violet-50/30 text-center py-10"
      >
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFilesSelected(e.dataTransfer.files);
          }}
          className="flex flex-col items-center"
        >
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-3xl bg-violet-100 text-violet-700">
            <UploadCloud className="h-7 w-7" />
          </div>
          <p className="text-base font-semibold text-violet-950">ลากไฟล์ Excel ของนักเรียนมาวางที่นี่</p>
          <p className="mt-1 text-xs text-slate-500">
            รองรับ .xlsx, .xls, .xlsm หลายไฟล์พร้อมกัน • ตรวจสอบไฟล์ซ้ำและจับคู่รหัสนักเรียนอัตโนมัติ
          </p>
          <label className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-700">
            <FileSpreadsheet className="h-4 w-4" />
            {uploading ? "กำลังอัปโหลด..." : "เลือกไฟล์จากเครื่อง"}
            <input
              type="file"
              multiple
              accept=".xlsx,.xls,.xlsm"
              className="hidden"
              disabled={!assignmentId || uploading}
              onChange={(e) => handleFilesSelected(e.target.files)}
            />
          </label>
        </div>
      </Card>

      {lastJob && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-center gap-3 text-emerald-900">
            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
            <div>
              <p className="font-semibold">ตรวจงานอัตโนมัติเสร็จสมบูรณ์!</p>
              <p className="text-xs">ตรวจทั้งหมด {lastJob.processed_files} ไฟล์ • พบปัญหา {lastJob.failed_files} ไฟล์</p>
            </div>
          </div>
          <Link href="/reports">
            <Button variant="mint">เปิดดูคะแนนและข้อผิดพลาดรายบุคคล</Button>
          </Link>
        </div>
      )}

      {/* Uploaded Submissions Queue with Selective Checkboxes */}
      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-violet-950">
              เลือกไฟล์ที่ต้องการตรวจ ({selectedSubIds.length}/{submissions.length} รายการ)
            </h2>
            {submissions.length > 0 && (
              <button
                type="button"
                onClick={() =>
                  setSelectedSubIds(
                    selectedSubIds.length === submissions.length ? [] : submissions.map((s) => s.id)
                  )
                }
                className="text-xs font-medium text-violet-600 hover:underline"
              >
                {selectedSubIds.length === submissions.length ? "ยกเลิกทั้งหมด" : "เลือกทั้งหมด"}
              </button>
            )}
          </div>
          <Button
            loading={grading}
            disabled={!assignmentId || !rubricId || selectedSubIds.length === 0}
            onClick={handleRunGrading}
          >
            <Play className="h-4 w-4" /> วิเคราะห์คะแนนที่เลือก ({selectedSubIds.length})
          </Button>
        </div>

        {submissions.length === 0 ? (
          <EmptyState title="ยังไม่มีไฟล์ในคิวตรวจ" description="อัปโหลดไฟล์ Excel ของนักเรียนด้านบนเพื่อเริ่มตรวจ" />
        ) : (
          <div className="divide-y divide-violet-50">
            {submissions.map((s) => {
              const checked = selectedSubIds.includes(s.id);
              return (
                <div
                  key={s.id}
                  className={`flex flex-wrap items-center justify-between gap-3 py-3 px-2 rounded-xl text-sm transition ${
                    checked ? "bg-violet-50/40" : ""
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSelectSub(s.id)}
                      className="mt-1 h-4 w-4 rounded border-violet-300 text-violet-600"
                    />
                    <div>
                      <p className="font-semibold text-violet-950">
                        {s.student_display_name}{" "}
                        {s.student_code_matched && <span className="text-xs text-slate-400">({s.student_code_matched})</span>}
                        {s.submitted_at && (
                          <span className="ml-2 text-xs font-normal text-slate-500">
                            • ส่งล่าสุด: {formatThaiDate(s.submitted_at)}
                          </span>
                        )}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-2">
                        {s.files.map((f, fIdx) => (
                          <button
                            key={f.id}
                            type="button"
                            onClick={() => !f.is_primary && handleSetPrimaryFile(s.id, f.id)}
                            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs transition ${
                              f.is_primary
                                ? "border-emerald-300 bg-emerald-50 text-emerald-900 font-medium"
                                : "border-violet-100 bg-white text-slate-600 hover:bg-violet-50"
                            }`}
                            title={f.is_primary ? "ไฟล์หลักที่จะใช้วิเคราะห์คะแนน" : "คลิกเพื่อเลือกไฟล์นี้แทน"}
                          >
                            {f.is_primary && <span>✓</span>}
                            <span>{f.original_filename}</span>
                            <span className="text-[11px] text-slate-500">
                              ({formatBytes(f.file_size_bytes)} • {formatThaiDate(f.created_at)})
                            </span>
                            {fIdx === 0 && s.files.length > 1 && <Badge tone="mint">ล่าสุด</Badge>}
                            {f.is_duplicate && <Badge tone="amber">ไฟล์ซ้ำ</Badge>}
                            {f.security_status !== "safe" && <Badge tone="rose">{f.security_status}</Badge>}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <Badge tone="sky">{s.submission_status}</Badge>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
