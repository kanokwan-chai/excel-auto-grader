"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Download, Eye, FileDown, FileSpreadsheet, RefreshCw } from "lucide-react";
import { apiRequest, downloadFileFromApi } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Icon3D,
  Skeleton,
} from "@/components/ui/primitives";

interface ClassroomExportAssignment {
  assignment_id: string;
  title: string;
  max_score: number;
  graded_count: number;
  average_score: number;
  passed_count: number;
}

interface ClassroomExportRoom {
  classroom_id: string;
  classroom_name: string;
  section?: string | null;
  room?: string | null;
  total_students: number;
  total_assignments: number;
  total_max_score: number;
  assignments: ClassroomExportAssignment[];
}

export default function ClassroomExportsPage() {
  const [rooms, setRooms] = useState<ClassroomExportRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest<{ classrooms: ClassroomExportRoom[] }>("/reports/classrooms/summary");
      setRooms(res.classrooms || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลห้องเรียนไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDownload = async (key: string, path: string, filename: string, label: string) => {
    setDownloadingKey(key);
    try {
      await downloadFileFromApi(path, filename);
      toast(`ดาวน์โหลด ${label} เรียบร้อยแล้ว ✨`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "ส่งออกไฟล์ไม่สำเร็จ", "error");
    } finally {
      setDownloadingKey(null);
    }
  };

  const safeSlug = (name: string) =>
    name
      .replace(/[\\/:*?"<>|]+/g, "_")
      .replace(/\s+/g, "_")
      .slice(0, 40) || "classroom";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Icon3D emoji="📤" tone="yellow" size="lg" />
          <div>
            <h1 className="text-2xl font-extrabold text-[#172B1C]">ส่งออกคะแนนแยกตามห้องเรียน</h1>
            <p className="text-sm text-[#5C7061]">
              ดาวน์โหลดสมุดคะแนนรวมทุกงานของแต่ละห้องเป็น Excel (.xlsx) พร้อมสูตรรวมและแยกแท็บรายใบงาน หรือไฟล์ CSV ได้ใน 1 คลิก
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={load} loading={loading}>
          <RefreshCw className="h-4 w-4" /> รีเฟรชข้อมูล
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : rooms.length === 0 ? (
        <EmptyState
          title="ยังไม่มีคะแนนพร้อมส่งออก"
          description="ตรวจงานจากเมนู Google Classroom อย่างน้อย 1 งานก่อน แล้วระบบจะแยกห้องให้ส่งออกคะแนนอัตโนมัติที่นี่"
          action={
            <Link href="/google-classroom">
              <Button>🎓 ไปตรวจงานใน Google Classroom</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {rooms.map((rm) => (
            <Card key={rm.classroom_id} className="space-y-4 clay-card-hover">
              {/* Classroom Header */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <Icon3D emoji="🏫" tone="sky" size="md" />
                  <div className="min-w-0">
                    <h2 className="text-lg font-extrabold text-[#172B1C] truncate">
                      {rm.classroom_name}
                    </h2>
                    <p className="text-xs text-[#5C7061]">
                      นักเรียนที่มีคะแนน {rm.total_students} คน • ตรวจแล้ว {rm.total_assignments} ใบงาน • เต็มรวม{" "}
                      {rm.total_max_score} คะแนน
                    </p>
                  </div>
                </div>
                <Badge tone="mint">{rm.total_assignments} งาน</Badge>
              </div>

              {/* Combined Classroom Export Buttons */}
              <div className="flex flex-wrap gap-2 rounded-2xl border border-[#D8EED3] bg-[#F4FBF2] p-3">
                <Button
                  size="sm"
                  variant="primary"
                  loading={downloadingKey === `room-xlsx-${rm.classroom_id}`}
                  onClick={() =>
                    handleDownload(
                      `room-xlsx-${rm.classroom_id}`,
                      `/reports/classrooms/${rm.classroom_id}/export/excel`,
                      `คะแนนรวม_${safeSlug(rm.classroom_name)}.xlsx`,
                      `Excel รวมทั้งห้อง (${rm.classroom_name})`
                    )
                  }
                >
                  <FileSpreadsheet className="h-4 w-4" /> ส่งออก Excel รวมทุกงาน (.xlsx)
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={downloadingKey === `room-csv-${rm.classroom_id}`}
                  onClick={() =>
                    handleDownload(
                      `room-csv-${rm.classroom_id}`,
                      `/reports/classrooms/${rm.classroom_id}/export/csv`,
                      `คะแนนรวม_${safeSlug(rm.classroom_name)}.csv`,
                      `CSV รวมทั้งห้อง (${rm.classroom_name})`
                    )
                  }
                >
                  <FileDown className="h-4 w-4" /> ส่งออก CSV รวม (.csv)
                </Button>
              </div>

              {/* Per-Assignment Quick Exports inside this Room */}
              <div className="space-y-2">
                <p className="text-xs font-bold text-[#39553E]">
                  แยกส่งออกรายใบงานในห้องนี้:
                </p>
                <div className="divide-y divide-[#EAF5E7] rounded-2xl border border-[#E2F0DF] bg-white">
                  {rm.assignments.map((a) => (
                    <div
                      key={a.assignment_id}
                      className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-xs"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-bold text-[#172B1C] truncate">{a.title}</p>
                        <p className="text-[11px] text-[#5C7061]">
                          ตรวจแล้ว {a.graded_count} คน • เฉลี่ย {a.average_score}/{a.max_score} คะแนน
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Button
                          size="sm"
                          variant="mint"
                          loading={downloadingKey === `a-xlsx-${a.assignment_id}`}
                          onClick={() =>
                            handleDownload(
                              `a-xlsx-${a.assignment_id}`,
                              `/reports/assignments/${a.assignment_id}/export/excel`,
                              `${safeSlug(rm.classroom_name)}_${safeSlug(a.title)}.xlsx`,
                              `Excel (${a.title})`
                            )
                          }
                        >
                          <Download className="h-3 w-3" /> .xlsx
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          loading={downloadingKey === `a-csv-${a.assignment_id}`}
                          onClick={() =>
                            handleDownload(
                              `a-csv-${a.assignment_id}`,
                              `/reports/assignments/${a.assignment_id}/export/csv`,
                              `${safeSlug(rm.classroom_name)}_${safeSlug(a.title)}.csv`,
                              `CSV (${a.title})`
                            )
                          }
                        >
                          <FileDown className="h-3 w-3" /> .csv
                        </Button>
                        <Link href={`/reports?assignment_id=${encodeURIComponent(a.assignment_id)}`}>
                          <Button size="sm" variant="ghost" title="เปิดดูหน้ารายงานของงานนี้">
                            <Eye className="h-3.5 w-3.5" />
                          </Button>
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
