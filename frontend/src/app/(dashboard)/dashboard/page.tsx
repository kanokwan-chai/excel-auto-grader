"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
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
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Excel3DLogo,
  Icon3D,
  Skeleton,
  type Tone3D,
} from "@/components/ui/primitives";

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
        <Skeleton className="h-12 w-72" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <Skeleton key={i} className="h-24" />
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

  const kpiCards: {
    label: string;
    value: string | number;
    emoji: string;
    tone: Tone3D;
    cardStyle: string;
    sparkle?: boolean;
  }[] = [
    {
      label: "จำนวนนักเรียน",
      value: data.kpis.total_students,
      emoji: "👥",
      tone: "green",
      cardStyle: "bg-gradient-to-br from-[#F2FCEE] to-[#E6F8DF] border-2 border-[#BFE9AE]",
      sparkle: true,
    },
    {
      label: "จำนวนชั้นเรียน",
      value: data.kpis.total_classes,
      emoji: "📒",
      tone: "yellow",
      cardStyle: "bg-gradient-to-br from-[#FFFDF0] to-[#FFF6D6] border-2 border-[#FDE293]",
      sparkle: true,
    },
    {
      label: "งานที่มอบหมาย",
      value: data.kpis.total_assignments,
      emoji: "📁",
      tone: "sky",
      cardStyle: "bg-gradient-to-br from-[#F0F9FF] to-[#E2F3FF] border-2 border-[#BAE3FD]",
      sparkle: true,
    },
    {
      label: "กำลังตรวจ",
      value: data.kpis.grading_in_progress,
      emoji: "🔍",
      tone: "pink",
      cardStyle: "bg-gradient-to-br from-[#FFF2F6] to-[#FFE4EE] border-2 border-[#FBCFE0]",
    },
    {
      label: "ตรวจเสร็จแล้ว",
      value: data.kpis.completed_assignments,
      emoji: "✅",
      tone: "lavender",
      cardStyle: "bg-gradient-to-br from-[#F6F2FF] to-[#ECE4FF] border-2 border-[#D9CCFE]",
      sparkle: true,
    },
    {
      label: "ไฟล์รอตรวจ",
      value: data.kpis.pending_files,
      emoji: "📄",
      tone: "rose",
      cardStyle: "bg-gradient-to-br from-[#FFF2F4] to-[#FFE3E8] border-2 border-[#FECDD6]",
    },
    {
      label: "คะแนนเฉลี่ยรวม",
      value: `${data.kpis.average_score_percentage}%`,
      emoji: "📊",
      tone: "mint",
      cardStyle: "bg-gradient-to-br from-[#EFFCF2] to-[#DCF8E4] border-2 border-[#AEEBC1]",
      sparkle: true,
    },
    {
      label: "บัญชี Google ที่เชื่อม",
      value: data.kpis.connected_google_accounts,
      emoji: "🔗",
      tone: "sky",
      cardStyle: "bg-gradient-to-br from-[#F1FAFF] to-[#E1F3FE] border-2 border-[#B8E2FC]",
      sparkle: true,
    },
  ];

  const statusThai = (s: string) => {
    if (s === "completed") return "✓ ตรวจเสร็จแล้ว";
    if (s === "grading") return "⏳ กำลังตรวจ";
    if (s === "published") return "📢 เผยแพร่แล้ว";
    return s;
  };

  return (
    <div className="space-y-6">
      {/* Cute 3D Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="animate-float-slow">
            <Icon3D emoji="🧮" tone="yellow" size="lg" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-[26px] font-extrabold text-[#172B1C] tracking-tight flex items-center gap-1.5">
              ภาพรวมระบบตรวจงาน Excel <span className="text-xl">✨</span>
            </h1>
            <p className="text-sm font-medium text-[#5C7061]">
              สรุปการส่งงาน การตรวจคะแนน และผลการเรียนของนักเรียนแบบเรียลไทม์
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link href="/google-classroom">
            <Button variant="outline" size="lg">
              <span className="text-base">🧑‍🏫</span>
              ตรวจผ่าน Google Classroom
            </Button>
          </Link>
          <Link href="/grading">
            <Button size="lg">
              <span className="text-base">📤</span>
              อัปโหลดไฟล์ตรวจงาน
            </Button>
          </Link>
        </div>
      </div>

      {/* 8 Cute 3D Pastel KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((k) => (
          <div
            key={k.label}
            className={`clay-kpi flex items-center gap-3.5 px-4 py-3.5 ${k.cardStyle}`}
          >
            <Icon3D emoji={k.emoji} tone={k.tone} size="md" />
            <div className="min-w-0">
              <p className="text-xs font-bold text-[#445B49] truncate">{k.label}</p>
              <p className="mt-0.5 text-2xl font-extrabold text-[#142618] flex items-center gap-1">
                {k.value}
                {k.sparkle && <span className="text-sm opacity-80">✨</span>}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* 2 Pastel Charts with 3D Section Pills */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="inline-flex items-center gap-2.5 rounded-full bg-gradient-to-r from-[#EFE9FF] to-[#F7F3FF] border border-[#DDD1FE] pl-1.5 pr-4 py-1 shadow-xs">
              <Icon3D emoji="📊" tone="yellow" size="xs" />
              <h2 className="text-sm font-extrabold text-[#2D1B69]">คะแนนเฉลี่ยแยกตามงาน</h2>
            </div>
          </div>
          {data.assignment_score_chart.length === 0 ? (
            <EmptyState
              title="ยังไม่มีข้อมูลคะแนน"
              description="สร้างงานและเริ่มตรวจไฟล์ Excel เพื่อดูกราฟคะแนนเฉลี่ย"
            />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.assignment_score_chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E8F3E5" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#445B49" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#445B49" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "16px",
                      border: "1.5px solid #CBE5C4",
                      boxShadow: "0 10px 25px -8px rgba(34,84,45,0.18)",
                    }}
                  />
                  <Bar
                    dataKey="average_score"
                    name="คะแนนเฉลี่ย"
                    fill="#6DC643"
                    radius={[12, 12, 4, 4]}
                    maxBarSize={68}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="inline-flex items-center gap-2.5 rounded-full bg-gradient-to-r from-[#E4FAD5] to-[#F2FDEA] border border-[#BEEB9F] pl-1.5 pr-4 py-1 shadow-xs">
              <Icon3D emoji="⏱️" tone="yellow" size="xs" />
              <h2 className="text-sm font-extrabold text-[#1B4922]">สถิติการส่งงานและการตรวจ</h2>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-bold text-[#445B49]">
              <span className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-xs bg-[#489E8E]" /> ส่งงาน
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-xs bg-[#A3DE6B]" /> ตรวจแล้ว
              </span>
            </div>
          </div>
          {data.submission_progress_chart.length === 0 ? (
            <EmptyState
              title="ยังไม่มีข้อมูลการส่งงาน"
              description="เมื่อนักเรียนส่งไฟล์ Excel ระบบจะแสดงความคืบหน้าที่นี่"
            />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.submission_progress_chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E8F3E5" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#445B49" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#445B49" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "16px",
                      border: "1.5px solid #CBE5C4",
                      boxShadow: "0 10px 25px -8px rgba(34,84,45,0.18)",
                    }}
                  />
                  <Bar dataKey="submitted" name="ส่งงานแล้ว" fill="#489E8E" radius={[10, 10, 4, 4]} maxBarSize={42} />
                  <Bar dataKey="graded" name="ตรวจแล้ว" fill="#A3DE6B" radius={[10, 10, 4, 4]} maxBarSize={42} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* 2 Bottom Lists with Cute 3D Badges */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5 border-2 border-[#CBE7FD]">
          <div className="mb-4 flex items-center justify-between">
            <div className="inline-flex items-center gap-2.5 rounded-full bg-gradient-to-r from-[#E3F4FF] to-[#F2FAFF] border border-[#B8E2FC] pl-1.5 pr-4 py-1 shadow-xs">
              <Icon3D emoji="⭐" tone="yellow" size="xs" />
              <h2 className="text-sm font-extrabold text-[#164E78]">รายการงานล่าสุด</h2>
            </div>
            <Link
              href="/assignments"
              className="text-xs font-bold text-[#2574A9] hover:underline flex items-center gap-1"
            >
              ดูทั้งหมด →
            </Link>
          </div>
          {data.recent_assignments.length === 0 ? (
            <EmptyState
              title="ยังไม่มีงานที่มอบหมาย"
              description="เริ่มต้นด้วยการสร้างงานใหม่หรือเชื่อมจาก Google Classroom"
            />
          ) : (
            <div className="space-y-3">
              {data.recent_assignments.map((a) => (
                <Link
                  key={a.id}
                  href="/assignments"
                  className="flex items-center justify-between gap-3 rounded-2xl border border-[#E5F2E1] bg-gradient-to-r from-[#FAFDF9] to-white px-3.5 py-3 hover:border-[#9CE077] hover:shadow-xs transition"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Excel3DLogo size="sm" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-[#172B1C]">{a.title}</p>
                      <p className="text-xs text-[#5C7061]">คะแนนเต็ม {a.max_score} คะแนน</p>
                    </div>
                  </div>
                  <Badge tone={a.status === "completed" ? "mint" : "sky"}>
                    {statusThai(a.status)}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5 border-2 border-[#FBD3DF]">
          <div className="mb-4 flex items-center justify-between">
            <div className="inline-flex items-center gap-2.5 rounded-full bg-gradient-to-r from-[#FFE8F0] to-[#FFF4F8] border border-[#FBC7D9] pl-1.5 pr-4 py-1 shadow-xs">
              <Icon3D emoji="🏆" tone="yellow" size="xs" />
              <h2 className="text-sm font-extrabold text-[#8B1A4B]">ผลการตรวจล่าสุด</h2>
            </div>
            <Link
              href="/reports"
              className="text-xs font-bold text-[#A6245A] hover:underline flex items-center gap-1"
            >
              ดูรายงาน →
            </Link>
          </div>
          {data.recent_gradings.length === 0 ? (
            <EmptyState
              title="ยังไม่มีประวัติการตรวจ"
              description="ผลการตรวจงาน Excel ของนักเรียนจะแสดงที่นี่"
            />
          ) : (
            <div className="space-y-3">
              {data.recent_gradings.map((g) => {
                const isPass = g.percentage >= 50;
                return (
                  <Link
                    key={g.result_id}
                    href="/reports"
                    className="flex items-center justify-between gap-3 rounded-2xl border border-[#FBE8EE] bg-gradient-to-r from-[#FFF9FB] to-white px-3.5 py-3 hover:border-[#F8B4C9] hover:shadow-xs transition"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Icon3D emoji={isPass ? "🧑‍🎓" : "📝"} tone="yellow" size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold text-[#172B1C]">{g.student_name}</p>
                        <p className="truncate text-xs text-[#5C7061]">
                          {g.assignment_title} • {formatThaiDate(g.graded_at)}
                        </p>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-extrabold text-[#172B1C]">
                        {g.final_score}
                        <span className="text-xs font-semibold text-slate-400">/{g.max_score}</span>
                      </p>
                      <Badge tone={isPass ? "mint" : "rose"} className="mt-0.5">
                        {isPass ? "✓ ผ่านเกณฑ์" : "✕ ไม่ผ่านเกณฑ์"}
                      </Badge>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
