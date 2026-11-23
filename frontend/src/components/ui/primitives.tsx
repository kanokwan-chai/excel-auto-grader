"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";

export type Tone3D = "green" | "yellow" | "sky" | "pink" | "lavender" | "rose" | "mint" | "orange";

export function Icon3D({
  emoji,
  tone = "green",
  size = "md",
  className,
}: {
  emoji: string;
  tone?: Tone3D;
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}) {
  const toneStyles: Record<Tone3D, string> = {
    green: "bg-gradient-to-b from-[#B9F28E] to-[#74D04A] border border-[#65BD3D]",
    yellow: "bg-gradient-to-b from-[#FFF099] to-[#F7C948] border border-[#E5B432]",
    sky: "bg-gradient-to-b from-[#BAE6FD] to-[#60B9FA] border border-[#4AA3E8]",
    pink: "bg-gradient-to-b from-[#FBCFE8] to-[#F472B6] border border-[#E15AA0]",
    lavender: "bg-gradient-to-b from-[#DDD6FE] to-[#A78BFA] border border-[#9071EB]",
    rose: "bg-gradient-to-b from-[#FECDD3] to-[#FB7185] border border-[#E85B70]",
    mint: "bg-gradient-to-b from-[#A7F3D0] to-[#34D399] border border-[#24BC84]",
    orange: "bg-gradient-to-b from-[#FED7AA] to-[#FB923C] border border-[#E57C24]",
  };
  const sizeStyles = {
    xs: "h-7 w-7 text-sm",
    sm: "h-9 w-9 text-base",
    md: "h-12 w-12 text-xl",
    lg: "h-14 w-14 text-2xl",
  };
  return (
    <span
      className={cn("clay-icon-3d shrink-0 select-none", toneStyles[tone], sizeStyles[size], className)}
      aria-hidden="true"
    >
      <span className="relative z-10 drop-shadow-[0_2px_2px_rgba(0,0,0,0.18)]">{emoji}</span>
    </span>
  );
}

export function Excel3DLogo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const dims = size === "sm" ? "h-9 w-9" : size === "lg" ? "h-16 w-16" : "h-11 w-11";
  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#52C44B] via-[#2B9E43] to-[#1A7431] text-white border border-[#1E7E34]",
        "shadow-[inset_0_2px_2px_rgba(255,255,255,0.45),0_4px_0_#145C25,0_10px_18px_-4px_rgba(26,116,49,0.45)]",
        dims
      )}
    >
      <div className="pointer-events-none absolute top-1 left-2 right-2 h-2.5 rounded-full bg-gradient-to-b from-white/50 to-transparent" />
      <svg viewBox="0 0 36 36" className="h-[72%] w-[72%] drop-shadow-[0_2px_2px_rgba(0,0,0,0.25)]" fill="none">
        <rect x="11" y="5" width="20" height="26" rx="4" fill="#A7F3A0" fillOpacity="0.95" />
        <path d="M11 12H31M11 19H31M11 26H31M21 5V31" stroke="#22863A" strokeWidth="1.5" strokeOpacity="0.45" />
        <rect x="4" y="9" width="18" height="18" rx="4.5" fill="#186A31" stroke="#8CE985" strokeWidth="1.5" />
        <path d="M9.5 14L16.5 22M16.5 14L9.5 22" stroke="#FFFFFF" strokeWidth="2.6" strokeLinecap="round" />
      </svg>
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  loading,
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger" | "mint";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}) {
  const variants = {
    primary: "clay-btn-green font-semibold",
    secondary:
      "bg-gradient-to-b from-[#EFF8FF] to-[#DBEFFE] text-[#1D4E7A] border border-[#BAE0FD] shadow-[inset_0_2px_0_rgba(255,255,255,0.85),0_3px_0_#A6D5FA] hover:brightness-[0.98] active:translate-y-[1.5px]",
    mint:
      "bg-gradient-to-b from-[#E3FAD5] to-[#C2F1A8] text-[#1C5123] border border-[#9FE27C] shadow-[inset_0_2px_0_rgba(255,255,255,0.85),0_3px_0_#88D162] hover:brightness-[0.98] active:translate-y-[1.5px]",
    outline: "clay-btn-white font-semibold",
    ghost: "text-[#2D5A36] hover:bg-[#EDF9E9]",
    danger:
      "bg-gradient-to-b from-[#FFF1F3] to-[#FFE0E5] text-[#BE123C] border border-[#FECDD3] shadow-[inset_0_2px_0_rgba(255,255,255,0.85),0_3px_0_#FDA4AF] hover:brightness-[0.98] active:translate-y-[1.5px]",
  };
  const sizes = {
    sm: "h-8 px-3.5 text-xs rounded-full gap-1.5",
    md: "h-10 px-4.5 text-sm rounded-full gap-2",
    lg: "h-11 px-6 text-sm rounded-full gap-2",
  };
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center font-medium transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("clay-card p-6", className)}>{children}</div>;
}

