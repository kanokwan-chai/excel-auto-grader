"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Link2, Plus, RefreshCw, ShieldAlert, Star, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatThaiDate } from "@/lib/utils";
import type { GoogleAccountItem } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  Skeleton,
} from "@/components/ui/primitives";

export default function GoogleAccountsPage() {
  const [accounts, setAccounts] = useState<GoogleAccountItem[]>([]);
  const [oauthConfigured, setOauthConfigured] = useState(true);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<GoogleAccountItem | null>(null);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest<{ oauth_configured: boolean; accounts: GoogleAccountItem[] }>("/google-accounts");
      setAccounts(res.accounts);
      setOauthConfigured(res.oauth_configured);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถโหลดบัญชี Google ได้");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleConnectNew = async (loginHint?: string) => {
    setConnecting(true);
    try {
      const query = loginHint ? `?login_hint=${encodeURIComponent(loginHint)}` : "";
      const res = await apiRequest<{ authorization_url: string }>(`/google-accounts/connect-url${query}`);
      window.location.href = res.authorization_url;
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถสร้างลิงก์เชื่อมต่อ Google ได้", "error");
      setConnecting(false);
    }
  };

  const handleRefreshToken = async (acc: GoogleAccountItem) => {
    try {
      await apiRequest(`/google-accounts/${acc.id}/refresh`, { method: "POST" });
      toast(`ต่ออายุ Token สำหรับ ${acc.google_email} สำเร็จ`);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ต่ออายุ Token ไม่สำเร็จ", "error");
      load();
    }
  };

  const handleSetDefault = async (acc: GoogleAccountItem) => {
    try {
      await apiRequest(`/google-accounts/${acc.id}/default`, { method: "PUT" });
      toast(`ตั้ง ${acc.google_email} เป็นบัญชีหลักแล้ว`);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ตั้งค่าบัญชีหลักไม่สำเร็จ", "error");
    }
  };

  const handleDisconnect = async () => {
    if (!deleteTarget) return;
    try {
      await apiRequest(`/google-accounts/${deleteTarget.id}`, { method: "DELETE" });
      toast(`ยกเลิกการเชื่อมต่อ ${deleteTarget.google_email} แล้ว`);
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ยกเลิกการเชื่อมต่อไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-violet-950">จัดการบัญชี Google (Multi-Account)</h1>
          <p className="text-sm text-slate-500">
            ครูหนึ่งคนสามารถเชื่อมบัญชี Google ได้หลายบัญชี แยกห้องเรียนและ Token เข้ารหัสอย่างปลอดภัย
          </p>
        </div>
        <Button onClick={() => handleConnectNew()} loading={connecting}>
          <Plus className="h-4 w-4" />
          เชื่อมต่อบัญชี Google เพิ่ม
        </Button>
      </div>

      {!oauthConfigured && (
        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div>
              <p className="font-semibold">ยังไม่ได้ตั้งค่า Google OAuth 2.0 Credentials</p>
              <p className="mt-1 text-amber-800">
                กรุณากรอก <code className="rounded bg-amber-100 px-1.5 py-0.5">GOOGLE_CLIENT_ID</code> และ{" "}
                <code className="rounded bg-amber-100 px-1.5 py-0.5">GOOGLE_CLIENT_SECRET</code> ในไฟล์{" "}
                <code className="rounded bg-amber-100 px-1.5 py-0.5">.env</code> จาก Google Cloud Console
                (เปิดใช้ Google Classroom API และ Google Drive API) ระบบจะไม่สร้างข้อมูลปลอมแทนการเชื่อมต่อจริง
              </p>
            </div>
          </div>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      ) : accounts.length === 0 ? (
        <EmptyState
          title="ยังไม่มีบัญชี Google ที่เชื่อมต่อ"
          description="เชื่อมต่อบัญชี Google อย่างน้อย 1 บัญชีเพื่อดึงรายวิชา งาน และไฟล์ Excel ของนักเรียนจาก Google Classroom"
          action={
            <Button onClick={() => handleConnectNew()} loading={connecting}>
              <Link2 className="h-4 w-4" />
              เชื่อมต่อบัญชี Google แรกของคุณ
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {accounts.map((acc) => (
            <Card key={acc.id} className="flex flex-col justify-between gap-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  {acc.avatar_url ? (
                    <img src={acc.avatar_url} alt={acc.google_email} className="h-12 w-12 rounded-2xl border border-violet-200" />
                  ) : (
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-100 text-violet-700 font-bold">
                      {acc.google_email.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-violet-950">{acc.display_name || acc.google_email}</p>
                      {acc.is_default && <Badge tone="lavender">บัญชีหลัก</Badge>}
                    </div>
                    <p className="text-xs text-slate-500">{acc.google_email}</p>
                  </div>
                </div>
                <Badge tone={acc.status === "connected" ? "mint" : "rose"}>
                  {acc.status === "connected" ? (
                    <>
                      <CheckCircle2 className="h-3 w-3" /> เชื่อมต่อแล้ว
                    </>
                  ) : (
                    acc.status
                  )}
                </Badge>
              </div>

              <div className="rounded-2xl bg-violet-50/60 p-3 text-xs text-slate-600 space-y-1">
                <p>หมดอายุ Token: {formatThaiDate(acc.token_expires_at)}</p>
                <p>ซิงค์ล่าสุด: {formatThaiDate(acc.last_synced_at)}</p>
                {acc.last_error && <p className="text-rose-600 font-medium">ข้อผิดพลาด: {acc.last_error}</p>}
              </div>

              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => handleRefreshToken(acc)}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  รีเฟรช Token
                </Button>
                {acc.status !== "connected" && (
                  <Button size="sm" variant="secondary" onClick={() => handleConnectNew(acc.google_email)}>
                    เชื่อมต่อใหม่
                  </Button>
                )}
                {!acc.is_default && (
                  <Button size="sm" variant="ghost" onClick={() => handleSetDefault(acc)}>
                    <Star className="h-3.5 w-3.5" />
                    ตั้งเป็นหลัก
                  </Button>
                )}
                <Button size="sm" variant="danger" onClick={() => setDeleteTarget(acc)}>
                  <Trash2 className="h-3.5 w-3.5" />
                  ยกเลิก
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="ยกเลิกการเชื่อมต่อบัญชี Google"
        description={`ยืนยันการยกเลิกเชื่อมต่อบัญชี ${deleteTarget?.google_email}?`}
        confirmLabel="ยกเลิกการเชื่อมต่อ"
        onConfirm={handleDisconnect}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
