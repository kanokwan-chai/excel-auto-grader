"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, LogOut, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import { Excel3DLogo, Icon3D, type Tone3D } from "@/components/ui/primitives";

const NAV_ITEMS: { href: string; label: string; emoji: string; tone: Tone3D }[] = [
  { href: "/dashboard", label: "ภาพรวม", emoji: "🏠", tone: "green" },
  { href: "/google-classroom", label: "Google Classroom", emoji: "🎓", tone: "sky" },
  { href: "/classroom-create", label: "สร้างงานลง Classroom", emoji: "🚀", tone: "mint" },
  { href: "/google-accounts", label: "บัญชี Google", emoji: "🔗", tone: "pink" },
  { href: "/classes", label: "ชั้นเรียนของฉัน", emoji: "📚", tone: "yellow" },
  { href: "/students", label: "รายชื่อนักเรียน", emoji: "👥", tone: "orange" },
  { href: "/assignments", label: "งานที่มอบหมาย", emoji: "📁", tone: "sky" },
  { href: "/grading", label: "ตรวจงาน Excel", emoji: "✅", tone: "green" },
  { href: "/rubrics", label: "เกณฑ์การตรวจ", emoji: "🎯", tone: "lavender" },
  { href: "/reports", label: "คะแนนและรายงาน", emoji: "📊", tone: "mint" },
  { href: "/history", label: "ประวัติการตรวจ", emoji: "🕒", tone: "rose" },
  { href: "/settings", label: "ตั้งค่าบัญชี", emoji: "⚙️", tone: "lavender" },
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
    <div className="flex h-full flex-col justify-between bg-white/95 border-r-2 border-[#E5F2E1] shadow-[4px_0_24px_-12px_rgba(34,84,45,0.08)]">
      <div>
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/dashboard" className="flex items-center gap-3 group">
            <div className="transition-transform duration-200 group-hover:scale-105 group-hover:-rotate-3">
              <Excel3DLogo size="md" />
            </div>
            <div>
              <div className="text-sm font-extrabold text-[#172B1C] leading-tight tracking-tight">
                Excel Auto Grader
              </div>
              <div className="text-[11px] font-semibold text-[#5E8266]">Multi-Teacher SaaS ✨</div>
            </div>
          </Link>
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden rounded-full p-1.5 text-slate-500 hover:bg-[#EDF9E9]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="mt-1 space-y-1.5 px-3 overflow-y-auto max-h-[calc(100vh-215px)] pb-3">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "group flex items-center gap-3 rounded-full px-3 py-2 text-sm font-semibold transition-all duration-150",
                  active
                    ? "clay-pill-active"
                    : "text-[#394D3E] hover:bg-[#F2FAF0] hover:text-[#172B1C] hover:translate-x-0.5"
                )}
              >
                {active ? (
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/85 text-sm shadow-xs">
                    {item.emoji}
                  </span>
                ) : (
                  <Icon3D
                    emoji={item.emoji}
                    tone={item.tone}
                    size="xs"
                    className="opacity-90 group-hover:scale-110 transition-transform"
                  />
                )}
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Teacher Profile Card & Logout */}
      <div className="p-3.5 border-t border-[#EAF5E7] bg-gradient-to-b from-white to-[#F6FCF4]">
        <Link
          href="/settings"
          onClick={() => setMobileOpen(false)}
          className="flex items-center gap-2.5 rounded-full border-2 border-[#DCEFD6] bg-white px-2.5 py-2 shadow-[inset_0_2px_0_rgba(255,255,255,0.9),0_4px_10px_-4px_rgba(34,84,45,0.12)] hover:border-[#9CE077] transition"
        >
          {validAvatar ? (
            <img
              src={teacher!.avatar_url!}
              alt={teacher!.full_name}
              onError={() => setAvatarFailed(true)}
              className="h-9 w-9 rounded-full object-cover border-2 border-[#BCE8A8]"
            />
          ) : (
            <div className="clay-icon-3d h-9 w-9 shrink-0 bg-gradient-to-b from-[#B9F28E] to-[#68C745] text-xs font-extrabold text-[#16361C]">
              <span className="relative z-10">{initials}</span>
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-bold text-[#172B1C]">
              {teacher?.full_name || "ครูผู้สอน"}
            </p>
            <p className="truncate text-[11px] text-[#5C7061]">{teacher?.email || ""}</p>
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-[#86A68D]" />
        </Link>
        <button
          onClick={logout}
          className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-full border border-rose-200 bg-gradient-to-b from-[#FFF2F4] to-[#FFE1E6] py-1.5 text-xs font-semibold text-rose-700 shadow-[inset_0_1.5px_0_rgba(255,255,255,0.8),0_2px_0_#FECDD3] hover:brightness-[0.98] active:translate-y-[1px] transition cursor-pointer"
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
      <div className="sticky top-0 z-30 flex items-center justify-between border-b-2 border-[#E5F2E1] bg-white/95 px-4 py-3 backdrop-blur-md lg:hidden">
        <div className="flex items-center gap-2.5">
          <Excel3DLogo size="sm" />
          <span className="text-sm font-extrabold text-[#172B1C]">Excel Auto Grader</span>
        </div>
        <button
          onClick={() => setMobileOpen(true)}
          className="rounded-full border-2 border-[#D4E8CE] bg-white p-2 text-[#2B6E36]"
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
          <div className="fixed inset-0 bg-[#142919]/30 backdrop-blur-xs" onClick={() => setMobileOpen(false)} />
          <div className="relative z-10 w-72 max-w-[85vw]">{content}</div>
        </div>
      )}
    </>
  );
}
