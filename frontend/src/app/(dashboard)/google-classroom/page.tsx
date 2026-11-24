"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  GraduationCap,
  Play,
  RefreshCw,
  Search,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatThaiDate } from "@/lib/utils";
import type {
  ClassroomAssignmentItem,
  ClassroomSubmissionItem,
  GoogleAccountItem,
  GoogleClassroomCourse,
  Rubric,
} from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  Select,
} from "@/components/ui/primitives";

const STEPS = [
  "1. บัญชี Google",
  "2. เลือก Classroom",
  "3. เลือกงาน",
  "4. ตรวจไฟล์ส่ง",
  "5. เลือกเกณฑ์",
  "6. ตัวอย่างเกณฑ์",
  "7. เริ่มตรวจงาน",
  "8. ผลการตรวจ",
];

export default function GoogleClassroomWizardPage() {
  const [step, setStep] = useState(1);
  const [accounts, setAccounts] = useState<GoogleAccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");

  const [courses, setCourses] = useState<GoogleClassroomCourse[]>([]);
  const [courseSearch, setCourseSearch] = useState("");
  const [selectedCourse, setSelectedCourse] = useState<GoogleClassroomCourse | null>(null);

  const [assignments, setAssignments] = useState<ClassroomAssignmentItem[]>([]);
  const [assignSearch, setAssignSearch] = useState("");
  const [selectedAssignment, setSelectedAssignment] = useState<ClassroomAssignmentItem | null>(null);

  const [submissions, setSubmissions] = useState<ClassroomSubmissionItem[]>([]);
  const [selectedSubIds, setSelectedSubIds] = useState<string[]>([]);
  const [subSortBy, setSubSortBy] = useState<"submitted_desc" | "name">("submitted_desc");
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [selectedRubricId, setSelectedRubricId] = useState<string>("");

  const [gradingResult, setGradingResult] = useState<{
    job_id: string;
    assignment_id: string;
    graded_count: number;
    failed_count: number;
    failed_details?: { student_name: string; reason: string }[];
  } | null>(null);

  const [recentJobs, setRecentJobs] = useState<
    {
      id: string;
      assignment_title: string;
      status: string;
      total_files: number;
      processed_files: number;
      failed_files: number;
      started_at?: string | null;
      completed_at?: string | null;
    }[]
  >([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const loadRecentJobs = async () => {
    try {
      const h = await apiRequest<{
        jobs: {
          id: string;
          assignment_title: string;
          status: string;
          total_files: number;
          processed_files: number;
          failed_files: number;
          started_at?: string | null;
          completed_at?: string | null;
        }[];
      }>("/grading/history");
      setRecentJobs((h.jobs || []).slice(0, 3));
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    Promise.all([
      apiRequest<{ accounts: GoogleAccountItem[] }>("/google-accounts"),
      apiRequest<Rubric[]>("/rubrics"),
    ])
      .then(([accRes, rubRes]) => {
        setAccounts(accRes.accounts);
        if (accRes.accounts.length > 0) setSelectedAccountId(accRes.accounts[0].id);
        setRubrics(rubRes);
        if (rubRes.length > 0) setSelectedRubricId(rubRes[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "โหลดข้อมูลเริ่มต้นไม่สำเร็จ"));
    loadRecentJobs();
  }, []);

  const loadCourses = async (connId: string, syncFirst = false) => {
    setLoading(true);
    setError(null);
    try {
      if (syncFirst) {
        await apiRequest(`/classroom/accounts/${connId}/sync-courses`, { method: "POST" });
        toast("ซิงค์รายชื่อห้องเรียนจาก Google Classroom สำเร็จ");
      }
      const list = await apiRequest<GoogleClassroomCourse[]>(
        `/classroom/courses?google_connection_id=${encodeURIComponent(connId)}`
      );
      setCourses(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถดึงรายชื่อห้องเรียนได้");
    } finally {
      setLoading(false);
    }
  };

  const loadAssignments = async (course: GoogleClassroomCourse, syncFirst = false) => {
    setLoading(true);
    setError(null);
    try {
      if (syncFirst) {
        await apiRequest(`/classroom/courses/${course.id}/sync-assignments`, { method: "POST" });
        toast("ซิงค์รายการงานจาก Google Classroom สำเร็จ");
      }
      const list = await apiRequest<ClassroomAssignmentItem[]>(`/classroom/courses/${course.id}/assignments`);
      setAssignments(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถดึงรายการงานได้");
    } finally {
      setLoading(false);
    }
  };

  const loadSubmissions = async (assign: ClassroomAssignmentItem, syncFirst = false) => {
    setLoading(true);
    setError(null);
    try {
      if (syncFirst) {
        await apiRequest(`/classroom/assignments/${assign.id}/sync-submissions`, { method: "POST" });
        toast("ดึงข้อมูลการส่งงานและไฟล์แนบจาก Google Drive สำเร็จ");
      }
      const list = await apiRequest<ClassroomSubmissionItem[]>(
        `/classroom/assignments/${assign.id}/submissions`
      );
      setSubmissions(list);
      setSelectedSubIds(list.filter((s) => s.ui_status === "ready_for_grading").map((s) => s.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถดึงข้อมูลการส่งงานได้");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectDriveFile = async (subId: string, driveFileId: string) => {
    try {
      await apiRequest(`/classroom/submissions/${subId}/select-file`, {
        method: "PUT",
        body: JSON.stringify({ drive_file_id: driveFileId }),
      });
      setSubmissions((prev) =>
        prev.map((s) => (s.id === subId ? { ...s, selected_drive_file_id: driveFileId } : s))
      );
      toast("เปลี่ยนไฟล์หลักสำหรับตรวจแล้ว");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถเปลี่ยนไฟล์ได้", "error");
    }
  };

  const [batchProgress, setBatchProgress] = useState<string | null>(null);

  const handleRunWizardGrading = async () => {
    if (!selectedAccountId || !selectedCourse || !selectedAssignment || !selectedRubricId) return;
    const targetIds =
      selectedSubIds.length > 0
        ? selectedSubIds
        : submissions.filter((s) => s.ui_status === "ready_for_grading").map((s) => s.id);
    if (targetIds.length === 0) {
      toast("ไม่พบไฟล์ Excel ที่พร้อมตรวจ", "error");
      return;
    }

    setLoading(true);
    setError(null);
    setBatchProgress(null);
    const BATCH_SIZE = 3;
    let totalGraded = 0;
    let totalFailed = 0;
    let lastJobId = "";
    let lastAssignId = "";
    const allFailedDetails: { student_name: string; reason: string }[] = [];

    const gradeChunk = async (chunkIds: string[]) =>
      apiRequest<{
        job_id: string;
        assignment_id: string;
        graded_count: number;
        failed_count: number;
        failed_details?: { student_name: string; reason: string }[];
      }>("/classroom/wizard/grade", {
        method: "POST",
        body: JSON.stringify({
          google_connection_id: selectedAccountId,
          google_classroom_id: selectedCourse.id,
          classroom_assignment_id: selectedAssignment.id,
          rubric_id: selectedRubricId,
          classroom_submission_ids: chunkIds,
          job_id: lastJobId || undefined,
        }),
      });

    try {
      const totalBatches = Math.ceil(targetIds.length / BATCH_SIZE);
      for (let i = 0; i < targetIds.length; i += BATCH_SIZE) {
        const chunk = targetIds.slice(i, i + BATCH_SIZE);
        const batchNum = Math.floor(i / BATCH_SIZE) + 1;
        setBatchProgress(
          `กำลังดาวน์โหลดและตรวจชุดที่ ${batchNum}/${totalBatches} (เสร็จแล้ว ${totalGraded}/${targetIds.length} คน)...`
        );
        try {
          const res = await gradeChunk(chunk);
          totalGraded += res.graded_count;
          totalFailed += res.failed_count;
          if (res.failed_details) allFailedDetails.push(...res.failed_details);
          lastJobId = res.job_id;
          lastAssignId = res.assignment_id;
        } catch {
          // If a 3-student batch hits memory/timeout, automatically retry 1-by-1
          for (const singleId of chunk) {
            const stuObj = submissions.find((s) => s.id === singleId);
            setBatchProgress(
              `กำลังตรวจแยกทีละไฟล์: ${stuObj?.student_name || ""} (เสร็จแล้ว ${totalGraded}/${targetIds.length} คน)...`
            );
            try {
              const singleRes = await gradeChunk([singleId]);
              totalGraded += singleRes.graded_count;
              totalFailed += singleRes.failed_count;
              if (singleRes.failed_details) allFailedDetails.push(...singleRes.failed_details);
              lastJobId = singleRes.job_id;
              lastAssignId = singleRes.assignment_id;
            } catch (singleErr) {
              totalFailed += 1;
              allFailedDetails.push({
                student_name: stuObj?.student_name || singleId,
                reason: singleErr instanceof Error ? singleErr.message : "เซิร์ฟเวอร์ประมวลผลไฟล์นี้ไม่สำเร็จ",
              });
            }
          }
        }
      }
      setGradingResult({
        job_id: lastJobId,
        assignment_id: lastAssignId,
        graded_count: totalGraded,
        failed_count: totalFailed,
        failed_details: allFailedDetails,
      });
      toast(
        totalFailed > 0
          ? `ตรวจงานเสร็จสิ้น ${totalGraded} ไฟล์ (พบปัญหา ${totalFailed} ไฟล์ — ดูสาเหตุละเอียดด้านล่าง)`
          : `ตรวจงานเสร็จสิ้น ${totalGraded} ไฟล์ ✨`,
        totalFailed > 0 ? "info" : "success"
      );
      setStep(8);
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message}${totalGraded > 0 ? ` (ตรวจสำเร็จไปแล้ว ${totalGraded} คน)` : ""}`
          : "การตรวจงานขัดข้อง"
      );
    } finally {
      setLoading(false);
      setBatchProgress(null);
    }
  };

  const selectedRubric = rubrics.find((r) => r.id === selectedRubricId);
  const filteredCourses = courses.filter((c) =>
    c.name.toLowerCase().includes(courseSearch.toLowerCase())
  );
  const filteredAssignments = assignments.filter((a) =>
    a.title.toLowerCase().includes(assignSearch.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-violet-950">ตรวจงานผ่าน Google Classroom</h1>
        <p className="text-sm text-slate-500">
          ขั้นตอนแบบ Wizard 8 ขั้น รองรับหลายบัญชี Google และเลือกไฟล์ Excel จาก Google Drive จริง
        </p>
      </div>

      {/* Active / Recent Grading Jobs Banner (so accidental refresh/exit never loses track!) */}
      {recentJobs.length > 0 && (
        <Card className="p-4 bg-gradient-to-r from-violet-50/80 to-sky-50/70 border-violet-200 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-bold text-violet-950">
              สถานะงานที่กำลังตรวจ / รอบตรวจล่าสุด (หากเผลอกดออก งานยังคงตรวจต่อและดูผลได้ที่นี่)
            </p>
            <Button size="sm" variant="outline" onClick={loadRecentJobs}>
              <RefreshCw className="h-3 w-3" /> รีเฟรชสถานะ
            </Button>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            {recentJobs.map((j) => (
              <div
                key={j.id}
                className="flex items-center justify-between gap-2 rounded-2xl border border-violet-100 bg-white px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-violet-950">{j.assignment_title}</p>
                  <p className="text-[11px] text-slate-500">
                    {j.processed_files}/{j.total_files} ไฟล์ • {formatThaiDate(j.completed_at || j.started_at)}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Badge tone={j.status === "completed" ? "mint" : j.status === "processing" ? "amber" : "sky"}>
                    {j.status === "processing" ? "กำลังตรวจ..." : j.status}
                  </Badge>
                  <Link href="/reports">
                    <Button size="sm" variant="secondary">ดูผล</Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 8-Step Progress Indicator */}
      <Card className="p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
          {STEPS.map((label, i) => {
            const idx = i + 1;
            const active = idx === step;
            const done = idx < step;
            return (
              <button
                key={label}
                disabled={idx > step}
                onClick={() => idx < step && setStep(idx)}
                className={`rounded-2xl px-2.5 py-2 text-left text-xs font-medium transition ${
                  active
                    ? "bg-violet-600 text-white shadow-sm"
                    : done
                    ? "bg-emerald-100 text-emerald-900 hover:bg-emerald-200"
                    : "bg-slate-50 text-slate-400"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </Card>

      {error && <ErrorBanner message={error} />}
      {batchProgress && (
        <div className="rounded-2xl border-2 border-[#B3E89C] bg-[#EEFCE7] px-4 py-3 text-sm font-semibold text-[#1E5626] animate-pulse">
          ⏳ {batchProgress}
        </div>
      )}

      {/* STEP 1: Select Google Account */}
      {step === 1 && (
        <Card className="space-y-4">
          <h2 className="text-lg font-semibold text-violet-950">ขั้นที่ 1: เลือกบัญชี Google</h2>
          {accounts.length === 0 ? (
            <EmptyState
              title="ยังไม่มีบัญชี Google ที่เชื่อมต่อ"
              description="กรุณาไปที่หน้า บัญชี Google เพื่อเชื่อมต่อบัญชีผ่าน OAuth 2.0 ก่อน"
              action={
                <Link href="/google-accounts">
                  <Button>ไปหน้าจัดการบัญชี Google</Button>
                </Link>
              }
            />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {accounts.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => setSelectedAccountId(a.id)}
                    className={`flex items-center justify-between rounded-2xl border p-4 text-left transition ${
                      selectedAccountId === a.id
                        ? "border-violet-500 bg-violet-50"
                        : "border-violet-100 hover:bg-violet-50/40"
                    }`}
                  >
                    <div>
                      <p className="font-semibold text-violet-950">{a.display_name || a.google_email}</p>
                      <p className="text-xs text-slate-500">{a.google_email}</p>
                    </div>
                    <Badge tone={a.status === "connected" ? "mint" : "rose"}>{a.status}</Badge>
                  </button>
                ))}
              </div>
              <div className="flex justify-end">
                <Button
                  disabled={!selectedAccountId}
                  onClick={async () => {
                    await loadCourses(selectedAccountId, false);
                    setStep(2);
                  }}
                >
                  ถัดไป: เลือก Classroom <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </>
          )}
        </Card>
      )}

      {/* STEP 2: Classroom Selector Card Grid */}
      {step === 2 && (
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-violet-950">ขั้นที่ 2: เลือกห้องเรียน Google Classroom</h2>
            <div className="flex gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <Input
                  value={courseSearch}
                  onChange={(e) => setCourseSearch(e.target.value)}
                  placeholder="ค้นหาห้องเรียน..."
                  className="pl-9 w-56"
                />
              </div>
              <Button variant="secondary" loading={loading} onClick={() => loadCourses(selectedAccountId, true)}>
                <RefreshCw className="h-4 w-4" />
                ซิงค์ห้องเรียนล่าสุด
              </Button>
            </div>
          </div>

          {filteredCourses.length === 0 ? (
            <EmptyState
              title="ไม่พบห้องเรียนในบัญชีนี้"
              description="กดปุ่ม ซิงค์ห้องเรียนล่าสุด เพื่อดึงรายวิชาจาก Google Classroom API"
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredCourses.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelectedCourse(c)}
                  className={`rounded-3xl border p-5 text-left transition ${
                    selectedCourse?.id === c.id
                      ? "border-violet-500 bg-violet-50 shadow-soft"
                      : "border-violet-100 bg-white hover:border-violet-300"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-100 text-sky-700">
                      <GraduationCap className="h-5 w-5" />
                    </div>
                    <Badge tone="mint">{c.course_state}</Badge>
                  </div>
                  <h3 className="mt-3 font-semibold text-violet-950">{c.name}</h3>
                  <p className="text-xs text-slate-500">
                    {c.section || "ไม่ระบุกลุ่ม"} {c.room ? `• ห้อง ${c.room}` : ""}
                  </p>
                  <p className="mt-2 text-xs text-violet-700">บัญชี: {c.google_account_email}</p>
                </button>
              ))}
            </div>
          )}

          <div className="flex justify-between pt-2">
            <Button variant="outline" onClick={() => setStep(1)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button
              disabled={!selectedCourse}
              onClick={async () => {
                if (selectedCourse) {
                  await loadAssignments(selectedCourse, false);
                  setStep(3);
                }
              }}
            >
              ถัดไป: เลือกงาน <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 3: Assignment Selector */}
      {step === 3 && selectedCourse && (
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-violet-950">ขั้นที่ 3: เลือกงานในห้อง {selectedCourse.name}</h2>
            </div>
            <div className="flex gap-2">
              <Input
                value={assignSearch}
                onChange={(e) => setAssignSearch(e.target.value)}
                placeholder="ค้นหางาน..."
                className="w-56"
              />
              <Button variant="secondary" loading={loading} onClick={() => loadAssignments(selectedCourse, true)}>
                <RefreshCw className="h-4 w-4" /> ซิงค์งาน
              </Button>
            </div>
          </div>

          {filteredAssignments.length === 0 ? (
            <EmptyState title="ไม่พบรายการงาน" description="กดปุ่ม ซิงค์งาน เพื่อดึงรายการมอบหมายงานจริงจาก Classroom" />
          ) : (
            <div className="space-y-3">
              {filteredAssignments.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelectedAssignment(a)}
                  className={`flex w-full items-center justify-between rounded-2xl border p-4 text-left transition ${
                    selectedAssignment?.id === a.id
                      ? "border-violet-500 bg-violet-50"
                      : "border-violet-100 hover:bg-violet-50/40"
                  }`}
                >
                  <div>
                    <p className="font-semibold text-violet-950">{a.title}</p>
                    <p className="text-xs text-slate-500">กำหนดส่ง: {formatThaiDate(a.due_at)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone="mint">ส่งแล้ว {a.turned_in_count}</Badge>
                    <Badge tone="amber">ยังไม่ส่ง {a.missing_count}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="flex justify-between pt-2">
            <Button variant="outline" onClick={() => setStep(2)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button
              disabled={!selectedAssignment}
              onClick={async () => {
                if (selectedAssignment) {
                  await loadSubmissions(selectedAssignment, false);
                  setStep(4);
                }
              }}
            >
              ถัดไป: ตรวจสอบไฟล์ส่ง <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 4: Submission Manager with Submission Dates & Selective Checkboxes */}
      {step === 4 && selectedAssignment && (() => {
        const readySubs = submissions.filter((s) => s.ui_status === "ready_for_grading");
        const sortedSubs = [...submissions].sort((a, b) => {
          if (subSortBy === "submitted_desc") {
            const ta = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
            const tb = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
            if (tb !== ta) return tb - ta;
          }
          return a.student_name.localeCompare(b.student_name, "th");
        });
        const toggleSub = (id: string) => {
          setSelectedSubIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
        };

        return (
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-violet-950">
                ขั้นที่ 4: ตรวจสอบวันส่งและเลือกไฟล์ที่จะตรวจ ({selectedSubIds.length}/{readySubs.length} คน)
              </h2>
              <p className="text-xs text-slate-500">
                ติ๊กเลือกนักเรียนและเลือกไฟล์แนบ (พร้อมวัน-เวลาส่งจาก Classroom) ที่ต้องการให้ระบบวิเคราะห์คะแนน
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={subSortBy}
                onChange={(e) => setSubSortBy(e.target.value as "submitted_desc" | "name")}
                className="h-9 w-48 text-xs"
              >
                <option value="submitted_desc">เรียงตามวันที่ส่งล่าสุด</option>
                <option value="name">เรียงตามชื่อนักเรียน</option>
              </Select>
              <Button variant="secondary" loading={loading} onClick={() => loadSubmissions(selectedAssignment, true)}>
                <RefreshCw className="h-4 w-4" /> ดึงข้อมูลการส่งงานล่าสุด
              </Button>
            </div>
          </div>

          {submissions.length === 0 ? (
            <EmptyState title="ยังไม่มีข้อมูลการส่งงาน" description="กดปุ่ม ดึงข้อมูลการส่งงานล่าสุด เพื่อดึงรายชื่อ วันเวลาส่ง และไฟล์แนบจาก Classroom" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-violet-100 text-left text-xs text-slate-500">
                    <th className="py-2.5 w-10">
                      <input
                        type="checkbox"
                        checked={readySubs.length > 0 && selectedSubIds.length === readySubs.length}
                        onChange={() =>
                          setSelectedSubIds(
                            selectedSubIds.length === readySubs.length ? [] : readySubs.map((s) => s.id)
                          )
                        }
                        title="เลือกทั้งหมด"
                      />
                    </th>
                    <th className="py-2.5">นักเรียน</th>
                    <th className="py-2.5">สถานะการส่ง</th>
                    <th className="py-2.5">วันและเวลาส่งใน Classroom</th>
                    <th className="py-2.5">ไฟล์หลักที่จะใช้ตรวจ (เลือกได้)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-violet-50">
                  {sortedSubs.map((s) => {
                    const canGrade = s.ui_status === "ready_for_grading";
                    const checked = selectedSubIds.includes(s.id);
                    return (
                    <tr key={s.id} className={checked ? "bg-violet-50/40" : ""}>
                      <td className="py-3">
                        <input
                          type="checkbox"
                          disabled={!canGrade}
                          checked={checked}
                          onChange={() => toggleSub(s.id)}
                          className="h-4 w-4 rounded border-violet-300 text-violet-600 disabled:opacity-40"
                        />
                      </td>
                      <td className="py-3 font-medium text-violet-950">{s.student_name}</td>
                      <td className="py-3">
                        <div className="flex flex-wrap items-center gap-1">
                          {s.ui_status === "ready_for_grading" && <Badge tone="mint">พร้อมตรวจ ({s.state})</Badge>}
                          {s.ui_status === "no_excel_file" && <Badge tone="amber">ส่งแล้วแต่ไม่พบไฟล์ Excel</Badge>}
                          {s.ui_status === "not_submitted" && <Badge tone="rose">ยังไม่ส่งงาน ({s.state})</Badge>}
                          {s.late && <Badge tone="rose">ส่งช้า</Badge>}
                        </div>
                      </td>
                      <td className="py-3 text-xs text-slate-700 font-medium whitespace-nowrap">
                        {formatThaiDate(s.submitted_at)}
                      </td>
                      <td className="py-3">
                        {s.attachments.length > 0 ? (
                          <Select
                            value={s.selected_drive_file_id || ""}
                            onChange={(e) => handleSelectDriveFile(s.id, e.target.value)}
                            className="h-8 text-xs max-w-sm"
                          >
                            {s.attachments.map((att) => (
                              <option key={att.drive_file_id} value={att.drive_file_id}>
                                {att.title} {att.modified_time ? `(${formatThaiDate(att.modified_time)})` : ""}{" "}
                                {att.is_supported_excel ? "[Excel]" : "[ไม่รองรับ]"}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <span className="text-xs text-slate-400">ไม่มีไฟล์แนบ</span>
                        )}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex justify-between pt-2">
            <Button variant="outline" onClick={() => setStep(3)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button
              disabled={selectedSubIds.length === 0}
              onClick={async () => {
                try {
                  const freshRubrics = await apiRequest<Rubric[]>("/rubrics");
                  setRubrics(freshRubrics);
                  const matched =
                    (selectedAssignment.local_assignment_id
                      ? freshRubrics.find((r) => r.assignment_id === selectedAssignment.local_assignment_id)
                      : undefined) ||
                    freshRubrics.find((r) => r.name.trim() === selectedAssignment.title.trim());
                  if (matched) {
                    setSelectedRubricId(matched.id);
                  } else if (!freshRubrics.some((r) => r.id === selectedRubricId) && freshRubrics.length > 0) {
                    setSelectedRubricId(freshRubrics[0].id);
                  }
                } catch {
                  // keep cached rubrics if offline
                }
                setStep(5);
              }}
            >
              ถัดไป: เลือกเกณฑ์ ({selectedSubIds.length} คน) <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
        );
      })()}

      {/* STEP 5: Choose Rubric */}
      {step === 5 && (
        <Card className="space-y-4">
          <h2 className="text-lg font-semibold text-violet-950">ขั้นที่ 5: เลือกเกณฑ์การตรวจ (Rubric)</h2>
          {rubrics.length === 0 ? (
            <EmptyState
              title="ยังไม่มีเกณฑ์การตรวจ"
              description="สร้างชุดเกณฑ์การตรวจก่อนดำเนินการต่อ"
              action={
                <Link href="/rubrics">
                  <Button>ไปสร้างเกณฑ์การตรวจ</Button>
                </Link>
              }
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {rubrics.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedRubricId(r.id)}
                  className={`rounded-2xl border p-4 text-left transition ${
                    selectedRubricId === r.id ? "border-violet-500 bg-violet-50" : "border-violet-100"
                  }`}
                >
                  <p className="font-semibold text-violet-950">{r.name}</p>
                  <p className="text-xs text-slate-500">
                    {r.items.length} ข้อ • คะแนนเต็ม {r.total_points} • เวอร์ชัน {r.current_version}
                  </p>
                </button>
              ))}
            </div>
          )}
          <div className="flex justify-between pt-2">
            <Button variant="outline" onClick={() => setStep(4)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button disabled={!selectedRubricId} onClick={() => setStep(6)}>
              ถัดไป: ตัวอย่างเกณฑ์ <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 6: Preview Rubric */}
      {step === 6 && selectedRubric && (
        <Card className="space-y-4">
          <h2 className="text-lg font-semibold text-violet-950">ขั้นที่ 6: ตรวจสอบตัวอย่างเกณฑ์ก่อนเริ่มตรวจ</h2>
          <p className="text-sm text-slate-600">
            ชุดเกณฑ์: <strong>{selectedRubric.name}</strong> (รวม {selectedRubric.allocated_points}/{selectedRubric.total_points} คะแนน)
          </p>
          <div className="divide-y divide-violet-100 rounded-2xl border border-violet-100">
            {selectedRubric.items.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <p className="font-medium text-violet-950">{item.title}</p>
                  <p className="text-xs text-slate-500">
                    หมวด: {item.category} • เซลล์: {item.target_cell || "-"}
                  </p>
                </div>
                <Badge tone="lavender">{item.max_points} คะแนน</Badge>
              </div>
            ))}
          </div>
          <div className="flex justify-between pt-2">
            <Button variant="outline" onClick={() => setStep(5)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button onClick={() => setStep(7)}>
              ถัดไป: ยืนยันเริ่มตรวจงาน <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 7: Start Grading */}
      {step === 7 && (
        <Card className="space-y-5 text-center py-10">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-violet-100 text-violet-700">
            <FileSpreadsheet className="h-8 w-8" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-violet-950">พร้อมเริ่มตรวจงานอัตโนมัติ</h2>
            <p className="mt-1 text-sm text-slate-500">
              ระบบจะดาวน์โหลดไฟล์ Excel จาก Google Drive และประมวลผลสูตรผ่าน Excel Grading Engine
            </p>
          </div>
          <div className="flex justify-center gap-3">
            <Button variant="outline" onClick={() => setStep(6)}>
              <ArrowLeft className="h-4 w-4" /> ย้อนกลับ
            </Button>
            <Button size="lg" loading={loading} onClick={handleRunWizardGrading}>
              <Play className="h-4 w-4" /> เริ่มตรวจงานทั้งหมด
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 8: Done */}
      {step === 8 && gradingResult && (
        <Card className="space-y-5 text-center py-10">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-emerald-100 text-emerald-700">
            <CheckCircle2 className="h-8 w-8" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-violet-950">ตรวจงานเรียบร้อยแล้ว!</h2>
            <p className="mt-1 text-sm text-slate-600">
              ตรวจสำเร็จ {gradingResult.graded_count} ไฟล์ • พบปัญหา {gradingResult.failed_count} ไฟล์
            </p>
          </div>
          {gradingResult.failed_details && gradingResult.failed_details.length > 0 && (
            <div className="mx-auto max-w-2xl rounded-2xl border border-rose-200 bg-rose-50/70 p-4 text-left text-xs space-y-1.5">
              <p className="font-bold text-rose-900">
                รายชื่อไฟล์ที่ตรวจไม่สำเร็จ ({gradingResult.failed_details.length} คน) พร้อมสาเหตุจริง:
              </p>
              <div className="max-h-44 overflow-y-auto space-y-1">
                {gradingResult.failed_details.map((fd, idx) => (
                  <div key={idx} className="rounded-xl bg-white px-3 py-1.5 border border-rose-100 text-rose-950">
                    <strong>{fd.student_name}:</strong> {fd.reason}
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex justify-center gap-3">
            <Button variant="outline" onClick={() => setStep(1)}>
              ตรวจงานอื่นต่อ
            </Button>
            <Link
              href={
                gradingResult.assignment_id
                  ? `/reports?assignment_id=${encodeURIComponent(gradingResult.assignment_id)}`
                  : "/reports"
              }
            >
              <Button size="lg">ดูคะแนนและรายงานละเอียด</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}
