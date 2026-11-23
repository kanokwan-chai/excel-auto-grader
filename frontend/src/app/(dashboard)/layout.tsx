"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/hooks/use-auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { teacher, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !teacher) {
      router.replace("/login");
    }
  }, [teacher, loading, router]);

  if (loading || !teacher) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F8FCF7]">
        <Loader2 className="h-7 w-7 animate-spin text-[#56BC31]" />
      </div>
    );
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-gradient-to-br from-[#F9FDF8] via-[#FEFFF9] to-[#F2FAF5]">
      {/* Cute Pastel Floating Background Blobs (Inspired by 3D Pastel Mockup) */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden z-0">
        <div className="absolute -top-20 right-[-60px] h-80 w-80 rounded-full bg-[#C7F5A6]/40 blur-3xl" />
        <div className="absolute bottom-[-80px] left-[18%] h-72 w-72 rounded-full bg-[#B9F29B]/35 blur-3xl" />
        <div className="absolute bottom-[-60px] right-[-40px] h-80 w-80 rounded-full bg-[#FFF2A6]/45 blur-3xl" />
        <div className="absolute top-[40%] right-6 h-24 w-12 bg-dot-pastel opacity-70" />
      </div>

      <Sidebar />
      <main className="relative lg:pl-64">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
