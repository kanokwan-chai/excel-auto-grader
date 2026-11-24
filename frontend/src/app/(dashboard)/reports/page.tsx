"use client";

import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, ClipboardCopy, Download, Edit3, Eye, FileDown, RefreshCw, Send, ShieldCheck, Unlock } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiRequest, downloadFileFromApi } from "@/lib/api";
import type { AssignmentItem, GradingResultDetail, Rubric } from "@/types";
import { useToast } from "@/components/ui/toast";
import { ExcelSpreadsheetPreview, type ExcelPreviewData } from "@/components/excel/excel-preview";
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

interface ClassReportResponse {
  summary: {
    assignment_id: string;
    assignment_title: string;
    last_rubric_id?: string | null;
    max_score: number;
    pass_score: number;
    total_students: number;
    highest_score: number;
    lowest_score: number;
    average_score: number;
    passed_count: number;
    failed_count: number;
  };
  distribution: { range: string; count: number }[];
  rows: {
    result_id: string;
    submission_id?: string;
    seat_number: number;
    student_code: string;
    student_name: string;
    final_score: number;
    auto_score: number;
    max_score: number;
    percentage: number;
    passed: boolean;
    is_confirmed: boolean;
    status_label: string;
    deduction_summary?: string;
    deduction_comment?: string;
    is_classroom_linked?: boolean;
  }[];
}

interface BatchPushResponse {
  total: number;
  confirmed_count: number;
  pushed_count: number;
  failed_push_count: number;
  items: {
    result_id: string;
    student_name: string;
    final_score: number;
    pushed_to_classroom: boolean;
    concise_comment: string;
    classroom_message: string;
  }[];
}

