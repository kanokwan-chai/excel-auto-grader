"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Loader2 } from "lucide-react";

export default function HomePage() {
  const { teacher, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      router.replace(teacher ? "/dashboard" : "/login");
    }
  }, [teacher, loading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FFFDF9]">
      <div className="flex items-center gap-2.5 text-violet-700">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm font-medium">กำลังโหลด Excel Auto Grader...</span>
      </div>
    </div>
  );
}
