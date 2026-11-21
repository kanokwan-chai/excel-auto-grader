"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, ExternalLink, GraduationCap, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { GoogleAccountItem, GoogleClassroomCourse } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  Select,
  Textarea,
} from "@/components/ui/primitives";

export default function CreateClassroomAssignmentPage() {
  const [accounts, setAccounts] = useState<GoogleAccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [courses, setCourses] = useState<GoogleClassroomCourse[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [maxPoints, setMaxPoints] = useState("20");
  const [dueAt, setDueAt] = useState("");
  const [state, setState] = useState<"PUBLISHED" | "DRAFT">("PUBLISHED");

  const [syncing, setSyncing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{
    title: string;
    state: string;
    alternate_link?: string | null;
    message: string;
  } | null>(null);

  const { toast } = useToast();

  useEffect(() => {
    apiRequest<{ accounts: GoogleAccountItem[] }>("/google-accounts")
      .then((res) => {
        setAccounts(res.accounts);
        if (res.accounts.length > 0) {
          const first = res.accounts[0].id;
          setSelectedAccountId(first);
          loadCourses(first, false);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "โหลดบัญชี Google ไม่สำเร็จ"));
  }, []);

  const loadCourses = async (connId: string, syncFirst: boolean) => {
    if (!connId) return;
    setSyncing(true);
    setError(null);
    try {
      if (syncFirst) {
        await apiRequest(`/classroom/accounts/${connId}/sync-courses`, { method: "POST" });
        toast("ซิงค์รายชื่อห้องเรียนล่าสุดแล้ว");
      }
      const list = await apiRequest<GoogleClassroomCourse[]>(
        `/classroom/courses?google_connection_id=${encodeURIComponent(connId)}`
      );
      setCourses(list);
      if (list.length > 0) setSelectedCourseId(list[0].id);
      else setSelectedCourseId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดห้องเรียนไม่สำเร็จ");
    } finally {
      setSyncing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCourseId) {
      toast("กรุณาเลือกห้องเรียน Google Classroom", "error");
      return;
    }
    setSubmitting(true);
    setError(null);
    setCreated(null);
    try {
      const res = await apiRequest<{
        title: string;
        state: string;
        alternate_link?: string | null;
        message: string;
      }>(`/classroom/courses/${selectedCourseId}/assignments`, {
        method: "POST",
        body: JSON.stringify({
          title,
          description: description || null,
          max_points: Number(maxPoints || 20),
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
          state,
        }),
      });
      setCreated(res);
      toast("โพสต์งานลง Google Classroom เรียบร้อยแล้ว!");
      setTitle("");
      setDescription("");
      setDueAt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "สร้างงานลง Google Classroom ไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-violet-950">สร้างและโพสต์งานลง Google Classroom</h1>
        <p className="text-sm text-slate-500">
          สร้างงานจากหน้านี้เพื่อโพสต์ขึ้น Google Classroom ทันที และรองรับการส่งคะแนนกลับเข้า Classroom อัตโนมัติ 100%
        </p>
      </div>

      <div className="flex items-start gap-2.5 rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-xs text-emerald-900">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
        <span>
          <strong>ข้อดีของการสร้างงานจากหน้านี้:</strong> งานจะถูกโพสต์ลงห้องเรียน Google Classroom ให้นักเรียนส่งไฟล์ Excel ได้ตามปกติ
          และเมื่อตรวจเสร็จ คุณครูสามารถกด <strong>&ldquo;อนุมัติและส่งคะแนนเข้า Classroom&rdquo;</strong> ให้คะแนนเด้งเข้า Classroom อัตโนมัติได้เลย
        </span>
      </div>

      {error && <ErrorBanner message={error} />}

      {created && (
        <Card className="border-emerald-200 bg-emerald-50/60 space-y-3">
          <div className="flex items-center gap-2.5 text-emerald-900">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <div>
              <p className="font-bold">สร้างงาน &ldquo;{created.title}&rdquo; สำเร็จ!</p>
              <p className="text-xs text-emerald-800">{created.message}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {created.alternate_link && (
              <a
                href={created.alternate_link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-700"
              >
                <ExternalLink className="h-3.5 w-3.5" /> เปิดดูงานบน Google Classroom
              </a>
            )}
            <Link href="/rubrics">
              <Button size="sm" variant="secondary">ไปตั้งเกณฑ์การตรวจ (Rubric)</Button>
            </Link>
          </div>
        </Card>
      )}

      {accounts.length === 0 ? (
        <EmptyState
          title="ยังไม่มีบัญชี Google ที่เชื่อมต่อ"
          description="เชื่อมต่อบัญชี Google ก่อนเพื่อโพสต์งานลง Google Classroom"
          action={
            <Link href="/google-accounts">
              <Button>ไปหน้าบัญชี Google</Button>
            </Link>
          }
        />
      ) : (
        <Card>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold text-violet-900">1. บัญชี Google</label>
                <Select
                  value={selectedAccountId}
                  onChange={(e) => {
                    setSelectedAccountId(e.target.value);
                    loadCourses(e.target.value, false);
                  }}
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.google_email}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className="text-xs font-semibold text-violet-900">2. ห้องเรียน Google Classroom</label>
                  <button
                    type="button"
                    onClick={() => loadCourses(selectedAccountId, true)}
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-600 hover:underline"
                  >
                    <RefreshCw className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`} /> ซิงค์ห้อง
                  </button>
                </div>
                <Select
                  required
                  value={selectedCourseId}
                  onChange={(e) => setSelectedCourseId(e.target.value)}
                >
                  <option value="">-- เลือกห้องเรียน --</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.section ? `(${c.section})` : ""}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-violet-900">ชื่องาน *</label>
              <Input
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="เช่น ใบงานที่ 2 การใช้สูตร SUM, AVERAGE, IF และตกแต่งตาราง"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-violet-900">รายละเอียดคำสั่ง / โจทย์ให้นักเรียน</label>
              <Textarea
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="อธิบายคำสั่งให้นักเรียนทำไฟล์ Excel และแนบส่งในงานนี้..."
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-violet-900">คะแนนเต็ม *</label>
                <Input
                  type="number"
                  step="0.5"
                  min="1"
                  required
                  value={maxPoints}
                  onChange={(e) => setMaxPoints(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-violet-900">วันกำหนดส่ง (ไม่บังคับ)</label>
                <Input
                  type="datetime-local"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-violet-900">รูปแบบการโพสต์</label>
                <Select value={state} onChange={(e) => setState(e.target.value as "PUBLISHED" | "DRAFT")}>
                  <option value="PUBLISHED">โพสต์ให้นักเรียนเห็นทันที</option>
                  <option value="DRAFT">บันทึกเป็นฉบับร่าง (Draft) ใน Classroom</option>
                </Select>
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-violet-50">
              <Badge tone="sky">
                <GraduationCap className="h-3 w-3" /> ส่งคะแนนกลับเข้า Classroom อัตโนมัติได้
              </Badge>
              <Button type="submit" size="lg" loading={submitting} disabled={!selectedCourseId}>
                <Send className="h-4 w-4" /> โพสต์งานลง Google Classroom
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