export default function ReportsPage() {
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [assignmentId, setAssignmentId] = useState("");
  const [sortBy, setSortBy] = useState("seat");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [report, setReport] = useState<ClassReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Batch selection & push state
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchPushing, setBatchPushing] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchPushResponse | null>(null);

  // Instant re-grade without re-pulling from Classroom
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [regradeRubricId, setRegradeRubricId] = useState("");
  const lastSyncedAssignmentRef = useRef<string>("");
  const pinnedRubricFromUrlRef = useRef<string | null>(null);
  const [regrading, setRegrading] = useState(false);
  const [regradeProgress, setRegradeProgress] = useState<string | null>(null);
  const [overwriteConfirmed, setOverwriteConfirmed] = useState(true);

  const [detail, setDetail] = useState<GradingResultDetail | null>(null);
  const [excelPreview, setExcelPreview] = useState<ExcelPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [focusCell, setFocusCell] = useState<string | null>(null);
  const [adjustScore, setAdjustScore] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [savingAdjust, setSavingAdjust] = useState(false);
  const [conciseComment, setConciseComment] = useState("");
  const [pushingClassroom, setPushingClassroom] = useState(false);
  const [pushFeedbackMsg, setPushFeedbackMsg] = useState<string | null>(null);
  const { toast } = useToast();

  const buildDefaultConciseComment = (d: GradingResultDetail) => {
    const deducted = d.details
      .filter((x) => x.deducted_points > 0)
      .map((x) => `- ${x.item_title} (หัก ${x.deducted_points} คะแนน): ${x.reason || "ไม่ตรงตามเกณฑ์"}`);
    if (deducted.length === 0) {
      return "ไม่ถูกหักคะแนน (ทำถูกต้องครบทุกเกณฑ์)";
    }
    return `รายการที่ถูกหักคะแนน:\n${deducted.join("\n")}`;
  };

  useEffect(() => {
    const sp = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
    const urlRubricId = sp?.get("rubric_id") || null;
    const urlAssignId = sp?.get("assignment_id") || null;
    if (urlRubricId) {
      pinnedRubricFromUrlRef.current = urlRubricId;
    }
    Promise.all([
      apiRequest<AssignmentItem[]>("/assignments"),
      apiRequest<Rubric[]>("/rubrics"),
    ])
      .then(([assignList, rubricList]) => {
        setAssignments(assignList);
        setRubrics(rubricList);
        if (urlAssignId && assignList.some((a) => a.id === urlAssignId)) {
          setAssignmentId(urlAssignId);
        } else if (assignList.length > 0) {
          setAssignmentId(assignList[0].id);
        }
        if (urlRubricId && rubricList.some((r) => r.id === urlRubricId)) {
          setRegradeRubricId(urlRubricId);
        } else if (rubricList.length > 0) {
          setRegradeRubricId(rubricList[0].id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "โหลดรายการงานไม่สำเร็จ"));
  }, []);

  useEffect(() => {
    if (!assignmentId || rubrics.length === 0) return;
    if (pinnedRubricFromUrlRef.current) return;
    const matched = rubrics.find((r) => r.assignment_id === assignmentId);
    if (matched) setRegradeRubricId(matched.id);
  }, [assignmentId, rubrics]);

  const handleQuickRegrade = async (onlySelected: boolean) => {
    if (!assignmentId || !regradeRubricId || !report) {
      toast("กรุณาเลือกงานและเกณฑ์การตรวจก่อน", "error");
      return;
    }
    const targetRows = onlySelected
      ? report.rows.filter((r) => selectedIds.includes(r.result_id))
      : report.rows;
    const subIds = targetRows.map((r) => r.submission_id).filter((id): id is string => Boolean(id));
    if (onlySelected && targetRows.length === 0) {
      toast("กรุณาติ๊กเลือกนักเรียนอย่างน้อย 1 คน", "error");
      return;
    }

    setRegrading(true);
    setRegradeProgress(null);
    const BATCH_SIZE = 10;
    let done = 0;
    try {
      if (subIds.length > 0) {
        const totalBatches = Math.ceil(subIds.length / BATCH_SIZE);
        let sharedJobId: string | undefined = undefined;
        for (let i = 0; i < subIds.length; i += BATCH_SIZE) {
          const chunk = subIds.slice(i, i + BATCH_SIZE);
          const batchNum = Math.floor(i / BATCH_SIZE) + 1;
          setRegradeProgress(`กำลังรีการตรวจ (${done}/${subIds.length} คน)...`);
          const res: { job_id?: string; processed_files: number; batch_processed?: number } = await apiRequest(
            "/grading/run",
            {
              method: "POST",
              body: JSON.stringify({
                assignment_id: assignmentId,
                rubric_id: regradeRubricId,
                submission_ids: chunk,
                force_regrade_confirmed: overwriteConfirmed,
                job_id: sharedJobId,
              }),
            }
          );
          if (res.job_id) sharedJobId = res.job_id;
          done = res.processed_files;
          void batchNum;
          void totalBatches;
        }
      } else {
        setRegradeProgress("กำลังรีการตรวจทั้งห้อง...");
        const res = await apiRequest<{ processed_files: number }>("/grading/run", {
          method: "POST",
          body: JSON.stringify({
            assignment_id: assignmentId,
            rubric_id: regradeRubricId,
            force_regrade_confirmed: overwriteConfirmed,
          }),
        });
        done = res.processed_files;
      }
      toast(`รีการตรวจด้วยเกณฑ์ล่าสุดเรียบร้อยแล้ว (${done} คน) ✨`);
      await loadReport();
    } catch (err) {
      toast(err instanceof Error ? err.message : "รีการตรวจไม่สำเร็จ", "error");
    } finally {
      setRegrading(false);
      setRegradeProgress(null);
    }
  };

  const loadReport = async () => {
    if (!assignmentId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ sort_by: sortBy });
      if (search) params.set("search", search);
      if (statusFilter) params.set("status_filter", statusFilter);
      const data = await apiRequest<ClassReportResponse>(
        `/reports/assignments/${assignmentId}?${params.toString()}`
      );
      setReport(data);
      if (lastSyncedAssignmentRef.current !== assignmentId) {
        lastSyncedAssignmentRef.current = assignmentId;
        if (!pinnedRubricFromUrlRef.current && data.summary.last_rubric_id) {
          setRegradeRubricId(data.summary.last_rubric_id);
        }
        pinnedRubricFromUrlRef.current = null;
      }
      setSelectedIds(data.rows.map((r) => r.result_id));
      setBatchResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดรายงานไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  const toggleSelectRow = (resultId: string) => {
    setSelectedIds((prev) =>
      prev.includes(resultId) ? prev.filter((id) => id !== resultId) : [...prev, resultId]
    );
  };

  const toggleSelectAll = () => {
    if (!report) return;
    if (selectedIds.length === report.rows.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(report.rows.map((r) => r.result_id));
    }
  };

  const handleBatchApproveAndPush = async (returnToStudent: boolean, pushAll: boolean = false) => {
    if (!report || report.rows.length === 0) return;
    const targetIds = pushAll ? report.rows.map((r) => r.result_id) : selectedIds;
    if (targetIds.length === 0) {
      toast("กรุณาเลือกนักเรียนอย่างน้อย 1 คน", "error");
      return;
    }
    setBatchPushing(true);
    setBatchResult(null);
    try {
      const res = await apiRequest<BatchPushResponse>("/classroom/results/batch-approve-and-push", {
        method: "POST",
        body: JSON.stringify({
          result_ids: targetIds,
          return_to_student: returnToStudent,
        }),
      });
      setBatchResult(res);
      toast(
        res.pushed_count > 0
          ? `ส่งคะแนนเข้า Google Classroom สำเร็จ ${res.pushed_count}/${res.total} คน!`
          : `อนุมัติคะแนนและบันทึกคอมเมนต์แล้ว ${res.confirmed_count} คน`,
        res.pushed_count > 0 ? "success" : "info"
      );
      loadReport();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ส่งคะแนนแบบกลุ่มไม่สำเร็จ", "error");
    } finally {
      setBatchPushing(false);
    }
  };

  const handleCopyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast(label);
    } catch {
      toast("ไม่สามารถคัดลอกได้", "error");
    }
  };

  const handleCopyBatchComments = async () => {
    if (!report) return;
    const targetRows = report.rows.filter((r) => selectedIds.includes(r.result_id));
    if (targetRows.length === 0) {
      toast("กรุณาเลือกนักเรียนอย่างน้อย 1 คน", "error");
      return;
    }
    const text = targetRows
      .map((r) => `${r.student_name} (${r.final_score}/${r.max_score}):\n${r.deduction_comment || r.deduction_summary || "ไม่ถูกหักคะแนน"}`)
      .join("\n\n---\n\n");
    await handleCopyText(text, `คัดลอกคอมเมนต์หักคะแนนของนักเรียน ${targetRows.length} คนแล้ว`);
  };

  useEffect(() => {
    if (assignmentId) loadReport();
  }, [assignmentId, sortBy, statusFilter]);

  const openStudentDetail = async (resultId: string) => {
    setExcelPreview(null);
    setFocusCell(null);
    setPreviewLoading(true);
    try {
      const [d, prev] = await Promise.all([
        apiRequest<GradingResultDetail>(`/grading/results/${resultId}`),
        apiRequest<ExcelPreviewData>(`/grading/results/${resultId}/preview`).catch(() => null),
      ]);
      setDetail(d);
      setExcelPreview(prev);
      setAdjustScore(String(d.final_score));
      setAdjustReason("");
      setConciseComment(d.teacher_comment || buildDefaultConciseComment(d));
      setPushFeedbackMsg(null);
    } catch (err) {
      toast(err instanceof Error ? err.message : "โหลดรายละเอียดคะแนนไม่สำเร็จ", "error");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleAdjustScore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!detail) return;
    setSavingAdjust(true);
    try {
      await apiRequest(`/grading/results/${detail.id}/adjust`, {
        method: "PUT",
        body: JSON.stringify({ new_score: Number(adjustScore), reason: adjustReason }),
      });
      toast("บันทึกการปรับคะแนนเรียบร้อยแล้ว");
      await openStudentDetail(detail.id);
      loadReport();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ปรับคะแนนไม่สำเร็จ", "error");
    } finally {
      setSavingAdjust(false);
    }
  };

  const handleApproveAndPush = async (returnToStudent: boolean) => {
    if (!detail) return;
    setPushingClassroom(true);
    setPushFeedbackMsg(null);
    try {
      const res = await apiRequest<{
        confirmed: boolean;
        pushed_to_classroom: boolean;
        concise_comment: string;
        classroom_message: string;
      }>(`/classroom/results/${detail.id}/approve-and-push`, {
        method: "POST",
        body: JSON.stringify({
          comment: conciseComment,
          return_to_student: returnToStudent,
        }),
      });
      setPushFeedbackMsg(res.classroom_message);
      toast(
        res.pushed_to_classroom ? "อนุมัติและส่งคะแนนเข้า Google Classroom สำเร็จ!" : "อนุมัติคะแนนและบันทึกคอมเมนต์แล้ว",
        res.pushed_to_classroom ? "success" : "info"
      );
      await openStudentDetail(detail.id);
      setPushFeedbackMsg(res.classroom_message);
      loadReport();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ส่งคะแนนไม่สำเร็จ", "error");
    } finally {
      setPushingClassroom(false);
    }
  };

  const handleCopyComment = async () => {
    try {
      await navigator.clipboard.writeText(conciseComment);
      toast("คัดลอกคอมเมนต์กระชับแล้ว (นำไปวางใน Google Classroom ได้เลย)");
    } catch {
      toast("ไม่สามารถคัดลอกได้", "error");
    }
  };

  const handleToggleConfirm = async () => {
    if (!detail) return;
    const action = detail.is_confirmed ? "unconfirm" : "confirm";
    try {
      await apiRequest(`/grading/results/${detail.id}/${action}`, { method: "POST" });
      toast(detail.is_confirmed ? "ยกเลิกการยืนยันคะแนนแล้ว" : "ยืนยันคะแนนเรียบร้อยแล้ว (ระบบจะไม่เขียนทับอัตโนมัติ)");
      await openStudentDetail(detail.id);
      loadReport();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ดำเนินการไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">คะแนนและรายงานทั้งห้อง</h1>
          <p className="text-sm text-slate-500">ตรวจสอบผลรายบุคคล เปรียบเทียบสูตร ปรับคะแนน ยืนยัน และส่งออก Excel/CSV/PDF</p>
        </div>
        {assignmentId && (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => downloadFileFromApi(`/reports/assignments/${assignmentId}/export/excel`, "excel_grades.xlsx")}
            >
              <Download className="h-4 w-4" /> ส่งออก Excel (.xlsx)
            </Button>
            <Button
              variant="outline"
              onClick={() => downloadFileFromApi(`/reports/assignments/${assignmentId}/export/csv`, "excel_grades.csv")}
            >
              <FileDown className="h-4 w-4" /> ส่งออก CSV
            </Button>
          </div>
        )}
      </div>

      <Card className="grid gap-3 sm:grid-cols-4 p-4">
        <Select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}>
          <option value="">-- เลือกงาน --</option>
          {assignments.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
        </Select>
        <Input
          placeholder="ค้นหาชื่อหรือรหัสนักเรียน..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadReport()}
        />
        <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="seat">เรียงตามเลขที่</option>
          <option value="score_desc">คะแนนมากไปน้อย</option>
          <option value="score_asc">คะแนนน้อยไปมาก</option>
        </Select>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">ทุกสถานะ</option>
          <option value="passed">ผ่านเกณฑ์</option>
          <option value="failed">ไม่ผ่านเกณฑ์</option>
          <option value="confirmed">ยืนยันคะแนนแล้ว</option>
        </Select>
      </Card>

      {error && <ErrorBanner message={error} onRetry={loadReport} />}

      {loading ? (
        <Skeleton className="h-72" />
      ) : !report || report.rows.length === 0 ? (
        <EmptyState title="ยังไม่มีผลคะแนนสำหรับงานนี้" description="สั่งตรวจงาน Excel ก่อนเพื่อดูรายงานคะแนนและกราฟการกระจายคะแนน" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-5">
            <Card className="p-4"><p className="text-xs text-slate-500">คะแนนสูงสุด</p><p className="text-xl font-bold text-emerald-700">{report.summary.highest_score}</p></Card>
            <Card className="p-4"><p className="text-xs text-slate-500">คะแนนต่ำสุด</p><p className="text-xl font-bold text-rose-600">{report.summary.lowest_score}</p></Card>
            <Card className="p-4"><p className="text-xs text-slate-500">คะแนนเฉลี่ย</p><p className="text-xl font-bold text-violet-800">{report.summary.average_score}</p></Card>
            <Card className="p-4"><p className="text-xs text-slate-500">ผ่านเกณฑ์</p><p className="text-xl font-bold text-teal-700">{report.summary.passed_count} คน</p></Card>
            <Card className="p-4"><p className="text-xs text-slate-500">ไม่ผ่านเกณฑ์</p><p className="text-xl font-bold text-amber-700">{report.summary.failed_count} คน</p></Card>
          </div>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-violet-950">กราฟการกระจายคะแนนทั้งห้อง</h2>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={report.distribution}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EDE9FE" />
                  <XAxis dataKey="range" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="จำนวนนักเรียน" fill="#A78BFA" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Instant Re-grade Bar (No Classroom Re-sync Needed!) */}
          <Card className="border-sky-200 bg-sky-50/40 p-4 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-sky-950">
                  🔄 รีการตรวจทันที (ใช้ไฟล์เดิมที่ดึงไว้แล้ว ไม่ต้องกลับไปดึงจาก Classroom ใหม่)
                </p>
                <p className="text-xs text-slate-600">
                  เมื่อแก้ไขเกณฑ์เสร็จ เลือกเกณฑ์ด้านขวาแล้วกดรีการตรวจได้ทันที
                </p>
                <label className="mt-1 inline-flex items-center gap-1.5 text-xs font-semibold text-sky-900 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={overwriteConfirmed}
                    onChange={(e) => setOverwriteConfirmed(e.target.checked)}
                    className="rounded accent-sky-600"
                  />
                  คำนวณคะแนนใหม่ทับคนที่เคยกดยืนยันคะแนนแล้วด้วย
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={regradeRubricId}
                  onChange={(e) => setRegradeRubricId(e.target.value)}
                  className="w-64 bg-white"
                >
                  <option value="">-- เลือกเกณฑ์การตรวจ --</option>
                  {rubrics.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} (v{r.current_version} • {r.total_points} คะแนน)
                    </option>
                  ))}
                </Select>
                <Button
                  size="sm"
                  variant="outline"
                  loading={regrading}
                  disabled={!regradeRubricId || selectedIds.length === 0}
                  onClick={() => handleQuickRegrade(true)}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> รีการตรวจที่เลือก ({selectedIds.length})
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={regrading}
                  disabled={!regradeRubricId}
                  onClick={() => handleQuickRegrade(false)}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> รีการตรวจทั้งห้อง ({report.rows.length})
                </Button>
              </div>
            </div>
            {regradeProgress && (
              <div className="rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs font-semibold text-sky-900 animate-pulse">
                ⏳ {regradeProgress}
              </div>
            )}
          </Card>

          {/* Batch Approve & Push to Google Classroom Bar */}
          <Card className="border-emerald-200 bg-emerald-50/40 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-emerald-950">
                  ส่งคะแนนเข้า Google Classroom แบบกลุ่ม / เลือกเฉพาะคน
                </p>
                <p className="text-xs text-slate-600">
                  เลือกแล้ว <strong>{selectedIds.length}</strong> จาก {report.rows.length} คน •
                  คอมเมนต์จะสรุป <strong>เฉพาะส่วนที่ถูกหักคะแนนพร้อมสาเหตุ</strong> อัตโนมัติ
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyBatchComments}
                  disabled={selectedIds.length === 0}
                >
                  <ClipboardCopy className="h-3.5 w-3.5" /> คัดลอกคอมเมนต์ ({selectedIds.length})
                </Button>
                <Button
                  size="sm"
                  variant="mint"
                  loading={batchPushing}
                  disabled={selectedIds.length === 0}
                  onClick={() => handleBatchApproveAndPush(false, false)}
                >
                  <ShieldCheck className="h-3.5 w-3.5" /> ส่งคะแนนที่เลือก (Draft)
                </Button>
                <Button
                  size="sm"
                  loading={batchPushing}
                  disabled={selectedIds.length === 0}
                  onClick={() => handleBatchApproveAndPush(true, false)}
                >
                  <Send className="h-3.5 w-3.5" /> ส่งและคืนงานที่เลือก (Return)
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={batchPushing}
                  onClick={() => handleBatchApproveAndPush(true, true)}
                >
                  <Send className="h-3.5 w-3.5" /> ส่งทั้งหมดในครั้งเดียว ({report.rows.length})
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-slate-500">
              หมายเหตุ: Google Classroom API รองรับการส่งคะแนนและคืนงานอัตโนมัติทีละหลายคน (สำหรับงานที่สร้างจากเมนู &ldquo;สร้างงานลง Classroom&rdquo;) แต่ยังไม่มี API สำหรับโพสต์ Private Comment แทนครูโดยตรง — ระบบจึงสร้างคอมเมนต์เฉพาะจุดที่หักคะแนนไว้ให้กดคัดลอกได้ทันทีทั้งรายคนและแบบกลุ่ม
            </p>
            {batchResult && (
              <div className="rounded-xl border border-emerald-200 bg-white p-3 text-xs space-y-1.5">
                <p className="font-semibold text-emerald-900">
                  สรุปการส่งแบบกลุ่ม: อนุมัติแล้ว {batchResult.confirmed_count}/{batchResult.total} คน •
                  ส่งเข้า Google Classroom สำเร็จ {batchResult.pushed_count} คน
                  {batchResult.failed_push_count > 0 && ` • ยังไม่ได้ส่งเข้า Classroom ${batchResult.failed_push_count} คน`}
                </p>
                {batchResult.failed_push_count > 0 && batchResult.items.find((i) => !i.pushed_to_classroom) && (
                  <p className="text-amber-700">
                    หมายเหตุ: {batchResult.items.find((i) => !i.pushed_to_classroom)?.classroom_message}
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-violet-100 bg-violet-50/50 text-left text-xs text-violet-900">
                  <th className="px-3 py-3 w-10 text-center">
                    <input
                      type="checkbox"
                      checked={report.rows.length > 0 && selectedIds.length === report.rows.length}
                      onChange={toggleSelectAll}
                      aria-label="เลือกทั้งหมด"
                      className="h-4 w-4 rounded border-violet-300 accent-violet-600 cursor-pointer"
                    />
                  </th>
                  <th className="px-3 py-3">เลขที่</th>
                  <th className="px-3 py-3">ชื่อ-นามสกุล</th>
                  <th className="px-3 py-3">คะแนน</th>
                  <th className="px-3 py-3">ส่วนที่ถูกหักคะแนน (คอมเมนต์)</th>
                  <th className="px-3 py-3">สถานะ</th>
                  <th className="px-4 py-3 text-right">จัดการ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-violet-50">
                {report.rows.map((r) => {
                  const checked = selectedIds.includes(r.result_id);
                  return (
                    <tr
                      key={r.result_id}
                      className={`hover:bg-violet-50/30 ${checked ? "bg-violet-50/20" : ""}`}
                    >
                      <td className="px-3 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSelectRow(r.result_id)}
                          aria-label={`เลือก ${r.student_name}`}
                          className="h-4 w-4 rounded border-violet-300 accent-violet-600 cursor-pointer"
                        />
                      </td>
                      <td className="px-3 py-3">{r.seat_number}</td>
                      <td className="px-3 py-3">
                        <p className="font-medium text-violet-950">{r.student_name}</p>
                        <p className="font-mono text-[11px] text-slate-400">{r.student_code}</p>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className="font-bold text-violet-900">{r.final_score}</span>
                        <span className="text-slate-400"> / {r.max_score}</span>
                      </td>
                      <td className="px-3 py-3 max-w-xs">
                        <p
                          className={`text-xs line-clamp-2 ${
                            r.deduction_summary && r.deduction_summary !== "ไม่ถูกหักคะแนน"
                              ? "text-rose-700"
                              : "text-emerald-700"
                          }`}
                          title={r.deduction_comment || r.deduction_summary}
                        >
                          {r.deduction_summary || "ไม่ถูกหักคะแนน"}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <Badge tone={r.is_confirmed ? "mint" : r.passed ? "sky" : "rose"}>
                          {r.status_label}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            title="คัดลอกคอมเมนต์เฉพาะส่วนที่ถูกหักคะแนน"
                            onClick={() =>
                              handleCopyText(
                                r.deduction_comment || r.deduction_summary || "ไม่ถูกหักคะแนน",
                                `คัดลอกคอมเมนต์ของ ${r.student_name} แล้ว`
                              )
                            }
                          >
                            <ClipboardCopy className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => openStudentDetail(r.result_id)}>
                            <Eye className="h-3.5 w-3.5" /> ตรวจละเอียด
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {/* Individual Student Grading Report Modal (Side-by-Side Live Excel Preview + Score Breakdown) */}
      <Modal
        open={Boolean(detail)}
        onClose={() => {
          setDetail(null);
          setExcelPreview(null);
        }}
        title={`ผลการตรวจรายบุคคล: ${detail?.student_name || ""}`}
        maxWidth="max-w-7xl"
      >
        {detail && (
          <div className="space-y-4">
            {/* Top Score Header */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-violet-50 p-4">
              <div>
                <p className="text-sm font-bold text-violet-950">{detail.assignment_title}</p>
                <p className="text-xs text-slate-600">
                  รหัส: {detail.student_code} • เกณฑ์เวอร์ชัน {detail.rubric_version}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-2xl font-bold text-violet-900">
                    {detail.final_score} / {detail.max_score}
                  </p>
                  <p className="text-xs text-slate-500">{detail.percentage}%</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => downloadFileFromApi(`/reports/results/${detail.id}/export/pdf`, `report_${detail.student_code}.pdf`)}>
                  <FileDown className="h-3.5 w-3.5" /> PDF
                </Button>
                <Button size="sm" variant={detail.is_confirmed ? "outline" : "mint"} onClick={handleToggleConfirm}>
                  {detail.is_confirmed ? <><Unlock className="h-3.5 w-3.5" /> ยกเลิกยืนยัน</> : <><ShieldCheck className="h-3.5 w-3.5" /> ยืนยันคะแนน</>}
                </Button>
              </div>
            </div>

            {/* Side-by-Side Workspace: Left = Interactive Excel Screen | Right = Grading Report & Adjustments */}
            <div className="grid gap-5 lg:grid-cols-12 items-start">
              {/* Left 7 Cols: Live Excel Spreadsheet Preview */}
              <div className="lg:col-span-7 space-y-2">
                <p className="text-xs font-bold text-violet-950">
                  พรีวิวไฟล์ Excel ของนักเรียน (คลิกที่ช่องใดก็ได้เพื่อดูสูตรในแถบ fx หรือกดสลับดูสูตรทุกช่อง)
                </p>
                {previewLoading ? (
                  <Skeleton className="h-80" />
                ) : excelPreview ? (
                  <ExcelSpreadsheetPreview data={excelPreview} focusCell={focusCell} />
                ) : (
                  <div className="rounded-2xl border border-dashed border-violet-200 bg-violet-50/40 p-8 text-center text-xs text-slate-500">
                    ไม่สามารถโหลดพรีวิวไฟล์ Excel สำหรับรายการนี้ได้
                  </div>
                )}
              </div>

              {/* Right 5 Cols: Deduction Summary + Rubric Breakdown + Override */}
              <div className="lg:col-span-5 space-y-4 max-h-[65vh] overflow-y-auto pr-1">
                {/* Deduction Summary Panel */}
                {detail.details.some((d) => d.deducted_points > 0) ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50/60 p-3.5 space-y-2">
                    <p className="text-xs font-bold text-rose-900">
                      สรุปรายการที่ถูกหักคะแนน ({detail.details.filter((d) => d.deducted_points > 0).length} รายการ)
                    </p>
                    <div className="space-y-2">
                      {detail.details
                        .filter((d) => d.deducted_points > 0)
                        .map((d) => (
                          <div
                            key={d.id}
                            onClick={() => d.target_cell && setFocusCell(d.target_cell)}
                            className="cursor-pointer rounded-xl border border-rose-100 bg-white px-3 py-2 text-xs hover:border-rose-300 transition"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold text-rose-950">
                                {d.item_title} {d.target_cell ? `(${d.target_cell})` : ""}
                              </span>
                              <Badge tone="rose">หัก -{d.deducted_points}</Badge>
                            </div>
                            <p className="mt-1 text-slate-700">
                              <strong>สาเหตุ:</strong> {d.reason || "ไม่ตรงตามเกณฑ์ที่กำหนด"}
                            </p>
                            {d.suggestion && (
                              <p className="mt-0.5 text-violet-700">
                                <strong>แนะนำ:</strong> {d.suggestion}
                              </p>
                            )}
                          </div>
                        ))}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-xs font-medium text-emerald-900">
                    ไม่พบรายการที่ถูกหักคะแนน — นักเรียนทำผ่านครบทุกเกณฑ์!
                  </div>
                )}

                {/* Rubric Breakdown Table */}
                <div className="overflow-x-auto rounded-2xl border border-violet-100">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-violet-50/70 text-left text-violet-900">
                        <th className="px-2.5 py-2">รายการตรวจ</th>
                        <th className="px-2.5 py-2">สูตรเฉลย / นักเรียน</th>
                        <th className="px-2.5 py-2 text-right">คะแนน</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-violet-50">
                      {detail.details.map((d) => (
                        <tr
                          key={d.id}
                          onClick={() => d.target_cell && setFocusCell(d.target_cell)}
                          className="cursor-pointer hover:bg-violet-50/40"
                        >
                          <td className="px-2.5 py-2">
                            <p className="font-semibold text-violet-950">{d.item_title}</p>
                            <p className="text-[11px] text-slate-500">{d.target_cell || "-"} • {d.reason}</p>
                          </td>
                          <td className="px-2.5 py-2 space-y-0.5 font-mono text-[11px]">
                            {d.expected_formula && <div className="text-emerald-700">เฉลย: {d.expected_formula}</div>}
                            {d.actual_formula && <div className="text-slate-700">ส่งมา: {d.actual_formula}</div>}
                          </td>
                          <td className="px-2.5 py-2 text-right">
                            <Badge tone={d.passed ? "mint" : "rose"}>
                              {d.earned_points}/{d.max_points}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Approve & Push to Google Classroom with Concise Feedback Comment */}
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-3.5 space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="flex items-center gap-1.5 text-xs font-bold text-emerald-950">
                      <Send className="h-3.5 w-3.5 text-emerald-600" />
                      อนุมัติและส่งคะแนนเข้า Google Classroom + คอมเมนต์เฉพาะจุดที่หักคะแนน
                    </p>
                    <Button size="sm" variant="outline" onClick={handleCopyComment}>
                      <ClipboardCopy className="h-3 w-3" /> คัดลอกคอมเมนต์
                    </Button>
                  </div>
                  <Textarea
                    rows={3}
                    value={conciseComment}
                    onChange={(e) => setConciseComment(e.target.value)}
                    className="text-xs"
                    placeholder="คอมเมนต์เฉพาะรายการที่ถูกหักคะแนนพร้อมสาเหตุ..."
                  />
                  {pushFeedbackMsg && (
                    <p className="rounded-xl bg-white px-3 py-2 text-[11px] text-emerald-900 border border-emerald-200">
                      {pushFeedbackMsg}
                    </p>
                  )}
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button
                      size="sm"
                      variant="mint"
                      loading={pushingClassroom}
                      onClick={() => handleApproveAndPush(false)}
                    >
                      <ShieldCheck className="h-3.5 w-3.5" /> อนุมัติและส่งคะแนน (Draft)
                    </Button>
                    <Button
                      size="sm"
                      loading={pushingClassroom}
                      onClick={() => handleApproveAndPush(true)}
                    >
                      <Send className="h-3.5 w-3.5" /> อนุมัติและคืนงาน (Return)
                    </Button>
                  </div>
                </div>

                {/* Teacher Manual Override Form */}
                <form onSubmit={handleAdjustScore} className="rounded-2xl border border-violet-100 bg-pink-50/30 p-3.5 space-y-2.5">
                  <p className="flex items-center gap-1.5 text-xs font-bold text-violet-950">
                    <Edit3 className="h-3.5 w-3.5" /> ครูแก้ไขคะแนน (บันทึกประวัติทุกครั้ง)
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Input
                      type="number"
                      step="0.25"
                      max={detail.max_score}
                      min={0}
                      value={adjustScore}
                      onChange={(e) => setAdjustScore(e.target.value)}
                      placeholder="คะแนนใหม่"
                      required
                    />
                    <Input
                      value={adjustReason}
                      onChange={(e) => setAdjustReason(e.target.value)}
                      placeholder="เหตุผลการปรับคะแนน *"
                      required
                      className="sm:col-span-2"
                    />
                  </div>
                  <div className="flex justify-end">
                    <Button size="sm" type="submit" loading={savingAdjust}>
                      <CheckCircle2 className="h-3.5 w-3.5" /> บันทึกคะแนนใหม่
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
