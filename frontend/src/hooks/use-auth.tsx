"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiRequest, getSessionToken, setSessionToken, wakeUpBackend } from "@/lib/api";
import type { TeacherProfile } from "@/types";

interface AuthContextValue {
  teacher: TeacherProfile | null;
  loading: boolean;
  refreshProfile: () => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [teacher, setTeacher] = useState<TeacherProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshProfile = useCallback(async () => {
    const token = getSessionToken();
    if (!token) {
      setTeacher(null);
      setLoading(false);
      return;
    }
    try {
      const me = await apiRequest<TeacherProfile>("/auth/me");
      setTeacher(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSessionToken(null);
      }
      setTeacher(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    wakeUpBackend();
    refreshProfile();
  }, [refreshProfile]);

  const loginWithToken = async (token: string) => {
    setSessionToken(token);
    await refreshProfile();
  };

  const logout = () => {
    setSessionToken(null);
    setTeacher(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ teacher, loading, refreshProfile, loginWithToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
