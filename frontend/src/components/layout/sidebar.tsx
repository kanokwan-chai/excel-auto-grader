"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  ClipboardCheck,
  FileSpreadsheet,
  FolderKanban,
  GraduationCap,
  History,
  LayoutDashboard,
  Link2,
  LogOut,
  Menu,
  Scale,
  Send,
  Settings,
  Users,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";

const NAV_ITEMS = [
  { href: "/dashboard", label: "ภาพรวม", icon: LayoutDashboard, accent: "text-violet-600 bg-violet-100" },
  { href: "/google-classroom", label: "Google Classroom", icon: GraduationCap, accent: "text-sky-600 bg-sky-100" },
  { href: "/classroom-create", label: "สร้างงานลง Classroom", icon: Send, accent: "text-emerald-600 bg-emerald-100" },
  { href: "/google-accounts", label: "บัญชี Google", icon: Link2, accent: "text-pink-600 bg-pink-100" },
  { href: "/classes", label: "ชั้นเรียนของฉัน", icon: BookOpen, accent: "text-emerald-600 bg-emerald-100" },
  { href: "/students", label: "รายชื่อนักเรียน", icon: Users, accent: "text-amber-600 bg-amber-100" },
  { href: "/assignments", label: "งานที่มอบหมาย", icon: FolderKanban, accent: "text-purple-600 bg-purple-100" },
  { href: "/grading", label: "ตรวจงาน Excel", icon: ClipboardCheck, accent: "text-teal-600 bg-teal-100" },
  { href: "/rubrics", label: "เกณฑ์การตรวจ", icon: Scale, accent: "text-fuchsia-600 bg-fuchsia-100" },
  { href: "/reports", label: "คะแนนและรายงาน", icon: BarChart3, accent: "text-indigo-600 bg-indigo-100" },
  { href: "/history", label: "ประวัติการตรวจ", icon: History, accent: "text-rose-600 bg-rose-100" },
  { href: "/settings", label: "ตั้งค่าบัญชี", icon: Settings, accent: "text-slate-600 bg-slate-100" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { teacher, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);

  const validAvatar =
    teacher?.avatar_url &&
    !avatarFailed &&
    (teacher.avatar_url.startsWith("data:") || teacher.avatar_url.startsWith("http"));

  const initials = (teacher?.full_name || "CR")
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const content = (
    <div className="flex h-full flex-col justify-between bg-white/95 border-r border-violet-100">
      <div>
        <div className="flex items-center justify-between px-5 py-5 border-b border-violet-50">
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 via-purple-500 to-pink-400 text-white shadow-sm">
              <FileSpreadsheet className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-violet-950 leading-tight">Excel Auto Grader</div>
              <div className="text-[11px] font-medium text-violet-500">Multi-Teacher SaaS</div>
            </div>
          </Link>
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden rounded-xl p-1.5 text-slate-500 hover:bg-violet-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="mt-3 space-y-1 px-3 overflow-y-auto max-h-[calc(100vh-195px)]">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-medium transition-all",
                  active
                    ? "bg-gradient-to-r from-violet-100/90 to-pink-50/80 text-violet-950 shadow-xs"
                    : "text-slate-600 hover:bg-violet-50/70 hover:text-violet-900"
                )}
              >
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-xl transition",
                    active ? item.accent : "bg-slate-50 text-slate-500"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Teacher Profile & Logout */}
      <div className="border-t border-violet-100 p-4 bg-gradient-to-b from-white to-violet-50/40">
        <div className="flex items-center gap-3">
          {validAvatar ? (
            <img
              src={teacher!.avatar_url!}
              alt={teacher!.full_name}
              onError={() => setAvatarFailed(true)}
              className="h-10 w-10 rounded-2xl object-cover border border-violet-200"
            />
          ) : (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-200 to-pink-200 text-xs font-bold text-violet-900">
              {initials}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-violet-950">
              {teacher?.full_name || "ครูผู้สอน"}
            </p>
            <p className="truncate text-xs text-slate-500">{teacher?.email || ""}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-rose-200 bg-rose-50/80 py-2 text-xs font-medium text-rose-700 hover:bg-rose-100 transition"
        >
          <LogOut className="h-3.5 w-3.5" />
          ออกจากระบบ
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Header Bar */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-violet-100 bg-white/90 px-4 py-3 backdrop-blur-md lg:hidden">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-600 text-white">
            <FileSpreadsheet className="h-4 w-4" />
          </div>
          <span className="text-sm font-bold text-violet-950">Excel Auto Grader</span>
        </div>
        <button
          onClick={() => setMobileOpen(true)}
          className="rounded-xl border border-violet-200 p-2 text-violet-700"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {/* Desktop Fixed Sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:block lg:w-64 lg:z-30">
        {content}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="fixed inset-0 bg-violet-950/30 backdrop-blur-xs" onClick={() => setMobileOpen(false)} />
          <div className="relative z-10 w-72 max-w-[85vw]">{content}</div>
        </div>
      )}
    </>
  );
}
