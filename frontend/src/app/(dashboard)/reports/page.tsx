"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Download, Edit3, Eye, FileDown, ShieldCheck, Unlock } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiRequest, downloadFileFromApi } from "@/lib/api";
import type { AssignmentItem, GradingResultDetail } from "@/types";
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
} from "@/components/ui/primitives";

interface ClassReportResponse {
  summary: {
    assignment_id: string;
    assignment_title: string;
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

  const [detail, setDetail] = useState<GradingResultDetail | null>(null);
  const [excelPreview, setExcelPreview] = useState<ExcelPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [focusCell, setFocusCell] = useState<string | null>(null);
  const [adjustScore, setAdjustScore] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [savingAdjust, setSavingAdjust] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    apiRequest<AssignmentItem[]>("/assignments")
      .then((list) => {
        setAssignments(list);
        if (list.length > 0) setAssignmentId(list[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "โหลดรายการงานไม่สำเร็จ"));
  }, []);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดรายงานไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
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

          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-violet-100 bg-violet-50/50 text-left text-xs text-violet-900">
                  <th className="px-4 py-3">เลขที่</th>
                  <th className="px-4 py-3">รหัสนักเรียน</th>
                  <th className="px-4 py-3">ชื่อ-นามสกุล</th>
                  <th className="px-4 py-3">คะแนน</th>
                  <th className="px-4 py-3">เต็ม</th>
                  <th className="px-4 py-3">สถานะ</th>
                  <th className="px-4 py-3 text-right">รายละเอียด</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-violet-50">
                {report.rows.map((r) => (
                  <tr key={r.result_id} className="hover:bg-violet-50/30">
                    <td className="px-4 py-3">{r.seat_number}</td>
                    <td className="px-4 py-3 font-mono text-xs">{r.student_code}</td>
                    <td className="px-4 py-3 font-medium text-violet-950">{r.student_name}</td>
                    <td className="px-4 py-3 font-bold text-violet-900">{r.final_score}</td>
                    <td className="px-4 py-3 text-slate-500">{r.max_score}</td>
                    <td className="px-4 py-3">
                      <Badge tone={r.is_confirmed ? "mint" : r.passed ? "sky" : "rose"}>
                        {r.status_label}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="secondary" onClick={() => openStudentDetail(r.result_id)}>
                        <Eye className="h-3.5 w-3.5" /> ตรวจละเอียด
                      </Button>
                    </td>
                  </tr>
                ))}
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