export function Badge({
  children,
  tone = "lavender",
  className,
}: {
  children: React.ReactNode;
  tone?: "lavender" | "mint" | "pink" | "sky" | "amber" | "rose" | "slate";
  className?: string;
}) {
  const tones = {
    lavender: "bg-gradient-to-b from-[#F5F0FF] to-[#E9DDFF] text-[#5B21B6] border-[#D8C5FF]",
    mint: "bg-gradient-to-b from-[#E4FAD6] to-[#C3F1A7] text-[#1D5B26] border-[#9CE077]",
    pink: "bg-gradient-to-b from-[#FFF0F6] to-[#FFD6E7] text-[#9D174D] border-[#FBB6CE]",
    sky: "bg-gradient-to-b from-[#ECFAFF] to-[#D1F0FF] text-[#0369A1] border-[#A5DEFF]",
    amber: "bg-gradient-to-b from-[#FFFBEB] to-[#FEF0B8] text-[#92400E] border-[#FDE078]",
    rose: "bg-gradient-to-b from-[#FFF0F2] to-[#FFD6DC] text-[#BE123C] border-[#FDA4AF]",
    slate: "bg-gradient-to-b from-[#F8FAFC] to-[#E2E8F0] text-[#334155] border-[#CBD5E1]",
  };
  return (
    <span
      className={cn(
        "clay-badge inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-2xl border-2 border-[#DCECD7] bg-white px-3.5 text-sm text-[#1B2E1F] placeholder:text-slate-400 shadow-[inset_0_2px_4px_rgba(0,0,0,0.03)] focus:border-[#68C745] focus:outline-none focus:ring-2 focus:ring-[#C5F0B0] transition",
        className
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 w-full rounded-2xl border-2 border-[#DCECD7] bg-white px-3 text-sm text-[#1B2E1F] shadow-[inset_0_2px_4px_rgba(0,0,0,0.03)] focus:border-[#68C745] focus:outline-none focus:ring-2 focus:ring-[#C5F0B0] transition",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-2xl border-2 border-[#DCECD7] bg-white p-3 text-sm text-[#1B2E1F] placeholder:text-slate-400 shadow-[inset_0_2px_4px_rgba(0,0,0,0.03)] focus:border-[#68C745] focus:outline-none focus:ring-2 focus:ring-[#C5F0B0] transition",
        className
      )}
      {...props}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-3xl bg-[#E7F5E3]", className)} />;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[#CBE5C4] bg-[#F5FCF3] px-6 py-10 text-center">
      <Icon3D emoji="📭" tone="mint" size="md" className="mb-3" />
      <h3 className="text-base font-bold text-[#1B2E1F]">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-[#5C7061]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border-2 border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 shadow-xs">
      <div className="flex items-center gap-2.5">
        <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          ลองใหม่
        </Button>
      )}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  maxWidth = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidth?: string;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#142919]/35 p-4 backdrop-blur-xs">
      <div
        className={cn(
          "clay-card w-full p-6 max-h-[90vh] overflow-y-auto",
          maxWidth
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-[#1B2E1F]">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-slate-400 hover:bg-[#EDF9E9] hover:text-[#2D6A35] transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "ยืนยัน",
  onConfirm,
  onCancel,
  loading,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title} maxWidth="max-w-md">
      <p className="text-sm text-slate-600">{description}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          ยกเลิก
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border-2 border-[#B3E89C] bg-[#EEFCE7] px-4 py-3 text-sm text-[#1E5626]">
      <CheckCircle2 className="h-4 w-4 shrink-0 text-[#3EA326]" />
      <span>{message}</span>
    </div>
  );
}
