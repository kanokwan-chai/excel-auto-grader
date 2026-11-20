"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Award,
  BookOpen,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  FolderKanban,
  GraduationCap,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiRequest } from "@/lib/api";
import { formatThaiDate } from "@/lib/utils";
import type { DashboardSummary } from "@/types";
import { Badge, Button, Card, EmptyState, ErrorBanner, Skeleton } from "@/components/ui/primitives";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest<DashboardSummary>("/dashboard/summary");
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถโหลดข้อมูลภาพรวมได้");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return <ErrorBanner message={error || "ไม่พบข้อมูล"} onRetry={load} />;
  }

  const kpiCards = [
    { label: "ชั้นเรียนทั้งหมด", value: data.kpis.total_classes, icon: BookOpen, bg: "bg-violet-100 text-violet-700" },
    { label: "นักเรียนทั้งหมด", value: data.kpis.total_students, icon: Users, bg: "bg-pink-100 text-pink-700" },
    { label: "งานทั้งหมด", value: data.kpis.total_assignments, icon: FolderKanban, bg: "bg-sky-100 text-sky-700" },
    { label: "กำลังตรวจ", value: data.kpis.grading_in_progress, icon: Clock, bg: "bg-amber-100 text-amber-700" },
    { label: "ตรวจเสร็จแล้ว", value: data.kpis.completed_assignments, icon: CheckCircle2, bg: "bg-emerald-100 text-emerald-700" },
    { label: "ไฟล์รอตรวจ", value: data.kpis.pending_files, icon: FileSpreadsheet, bg: "bg-orange-100 text-orange-700" },
    { label: "คะแนนเฉลี่ย (%)", value: `${data.kpis.average_score_percentage}%`, icon: Award, bg: "bg-purple-100 text-purple-700" },
    { label: "บัญชี Google ที่เชื่อม", value: data.kpis.connected_google_accounts, icon: GraduationCap, bg: "bg-teal-100 text-teal-700" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">ภาพรวมระบบตรวจงาน Excel</h1>
          <p className="text-sm text-slate-500">สรุปสถิติชั้นเรียน งานที่มอบหมาย และผลการตรวจอัตโนมัติจากฐานข้อมูลจริง</p>
        </div>
        <div className="flex gap-2">
          <Link href="/google-classroom">
            <Button variant="secondary">
              <GraduationCap className="h-4 w-4" />
              ตรวจผ่าน Google Classroom
            </Button>
          </Link>
          <Link href="/grading">
            <Button>
              <FileSpreadsheet className="h-4 w-4" />
              อัปโหลดไฟล์ตรวจงาน
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.label} className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500">{k.label}</p>
                  <p className="mt-1.5 text-2xl font-bold text-violet-950">{k.value}</p>
                </div>
                <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${k.bg}`}>
                  <Icon className="h-5 w-5" />
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-base font-semibold text-violet-950">คะแนนเฉลี่ยแยกตามงาน</h2>
          {data.assignment_score_chart.length === 0 ? (
            <EmptyState title="ยังไม่มีข้อมูลคะแนน" description="สร้างงานและเริ่มตรวจไฟล์ Excel เพื่อดูกราฟคะแนนเฉลี่ย" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.assignment_score_chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EDE9FE" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="average_score" name="คะแนนเฉลี่ย" fill="#8B5CF6" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold text-violet-950">สถิติการส่งงานและการตรวจ</h2>
          {data.submission_progress_chart.length === 0 ? (
            <EmptyState title="ยังไม่มีข้อมูลการส่งงาน" description="เมื่อนักเรียนส่งไฟล์ Excel ระบบจะแสดงความคืบหน้าที่นี่" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.submission_progress_chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EDE9FE" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="submitted" name="ส่งงานแล้ว" fill="#38BDF8" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="graded" name="ตรวจแล้ว" fill="#34D399" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* Recent Lists */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-violet-950">รายการงานล่าสุด</h2>
            <Link href="/assignments" className="text-xs font-medium text-violet-600 hover:underline">
              ดูทั้งหมด
            </Link>
          </div>
          {data.recent_assignments.length === 0 ? (
            <EmptyState title="ยังไม่มีงานที่มอบหมาย" description="เริ่มต้นด้วยการสร้างงานใหม่และอัปโหลดไฟล์เฉลย" />
          ) : (
            <div className="space-y-3">
              {data.recent_assignments.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-2xl border border-violet-50 bg-violet-50/30 px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-violet-950">{a.title}</p>
                    <p className="text-xs text-slate-500">คะแนนเต็ม {a.max_score} คะแนน</p>
                  </div>
                  <Badge tone={a.status === "completed" ? "mint" : "lavender"}>{a.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-violet-950">ผลการตรวจล่าสุด</h2>
            <Link href="/reports" className="text-xs font-medium text-violet-600 hover:underline">
              ดูรายงาน
            </Link>
          </div>
          {data.recent_gradings.length === 0 ? (
            <EmptyState title="ยังไม่มีประวัติการตรวจ" description="ผลการตรวจงาน Excel ของนักเรียนจะแสดงที่นี่" />
          ) : (
            <div className="space-y-3">
              {data.recent_gradings.map((g) => (
                <div key={g.result_id} className="flex items-center justify-between rounded-2xl border border-violet-50 bg-pink-50/30 px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-violet-950">{g.student_name}</p>
                    <p className="text-xs text-slate-500">
                      {g.assignment_title} • {formatThaiDate(g.graded_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-violet-900">
                      {g.final_score}/{g.max_score}
                    </p>
                    <Badge tone={g.is_confirmed ? "mint" : "sky"}>
                      {g.is_confirmed ? "ยืนยันแล้ว" : `${g.percentage}%`}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
