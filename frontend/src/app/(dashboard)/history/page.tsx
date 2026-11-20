"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Eye, History, ShieldCheck, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatThaiDate } from "@/lib/utils";
import type { GradingResultDetail } from "@/types";
import { useToast } from "@/components/ui/toast";
import { ExcelSpreadsheetPreview, type ExcelPreviewData } from "@/components/excel/excel-preview";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  Modal,
  Skeleton,
} from "@/components/ui/primitives";

interface HistoryResponse {
  jobs: {
    id: string;
    assignment_id: string;
    assignment_title: string;
    status: string;
    total_files: number;
    processed_files: number;
    failed_files: number;
    started_at?: string | null;
    completed_at?: string | null;
  }[];
  adjustments: {
    id: string;
    result_id: string;
    assignment_title: string;
    student_name: string;
    previous_score: number;
    new_score: number;
    reason: string;
    action_type: string;
    is_confirmed: boolean;
    created_at?: string | null;
  }[];
}

export default function HistoryPage() {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ type: "job" | "adjustment"; id: string; label: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [detail, setDetail] = useState<GradingResultDetail | null>(null);
  const [preview, setPreview] = useState<ExcelPreviewData | null>(null);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiRequest<HistoryResponse>("/grading/history"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดประวัติการตรวจไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleOpenResult = async (resultId: string) => {
    setPreview(null);
    try {
      const [d, p] = await Promise.all([
        apiRequest<GradingResultDetail>(`/grading/results/${resultId}`),
        apiRequest<ExcelPreviewData>(`/grading/results/${resultId}/preview`).catch(() => null),
      ]);
      setDetail(d);
      setPreview(p);
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถเปิดดูผลการตรวจได้", "error");
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const url =
        deleteTarget.type === "job"
          ? `/grading/jobs/${deleteTarget.id}`
          : `/grading/adjustments/${deleteTarget.id}`;
      await apiRequest(url, { method: "DELETE" });
      toast("ลบประวัติการตรวจเรียบร้อยแล้ว (งานเด็กใน Google Classroom ยังอยู่ครบถ้วน)");
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ลบประวัติไม่สำเร็จ", "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-violet-950">ประวัติการตรวจและแก้ไขคะแนน</h1>
        <p className="text-sm text-slate-500">เปิดดูรายละเอียดผลการตรวจย้อนหลัง และลบประวัติการตรวจได้</p>
      </div>

      {/* Reassurance Banner */}
      <div className="flex items-center gap-2.5 rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-xs text-emerald-900">
        <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600" />
        <span>
          <strong>ปลอดภัยต่อ Google Classroom 100%:</strong> การลบประวัติในหน้านี้จะลบเฉพาะบันทึกในระบบตรวจงานนี้เท่านั้น
          <strong> ไม่มีการลบหรือแก้ไขไฟล์งานของนักเรียนใน Google Classroom / Google Drive</strong> (ระบบใช้สิทธิ์แบบอ่านอย่างเดียว Read-Only)
        </span>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <Skeleton className="h-64" />
      ) : !data ? null : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="space-y-4">
            <h2 className="flex items-center gap-2 text-base font-semibold text-violet-950">
              <History className="h-4 w-4 text-violet-600" /> ประวัติรอบการตรวจอัตโนมัติ ({data.jobs.length})
            </h2>
            {data.jobs.length === 0 ? (
              <EmptyState title="ยังไม่มีรอบการตรวจ" description="ประวัติการสั่งตรวจงาน Excel จะบันทึกไว้ที่นี่" />
            ) : (
              <div className="space-y-3">
                {data.jobs.map((j) => (
                  <div key={j.id} className="flex items-center justify-between gap-3 rounded-2xl border border-violet-50 bg-violet-50/30 p-3.5 text-sm">
                    <div className="min-w-0">
                      <p className="font-semibold text-violet-950 truncate">{j.assignment_title}</p>
                      <p className="text-xs text-slate-500">
                        ตรวจ {j.processed_files}/{j.total_files} ไฟล์ • ผิดพลาด {j.failed_files} • {formatThaiDate(j.completed_at || j.started_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge tone={j.status === "completed" ? "mint" : "amber"}>{j.status}</Badge>
                      <Link href="/reports">
                        <Button size="sm" variant="secondary" title="เข้าไปดูผลคะแนน">
                          <Eye className="h-3.5 w-3.5" /> ดูผล
                        </Button>
                      </Link>
                      <Button
                        size="sm"
                        variant="ghost"
                        title="ลบประวัติรอบการตรวจนี้"
                        onClick={() => setDeleteTarget({ type: "job", id: j.id, label: j.assignment_title })}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="space-y-4">
            <h2 className="text-base font-semibold text-violet-950">
              ประวัติการปรับและยืนยันคะแนนโดยครู ({data.adjustments.length})
            </h2>
            {data.adjustments.length === 0 ? (
              <EmptyState title="ยังไม่มีการปรับคะแนน" description="ทุกครั้งที่ครูแก้ไขหรือยืนยันคะแนนจะถูกบันทึกเหตุผลไว้ที่นี่" />
            ) : (
              <div className="space-y-3">
                {data.adjustments.map((adj) => (
                  <div key={adj.id} className="rounded-2xl border border-violet-50 bg-pink-50/30 p-3.5 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold text-violet-950">{adj.student_name}</p>
                      <div className="flex items-center gap-1.5">
                        <Badge tone="lavender">{adj.action_type}</Badge>
                        <Button size="sm" variant="outline" onClick={() => handleOpenResult(adj.result_id)}>
                          <Eye className="h-3.5 w-3.5" /> ดูงาน
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setDeleteTarget({
                              type: "adjustment",
                              id: adj.id,
                              label: `${adj.student_name} (${adj.assignment_title})`,
                            })
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-slate-600 mt-1">
                      {adj.assignment_title} • คะแนน {adj.previous_score} → <strong>{adj.new_score}</strong>
                    </p>
                    <p className="text-xs text-slate-500 mt-1">เหตุผล: {adj.reason}</p>
                    <p className="text-[11px] text-slate-400 mt-1">{formatThaiDate(adj.created_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Quick View Modal directly from History */}
      <Modal
        open={Boolean(detail)}
        onClose={() => {
          setDetail(null);
          setPreview(null);
        }}
        title={`ดูผลการตรวจย้อนหลัง: ${detail?.student_name || ""}`}
        maxWidth="max-w-6xl"
      >
        {detail && (
          <div className="grid gap-4 lg:grid-cols-12 items-start">
            <div className="lg:col-span-7">
              {preview ? (
                <ExcelSpreadsheetPreview data={preview} />
              ) : (
                <p className="text-xs text-slate-500">ไม่มีพรีวิวไฟล์ Excel</p>
              )}
            </div>
            <div className="lg:col-span-5 space-y-3">
              <div className="rounded-2xl bg-violet-50 p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-violet-950">{detail.assignment_title}</p>
                  <p className="text-xs text-slate-500">เกณฑ์เวอร์ชัน {detail.rubric_version}</p>
                </div>
                <p className="text-2xl font-bold text-violet-900">
                  {detail.final_score}/{detail.max_score}
                </p>
              </div>
              <div className="space-y-2 max-h-[50vh] overflow-y-auto">
                {detail.details.map((d) => (
                  <div key={d.id} className="rounded-xl border border-violet-100 bg-white p-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-violet-950">{d.item_title}</span>
                      <Badge tone={d.passed ? "mint" : "rose"}>
                        {d.earned_points}/{d.max_points}
                      </Badge>
                    </div>
                    <p className="mt-1 text-slate-600">{d.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="ยืนยันการลบประวัติการตรวจ"
        description={`ต้องการลบประวัติ "${deleteTarget?.label}" ออกจากระบบนี้ใช่หรือไม่? (ไฟล์และงานของนักเรียนใน Google Classroom จะไม่ถูกลบหรือเปลี่ยนแปลงใด ๆ)`}
        confirmLabel="ลบประวัติ"
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
