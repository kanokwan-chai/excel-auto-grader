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
      <div className="flex min-h-screen items-center justify-center bg-[#FFFDF9]">
        <Loader2 className="h-6 w-6 animate-spin text-violet-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#FFFDF9] via-[#FAF7FF] to-[#F4FBF8]">
      <Sidebar />
      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
