"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ClipboardCopy,
  ClipboardPaste,
  Copy,
  Eye,
  FileSpreadsheet,
  FlaskConical,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { AssignmentItem, Rubric, RubricItem } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Icon3D,
  Input,
  Modal,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";

const CATEGORY_LABELS: Record<string, string> = {
  formula: "🧮 ตรวจสูตร Excel",
  structure: "🔍 ตรวจตัวกรอง (Filter) / แท็บ",
  value: "🔢 ตรวจคำตอบ/ผลลัพธ์",
  chart: "📊 ตรวจกราฟ/แผนภูมิ",
  style: "🎨 ตรวจการตกแต่งตาราง",
  completeness: "📋 ตรวจข้อมูลครบ/เรียงลำดับ",
  position: "📍 ตรวจตำแหน่งเซลล์",
};

const VALID_CATEGORIES = new Set(Object.keys(CATEGORY_LABELS));

const FORMULA_PRESETS = [
  "SUM",
  "AVERAGE",
  "MAX",
  "MIN",
  "COUNT",
  "COUNTA",
  "COUNTBLANK",
  "IF",
  "IFS",
  "AND",
  "OR",
  "SUMIF",
  "SUMIFS",
  "COUNTIF",
  "COUNTIFS",
  "AVERAGEIF",
  "VLOOKUP",
  "HLOOKUP",
  "XLOOKUP",
  "FILTER",
  "SORT",
  "SORTBY",
  "UNIQUE",
  "SUBTOTAL",
  "AGGREGATE",
  "INDEX",
  "MATCH",
  "RANK",
  "ROUND",
  "LEFT",
  "RIGHT",
  "MID",
  "CONCAT",
  "TEXT",
  "TODAY",
  "DATEDIF",
];

interface DryRunResult {
  auto_score: number;
  max_score: number;
  percentage: number;
  all_passed: boolean;
  details: {
    item_title: string;
    earned_points: number;
    max_points: number;
    passed: boolean;
    reason: string;
    suggestion?: string | null;
  }[];
}

function makeEmptyItem(idx: number): RubricItem {
  return {
    order_index: idx,
    title: "",
    category: "formula",
    sheet_name: "",
    target_cell: "",
    rule_config: {},
    max_points: 2,
    min_points: 0,
    allow_partial_credit: true,
    weight_importance: "normal",
    zero_on_error: false,
    is_enabled: true,
  };
}

function parsePastedRubricText(raw: string): { items: RubricItem[]; totalPoints?: number; name?: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { items: [] };

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      const arr = Array.isArray(parsed) ? parsed : parsed.items;
      if (Array.isArray(arr)) {
        const mapped: RubricItem[] = arr.map((it: Partial<RubricItem>, idx: number) => ({
          order_index: idx,
          title: String(it.title || `เกณฑ์ข้อที่ ${idx + 1}`),
          category: VALID_CATEGORIES.has(String(it.category)) ? String(it.category) : "formula",
          sheet_name: it.sheet_name || "",
          target_cell: it.target_cell || "",
          rule_config: it.rule_config || {},
          max_points: Number(it.max_points ?? 2),
          min_points: Number(it.min_points ?? 0),
          allow_partial_credit: it.allow_partial_credit ?? true,
          weight_importance: it.weight_importance || "normal",
          zero_on_error: Boolean(it.zero_on_error),
          is_enabled: it.is_enabled ?? true,
        }));
        return {
          items: mapped,
          totalPoints: !Array.isArray(parsed) && parsed.total_points ? Number(parsed.total_points) : undefined,
          name: !Array.isArray(parsed) && parsed.name ? String(parsed.name) : undefined,
        };
      }
    } catch {
      // Fallback to line-by-line parser
    }
  }

  const lines = trimmed
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#") && !l.startsWith("---"));

  const items: RubricItem[] = [];
  for (const line of lines) {
    const parts = line.includes("\t")
      ? line.split("\t").map((p) => p.trim())
      : line.split("|").map((p) => p.trim()).filter((p) => p !== "");

    if (parts.length < 2) continue;
    if (parts[0].includes("รายการ") && (parts[parts.length - 1].includes("คะแนน") || parts[1].includes("คะแนน"))) {
      continue;
    }

    const lastNum = parseFloat(parts[parts.length - 1]);
    const points = Number.isFinite(lastNum) ? lastNum : 2;
    const title = parts[0].replace(/^[-•*\d.)\s]+/, "").trim() || parts[0];

    let category = "formula";
    let sheet_name = "";
    let target_cell = "";
    let rule_config: Record<string, unknown> = {};

    if (parts.length >= 6) {
      category = VALID_CATEGORIES.has(parts[1].toLowerCase()) ? parts[1].toLowerCase() : "formula";
      sheet_name = parts[2] || "";
      target_cell = parts[3] || "";
      const expected = parts[4] || "";
      if (category === "formula") rule_config = { expected_formula: expected };
      else if (category === "style") rule_config = { number_format: expected };
      else if (category === "chart") rule_config = { chart_type: expected };
    } else {
      const lower = title.toLowerCase();
      if (lower.includes("กรอง") || lower.includes("filter")) {
        category = "structure";
        rule_config = { require_autofilter: true };
      } else if (lower.includes("กราฟ") || lower.includes("แผนภูมิ") || lower.includes("chart")) {
        category = "chart";
      } else if (lower.includes("รูปแบบ") || lower.includes("ตกแต่ง") || lower.includes("สี") || lower.includes("เส้นขอบ")) {
        category = "style";
        rule_config = { match_reference_layout_ignore_color: true, bold: true, has_border: true, has_fill_color: true };
      }
    }

    items.push({
      order_index: items.length,
      title,
      category,
      sheet_name,
      target_cell,
      rule_config,
      max_points: points,
      min_points: 0,
      allow_partial_credit: true,
      weight_importance: "normal",
      zero_on_error: false,
      is_enabled: true,
    });
  }

  return { items };
}

export default function RubricsPage() {
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [openBuilder, setOpenBuilder] = useState(false);
  const [editingRubricId, setEditingRubricId] = useState<string | null>(null);
  const [previewRubric, setPreviewRubric] = useState<Rubric | null>(null);
  const [builderTab, setBuilderTab] = useState<"answer_key" | "quick_pick" | "text_prompt">("answer_key");

  const [name, setName] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [totalPoints, setTotalPoints] = useState("20");
  const [items, setItems] = useState<RubricItem[]>([makeEmptyItem(0)]);
  const [saving, setSaving] = useState(false);

  const [showPasteBox, setShowPasteBox] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [freeformText, setFreeformText] = useState("");
  const [expanding, setExpanding] = useState(false);
  const [customFormulaInput, setCustomFormulaInput] = useState("");
  const [extraFormulas, setExtraFormulas] = useState<string[]>([]);

  const [sampleUploading, setSampleUploading] = useState(false);
  const [sampleInfo, setSampleInfo] = useState<{
    filename: string;
    storage_path: string;
    sheet_names: string[];
    columns_by_sheet: Record<string, string[]>;
    formula_count: number;
    sheet_metadata: Record<string, unknown>;
    suggested_items: RubricItem[];
  } | null>(null);

  const [testingSample, setTestingSample] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);

  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, a] = await Promise.all([
        apiRequest<Rubric[]>("/rubrics"),
        apiRequest<AssignmentItem[]>("/assignments"),
      ]);
      setRubrics(r);
      setAssignments(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดเกณฑ์การตรวจไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const allocated = Math.round(
    items.filter((i) => i.is_enabled).reduce((sum, i) => sum + Number(i.max_points || 0), 0) * 100
  ) / 100;
  const exceeds = allocated > Number(totalPoints || 0) + 0.01;

  const updateItem = (index: number, patch: Partial<RubricItem>) => {
    setDryRunResult(null);
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  };

  const distributePointsToItems = (targetItems: RubricItem[], total: number): RubricItem[] => {
    const enabledIndices = targetItems.map((it, idx) => (it.is_enabled ? idx : -1)).filter((i) => i >= 0);
    if (total <= 0 || enabledIndices.length === 0) return targetItems;
    const base = Math.floor((total / enabledIndices.length) * 100) / 100;
    let running = 0;
    return targetItems.map((it, idx) => {
      if (!it.is_enabled) return it;
      const pos = enabledIndices.indexOf(idx);
      const pts = pos === enabledIndices.length - 1 ? Math.round((total - running) * 100) / 100 : base;
      running = Math.round((running + pts) * 100) / 100;
      return { ...it, max_points: pts };
    });
  };

  const handleAutoDistributePoints = () => {
    const total = Number(totalPoints || 0);
    if (total <= 0 || items.length === 0) {
      toast("กรุณากรอกคะแนนเต็มและมีข้อเกณฑ์อย่างน้อย 1 ข้อ", "error");
      return;
    }
    setItems((prev) => distributePointsToItems(prev, total));
    setDryRunResult(null);
    toast(`เฉลี่ยคะแนนรวม ${total} คะแนน ให้ครบทุกข้อเรียบร้อย ✨`);
  };

  const toggleFormulaPreset = (funcName: string) => {
    const clean = funcName.trim().toUpperCase();
    if (!clean) return;
    setDryRunResult(null);
    const existsIdx = items.findIndex(
      (it) =>
        it.category === "formula" &&
        (Array.isArray(it.rule_config.required_functions)
          ? (it.rule_config.required_functions as string[]).includes(clean)
          : it.title.toUpperCase().includes(clean))
    );
    if (existsIdx >= 0) {
      setItems((prev) => prev.filter((_, idx) => idx !== existsIdx));
    } else {
      const newItem: RubricItem = {
        order_index: items.length,
        title: `ตรวจสูตร ${clean}`,
        description: `ตรวจสอบการใช้ฟังก์ชัน ${clean}`,
        category: "formula",
        sheet_name: sampleInfo?.sheet_names[0] || "",
        target_cell: "",
        rule_config: { required_functions: [clean] },
        max_points: 2,
        min_points: 0,
        allow_partial_credit: true,
        weight_importance: "high",
        zero_on_error: false,
        is_enabled: true,
      };
      setItems((prev) => {
        const cleaned = prev.length === 1 && !prev[0].title.trim() ? [] : prev;
        return [...cleaned, newItem];
      });
    }
  };

  const handleAddCustomFormula = () => {
    const clean = customFormulaInput.trim().toUpperCase().replace(/^=/, "").replace(/\(.*$/, "");
    if (!clean) return;
    if (!FORMULA_PRESETS.includes(clean) && !extraFormulas.includes(clean)) {
      setExtraFormulas((prev) => [...prev, clean]);
    }
    toggleFormulaPreset(clean);
    setCustomFormulaInput("");
  };

  const handleSampleFileUpload = async (file: File | null) => {
    if (!file) return;
    setSampleUploading(true);
    setDryRunResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (assignmentId) fd.append("assignment_id", assignmentId);
      const res = await apiRequest<{
        filename: string;
        storage_path: string;
        columns_by_sheet?: Record<string, string[]>;
        sheet_metadata: { sheet_names: string[]; sheets: { formula_count: number }[] };
        suggested_items: RubricItem[];
      }>("/rubrics/inspect-sample", { method: "POST", body: fd });

      const formulaTotal = (res.sheet_metadata.sheets || []).reduce((s, sh) => s + (sh.formula_count || 0), 0);
      const total = Number(totalPoints || 20);
      const balancedSuggested = distributePointsToItems(res.suggested_items || [], total);

      setSampleInfo({
        filename: res.filename,
        storage_path: res.storage_path,
        sheet_names: res.sheet_metadata.sheet_names || [],
        columns_by_sheet: res.columns_by_sheet || {},
        formula_count: formulaTotal,
        sheet_metadata: res.sheet_metadata as unknown as Record<string, unknown>,
        suggested_items: balancedSuggested,
      });

      // Auto-populate name if empty, and auto-apply suggested ground-truth items on fresh rubric!
      if (!name.trim()) {
        setName(`เกณฑ์ตรวจ ${res.filename.replace(/\.xlsx?$/i, "")}`);
      }
      if (!editingRubricId && balancedSuggested.length > 0) {
        setItems(balancedSuggested);
        toast(`ดึงเกณฑ์เฉลยเป๊ะ 100% จาก "${res.filename}" สำเร็จ (${balancedSuggested.length} ข้อ)! กดปุ่มทดสอบตรวจด้านล่างได้เลย ✨`);
      } else {
        toast(`อ่านไฟล์เฉลย "${res.filename}" สำเร็จ (${res.sheet_metadata.sheet_names.length} แท็บ)`);
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถอ่านไฟล์เฉลยได้", "error");
    } finally {
      setSampleUploading(false);
    }
  };

  const handleUseSuggestedItems = () => {
    if (!sampleInfo || sampleInfo.suggested_items.length === 0) return;
    const balanced = distributePointsToItems(sampleInfo.suggested_items, Number(totalPoints || 20));
    setItems(balanced);
    setDryRunResult(null);
    toast(`ดึงเกณฑ์เฉลยเป๊ะ 100% ทั้ง ${balanced.length} ข้อเรียบร้อยแล้ว ✨`);
  };

  const handleTestAgainstSample = async () => {
    if (!sampleInfo?.storage_path) {
      toast("กรุณาแนบไฟล์เฉลย Excel ในขั้นที่ 1 ก่อนกดทดสอบครับ", "error");
      return;
    }
    setTestingSample(true);
    try {
      const res = await apiRequest<DryRunResult>("/rubrics/test-sample", {
        method: "POST",
        body: JSON.stringify({
          storage_path: sampleInfo.storage_path,
          total_points: Number(totalPoints || 20),
          items,
        }),
      });
      setDryRunResult(res);
      toast(
        res.all_passed
          ? `เป๊ะ 100%! ทดสอบกับไฟล์เฉลยได้ ${res.auto_score}/${res.max_score} คะแนนเต็มครบทุกข้อ 🎉`
          : `ทดสอบแล้วได้ ${res.auto_score}/${res.max_score} คะแนน — ดูจุดที่ต้องปรับด้านล่างได้เลย`,
        res.all_passed ? "success" : "info"
      );
    } catch (err) {
      toast(err instanceof Error ? err.message : "ทดสอบกับไฟล์เฉลยไม่สำเร็จ", "error");
    } finally {
      setTestingSample(false);
    }
  };

  const handleExpandFreeform = async () => {
    if (!freeformText.trim()) {
      toast("กรุณาพิมพ์โจทย์หรือเงื่อนไขที่ต้องการตรวจก่อนครับ", "error");
      return;
    }
    setExpanding(true);
    setDryRunResult(null);
    try {
      const res = await apiRequest<{
        total_points: number;
        items: RubricItem[];
        summary_th: string;
      }>("/rubrics/expand-text", {
        method: "POST",
        body: JSON.stringify({
          prompt_text: freeformText,
          total_points: Number(totalPoints || 20),
          sample_metadata: sampleInfo?.sheet_metadata || null,
        }),
      });
      setItems(res.items);
      setTotalPoints(String(res.total_points));
      toast(res.summary_th);
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถแปลงโจทย์เป็นเกณฑ์ได้", "error");
    } finally {
      setExpanding(false);
    }
  };

  const handleApplyPaste = () => {
    const parsed = parsePastedRubricText(pasteText);
    if (parsed.items.length === 0) {
      toast("ไม่พบรายการเกณฑ์ในข้อความที่วาง", "error");
      return;
    }
    setItems(parsed.items);
    const sumPts = parsed.items.reduce((s, it) => s + Number(it.max_points || 0), 0);
    if (parsed.totalPoints) setTotalPoints(String(parsed.totalPoints));
    else if (sumPts > Number(totalPoints || 0)) setTotalPoints(String(sumPts));
    if (parsed.name && !name) setName(parsed.name);
    setShowPasteBox(false);
    setPasteText("");
    setDryRunResult(null);
    toast(`นำเข้าเกณฑ์สำเร็จ ${parsed.items.length} ข้อ`);
  };

  const handleCopyRubricClipboard = async (r: Rubric) => {
    const payload = JSON.stringify({ name: r.name, total_points: r.total_points, items: r.items }, null, 2);
    try {
      await navigator.clipboard.writeText(payload);
      toast(`คัดลอกเกณฑ์ "${r.name}" ลงคลิปบอร์ดแล้ว`);
    } catch {
      toast("ไม่สามารถคัดลอกลงคลิปบอร์ดได้", "error");
    }
  };

  const handleDuplicateRubric = async (id: string) => {
    try {
      await apiRequest(`/rubrics/${id}/duplicate`, { method: "POST" });
      toast("ทำสำเนาชุดเกณฑ์เรียบร้อยแล้ว");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "คัดลอกชุดเกณฑ์ไม่สำเร็จ", "error");
    }
  };

  const openCreateModal = () => {
    setEditingRubricId(null);
    setName("");
    setAssignmentId("");
    setTotalPoints("20");
    setItems([makeEmptyItem(0)]);
    setSampleInfo(null);
    setDryRunResult(null);
    setFreeformText("");
    setShowPasteBox(false);
    setBuilderTab("answer_key");
    setOpenBuilder(true);
  };

  const openEditModal = (r: Rubric) => {
    setEditingRubricId(r.id);
    setName(r.name);
    setAssignmentId(r.assignment_id || "");
    setTotalPoints(String(r.total_points));
    setItems(
      r.items.length > 0
        ? r.items.map((it, idx) => ({
            ...it,
            order_index: idx,
            rule_config: JSON.parse(JSON.stringify(it.rule_config || {})),
          }))
        : [makeEmptyItem(0)]
    );
    setSampleInfo(null);
    setDryRunResult(null);
    setFreeformText("");
    setShowPasteBox(false);
    setBuilderTab("answer_key");
    setOpenBuilder(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (exceeds) {
      toast("คะแนนรวมของเกณฑ์ย่อยเกินคะแนนเต็ม กดปุ่ม 'เฉลี่ยคะแนนให้พอดี' ก่อนนะครับ", "error");
      return;
    }
    setSaving(true);
    try {
      const endpoint = editingRubricId ? `/rubrics/${editingRubricId}` : "/rubrics";
      const method = editingRubricId ? "PUT" : "POST";
      const normalizedItems = items.map((it, idx) => ({
        ...it,
        order_index: idx,
      }));
      const saved = await apiRequest<Rubric>(endpoint, {
        method,
        body: JSON.stringify({
          name,
          assignment_id: assignmentId || null,
          total_points: Number(totalPoints),
          items: normalizedItems,
          change_note: editingRubricId ? "แก้ไขเกณฑ์การตรวจ" : "สร้างชุดเกณฑ์ใหม่",
        }),
      });
      // Immediately reflect saved rubric in UI state so changes are 100% live right away
      setRubrics((prev) =>
        editingRubricId
          ? [saved, ...prev.filter((r) => r.id !== saved.id)]
          : [saved, ...prev]
      );
      toast(
        editingRubricId
          ? `บันทึก "${saved.name}" (เวอร์ชัน ${saved.current_version}) เรียบร้อยแล้ว ✨`
          : `สร้างชุดเกณฑ์ "${saved.name}" สำเร็จ ✨`
      );
      setOpenBuilder(false);
      setEditingRubricId(null);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกเกณฑ์ไม่สำเร็จ", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiRequest(`/rubrics/${id}`, { method: "DELETE" });
      toast("ลบชุดเกณฑ์แล้ว");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ลบเกณฑ์ไม่สำเร็จ", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Icon3D emoji="🎯" tone="lavender" size="lg" />
          <div>
            <h1 className="text-2xl font-extrabold text-[#172B1C]">ตั้งเกณฑ์การตรวจแบบเป๊ะ 100% ✨</h1>
            <p className="text-sm text-[#5C7061]">
              แนบไฟล์เฉลย Excel ที่ครูทำเสร็จแล้วให้ระบบดึงสูตร/ตัวกรองเป๊ะทุกช่อง พร้อมปุ่มจำลองตรวจเช็กความแม่นก่อนใช้จริง
            </p>
          </div>
        </div>
        <Button size="lg" onClick={openCreateModal}>
          <Plus className="h-4 w-4" /> สร้างชุดเกณฑ์ใหม่
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <Skeleton className="h-56" />
      ) : rubrics.length === 0 ? (
        <EmptyState
          title="ยังไม่มีชุดเกณฑ์การตรวจ"
          description="กดสร้างชุดเกณฑ์ใหม่แล้วโยนไฟล์เฉลย Excel ที่ทำเสร็จแล้วลงไป ระบบจะสร้างเกณฑ์ที่ตรวจเป๊ะ 100% ให้อัตโนมัติ!"
          action={<Button onClick={openCreateModal}>✨ สร้างเกณฑ์ชุดแรก</Button>}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rubrics.map((r) => (
            <Card key={r.id} className="space-y-3 clay-card-hover">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <Icon3D emoji="🎯" tone="lavender" size="sm" />
                  <div>
                    <h3 className="font-extrabold text-[#172B1C]">{r.name}</h3>
                    <p className="text-xs text-[#5C7061]">
                      เวอร์ชัน {r.current_version} • {r.items.length} ข้อตรวจ
                    </p>
                  </div>
                </div>
                <Badge tone="mint">
                  {r.allocated_points}/{r.total_points} คะแนน
                </Badge>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {r.items.slice(0, 6).map((i, idx) => (
                  <Badge key={idx} tone="sky">
                    {i.title} ({i.max_points})
                  </Badge>
                ))}
              </div>

              <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-[#EAF5E7]">
                <Link
                  href={`/reports?rubric_id=${encodeURIComponent(r.id)}${
                    r.assignment_id
                      ? `&assignment_id=${encodeURIComponent(r.assignment_id)}&auto_regrade=1`
                      : ""
                  }`}
                >
                  <Button size="sm" variant="mint">
                    <RefreshCw className="h-3.5 w-3.5" /> รีตรวจด้วยเกณฑ์นี้
                  </Button>
                </Link>
                <Button size="sm" variant="primary" onClick={() => openEditModal(r)}>
                  <Pencil className="h-3.5 w-3.5" /> แก้ไขเกณฑ์
                </Button>
                <Button size="sm" variant="outline" onClick={() => setPreviewRubric(r)}>
                  <Eye className="h-3.5 w-3.5" /> ดูรายละเอียด
                </Button>
                <Button size="sm" variant="secondary" onClick={() => handleCopyRubricClipboard(r)}>
                  <ClipboardCopy className="h-3.5 w-3.5" /> คัดลอก
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleDuplicateRubric(r.id)}>
                  <Copy className="h-3.5 w-3.5" /> ทำสำเนา
                </Button>
                <Button size="sm" variant="danger" onClick={() => handleDelete(r.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Redesigned Zero-Guesswork Rubric Studio Modal */}
      <Modal
        open={openBuilder}
        onClose={() => {
          setOpenBuilder(false);
          setEditingRubricId(null);
        }}
        title={editingRubricId ? "🎯 แก้ไขชุดเกณฑ์การตรวจ" : "🎯 สร้างชุดเกณฑ์การตรวจแบบเป๊ะ 100%"}
        maxWidth="max-w-5xl"
      >
        <form onSubmit={handleSave} className="space-y-4">
          {/* Basic Info Row */}
          <div className="grid gap-3 sm:grid-cols-12">
            <div className="sm:col-span-6">
              <label className="mb-1 block text-xs font-bold text-[#172B1C]">ชื่อชุดเกณฑ์ *</label>
              <Input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="เช่น ใบงานที่ 4 การกรองข้อมูลสินค้า"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-bold text-[#172B1C]">คะแนนเต็ม *</label>
              <Input
                type="number"
                step="0.5"
                required
                value={totalPoints}
                onChange={(e) => setTotalPoints(e.target.value)}
              />
            </div>
            <div className="sm:col-span-4">
              <label className="mb-1 block text-xs font-bold text-[#172B1C]">ผูกกับงาน Classroom (ไม่บังคับ)</label>
              <Select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}>
                <option value="">-- ใช้ได้กับทุกงาน --</option>
                {assignments.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title}
                    {a.class_name ? ` — 🏫 ${a.class_name}` : ""}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {/* 3 Easy Creation Mode Tabs */}
          <div className="flex flex-wrap gap-2 border-b border-[#E5F2E1] pb-2">
            <button
              type="button"
              onClick={() => setBuilderTab("answer_key")}
              className={`rounded-full px-4 py-1.5 text-xs font-bold transition cursor-pointer ${
                builderTab === "answer_key"
                  ? "clay-pill-active"
                  : "bg-[#F4FAF2] text-[#445B49] hover:bg-[#E7F6E3]"
              }`}
            >
              📁 1. แนบไฟล์เฉลย Excel ดึงเกณฑ์เป๊ะ 100% (แนะนำที่สุด!)
            </button>
            <button
              type="button"
              onClick={() => setBuilderTab("quick_pick")}
              className={`rounded-full px-4 py-1.5 text-xs font-bold transition cursor-pointer ${
                builderTab === "quick_pick"
                  ? "clay-pill-active"
                  : "bg-[#F4FAF2] text-[#445B49] hover:bg-[#E7F6E3]"
              }`}
            >
              ⚡ 2. จิ้มเลือกสูตร / ตัวกรอง / กราฟด่วน
            </button>
            <button
              type="button"
              onClick={() => setBuilderTab("text_prompt")}
              className={`rounded-full px-4 py-1.5 text-xs font-bold transition cursor-pointer ${
                builderTab === "text_prompt"
                  ? "clay-pill-active"
                  : "bg-[#F4FAF2] text-[#445B49] hover:bg-[#E7F6E3]"
              }`}
            >
              💬 3. วางโจทย์ภาษาไทย / คัดลอกเกณฑ์
            </button>
          </div>

          {/* TAB 1: Master Answer Key Upload (100% Exact Ground-Truth!) */}
          {builderTab === "answer_key" && (
            <div className="rounded-3xl border-2 border-[#B6E8A2] bg-gradient-to-br from-[#F2FCEE] to-[#E6F9DF] p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <Icon3D emoji="🏆" tone="yellow" size="sm" />
                  <div>
                    <p className="text-sm font-extrabold text-[#16361C]">
                      วิธีที่แม่นยำ 100%: อัปโหลด &ldquo;ไฟล์เฉลย Excel ที่ครูทำเสร็จสมบูรณ์แล้ว&rdquo;
                    </p>
                    <p className="text-xs text-[#445B49]">
                      ไม่ว่าจะเป็นงาน <strong>ผูกสูตรคำนวณ</strong>, <strong>กรองข้อมูลหลายแท็บ (Filter)</strong> หรือ <strong>สร้างกราฟ</strong> ระบบจะแกะคำตอบจริงทุกเซลล์และทุกแท็บมาเป็นเกณฑ์ให้ทันทีโดยไม่ต้องเดา!
                    </p>
                  </div>
                </div>
                <label className="clay-btn-green inline-flex cursor-pointer items-center gap-2 rounded-full px-4 py-2 text-xs font-bold">
                  <Upload className="h-4 w-4" />
                  {sampleUploading ? "กำลังแกะไฟล์เฉลย..." : "อัปโหลดไฟล์เฉลย (.xlsx)"}
                  <input
                    type="file"
                    accept=".xlsx,.xls,.xlsm"
                    className="hidden"
                    disabled={sampleUploading}
                    onChange={(e) => handleSampleFileUpload(e.target.files?.[0] || null)}
                  />
                </label>
              </div>

              {sampleInfo && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white px-4 py-2.5 text-xs border border-[#CBE8BF]">
                  <div>
                    <p className="font-bold text-[#172B1C]">
                      ✅ ไฟล์เฉลยพร้อมใช้: {sampleInfo.filename}
                    </p>
                    <p className="text-[#5C7061]">
                      พบ {sampleInfo.sheet_names.length} แท็บ ({sampleInfo.sheet_names.join(", ")}) • พบสูตร {sampleInfo.formula_count} เซลล์
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {sampleInfo.suggested_items.length > 0 && (
                      <Button type="button" size="sm" variant="mint" onClick={handleUseSuggestedItems}>
                        <Sparkles className="h-3.5 w-3.5" /> ใช้เกณฑ์จากไฟล์เฉลย ({sampleInfo.suggested_items.length} ข้อ)
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      loading={testingSample}
                      onClick={handleTestAgainstSample}
                    >
                      <FlaskConical className="h-3.5 w-3.5" /> ทดสอบตรวจกับไฟล์เฉลย!
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Quick Formula & Filter Chips */}
          {builderTab === "quick_pick" && (
            <div className="rounded-3xl border-2 border-[#D5E6FB] bg-[#F4F9FF] p-4 space-y-3">
              <p className="text-xs font-bold text-[#164E78]">
                คลิกเลือกสูตรหรือฟีเจอร์ที่ต้องการตรวจ (กดซ้ำเพื่อเอาออก):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {[...FORMULA_PRESETS, ...extraFormulas].map((fn) => {
                  const checked = items.some(
                    (it) =>
                      it.category === "formula" &&
                      (Array.isArray(it.rule_config.required_functions)
                        ? (it.rule_config.required_functions as string[]).includes(fn)
                        : it.title.toUpperCase().includes(fn))
                  );
                  return (
                    <button
                      key={fn}
                      type="button"
                      onClick={() => toggleFormulaPreset(fn)}
                      className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-bold transition cursor-pointer ${
                        checked
                          ? "border-[#4BA828] bg-[#65C73E] text-white shadow-xs"
                          : "border-[#CBE0F8] bg-white text-[#1D4E7A] hover:bg-[#E8F3FF]"
                      }`}
                    >
                      <span>{checked ? "✓" : "+"}</span>
                      <span>{fn}</span>
                    </button>
                  );
                })}
              </div>
              <div className="flex flex-wrap gap-2 pt-2 border-t border-[#DCEBFA]">
                <Button
                  type="button"
                  size="sm"
                  variant="mint"
                  onClick={() =>
                    setItems((prev) => [
                      ...(prev.length === 1 && !prev[0].title.trim() ? [] : prev),
                      {
                        ...makeEmptyItem(prev.length),
                        title: "ตรวจตัวกรองข้อมูล (Filter)",
                        category: "structure",
                        sheet_name: sampleInfo?.sheet_names[0] || "",
                        rule_config: {
                          require_autofilter: true,
                          filter_conditions: [{ column: "", operator: "equals", value: "" }],
                        },
                      },
                    ])
                  }
                >
                  + เพิ่มข้อตรวจตัวกรอง (Filter)
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setItems((prev) => [
                      ...(prev.length === 1 && !prev[0].title.trim() ? [] : prev),
                      {
                        ...makeEmptyItem(prev.length),
                        title: "ตรวจแผนภูมิ (Chart)",
                        category: "chart",
                        sheet_name: sampleInfo?.sheet_names[0] || "",
                        rule_config: { chart_type: "column" },
                      },
                    ])
                  }
                >
                  + เพิ่มข้อตรวจแผนภูมิ
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setItems((prev) => [
                      ...(prev.length === 1 && !prev[0].title.trim() ? [] : prev),
                      {
                        ...makeEmptyItem(prev.length),
                        title: "ความสวยงามและการตกแต่งตาราง (เลือกสีเองได้)",
                        category: "style",
                        sheet_name: sampleInfo?.sheet_names[0] || "",
                        rule_config: {
                          match_reference_layout_ignore_color: true,
                          bold: true,
                          has_border: true,
                          has_fill_color: true,
                        },
                      },
                    ])
                  }
                >
                  + เพิ่มความสวยงามตาราง
                </Button>
                <div className="flex gap-1.5 ml-auto">
                  <Input
                    value={customFormulaInput}
                    onChange={(e) => setCustomFormulaInput(e.target.value)}
                    placeholder="พิมพ์ชื่อสูตรอื่น เช่น PMT..."
                    className="h-8 w-44 text-xs"
                  />
                  <Button type="button" size="sm" variant="secondary" onClick={handleAddCustomFormula}>
                    เพิ่มสูตร
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Thai Natural Language Prompt or Copy-Paste */}
          {builderTab === "text_prompt" && (
            <div className="rounded-3xl border-2 border-[#E2D6FE] bg-[#F8F5FF] p-4 space-y-3">
              <p className="text-xs font-bold text-[#3B1D7A]">
                วางโจทย์ใบงานภาษาไทย (เช่น ข้อ 1..ข้อ 6) แล้วให้ระบบแปลงเป็นข้อเกณฑ์ให้อัตโนมัติ:
              </p>
              <Textarea
                rows={4}
                value={freeformText}
                onChange={(e) => setFreeformText(e.target.value)}
                placeholder="วางคำสั่งโจทย์ได้เลย เช่น ข้อ 1 กรองยี่ห้อ 'Pentel' ... หรือ ตรวจสูตร SUM, AVERAGE, IF..."
              />
              <div className="flex flex-wrap justify-between gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => setShowPasteBox((v) => !v)}>
                  <ClipboardPaste className="h-3.5 w-3.5" /> วางเกณฑ์จาก JSON / ตาราง
                </Button>
                <Button type="button" size="sm" loading={expanding} onClick={handleExpandFreeform}>
                  <Sparkles className="h-3.5 w-3.5" /> แปลงโจทย์เป็นข้อเกณฑ์อัตโนมัติ
                </Button>
              </div>
              {showPasteBox && (
                <div className="rounded-2xl border border-sky-200 bg-white p-3 space-y-2">
                  <Textarea
                    rows={4}
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    placeholder="วาง JSON จากปุ่มคัดลอกเกณฑ์ หรือ รายการ | คะแนน"
                  />
                  <div className="flex justify-end gap-2">
                    <Button type="button" size="sm" onClick={handleApplyPaste}>
                      นำเข้าเกณฑ์ที่วาง
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Dry-Run Self-Verification Result Banner */}
          {dryRunResult && (
            <div
              className={`rounded-2xl border-2 p-3.5 text-xs space-y-2 ${
                dryRunResult.all_passed
                  ? "border-[#9CE077] bg-[#EEFCE7] text-[#17461F]"
                  : "border-amber-300 bg-amber-50 text-amber-950"
              }`}
            >
              <div className="flex items-center justify-between">
                <p className="font-extrabold text-sm">
                  {dryRunResult.all_passed
                    ? `🎉 ทดสอบกับไฟล์เฉลยผ่านเป๊ะ 100%! ได้คะแนนเต็ม ${dryRunResult.auto_score} / ${dryRunResult.max_score}`
                    : `⚠️ ผลทดสอบกับไฟล์เฉลยได้ ${dryRunResult.auto_score} / ${dryRunResult.max_score} คะแนน (ตรวจสอบข้อที่ขึ้นสีส้มด้านล่าง)`}
                </p>
                <button type="button" onClick={() => setDryRunResult(null)} className="underline text-[11px]">
                  ซ่อนผลทดสอบ
                </button>
              </div>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {dryRunResult.details.map((d, dIdx) => (
                  <div
                    key={dIdx}
                    className={`rounded-xl px-2.5 py-1.5 border ${
                      d.passed ? "bg-white/90 border-[#BCE8A8]" : "bg-white border-rose-300 text-rose-800"
                    }`}
                  >
                    <strong>{d.passed ? "✅" : "❌"} {d.item_title}:</strong> {d.earned_points}/{d.max_points} คะแนน
                    {!d.passed && <div className="text-[11px] mt-0.5">{d.reason}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Points Budget Bar + Action Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-[#F2FAF0] border border-[#D8EED3] px-4 py-2.5 text-xs">
            <div>
              รวมคะแนนย่อย:{" "}
              <strong className={exceeds ? "text-rose-600 text-sm" : "text-[#1B5E28] text-sm"}>
                {allocated}
              </strong>{" "}
              / {totalPoints} คะแนน ({items.length} ข้อ)
              {exceeds && <span className="ml-2 text-rose-600 font-semibold">⚠️ เกินคะแนนเต็ม! กดปุ่มเฉลี่ยคะแนนด้านขวาได้เลย</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {sampleInfo?.storage_path && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  loading={testingSample}
                  onClick={handleTestAgainstSample}
                >
                  <FlaskConical className="h-3.5 w-3.5" /> ทดสอบกับไฟล์เฉลย
                </Button>
              )}
              <Button type="button" size="sm" variant="mint" onClick={handleAutoDistributePoints}>
                <Sparkles className="h-3.5 w-3.5" /> เฉลี่ยคะแนนให้พอดี ({totalPoints})
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setItems([...items, makeEmptyItem(items.length)])}
              >
                <Plus className="h-3.5 w-3.5" /> เพิ่มข้อตรวจเอง
              </Button>
            </div>
          </div>

          {/* Visual Per-Item Cards (Transparent & Editable!) */}
          <div className="space-y-3 max-h-[42vh] overflow-y-auto pr-1">
            {items.map((it, idx) => {
              const sheetCols = (it.sheet_name && sampleInfo?.columns_by_sheet?.[it.sheet_name]) || [];
              const hasAnswerKeyFilter =
                Array.isArray(it.rule_config.expected_visible_row_numbers) &&
                (it.rule_config.expected_visible_row_numbers as number[]).length > 0;

              return (
                <div
                  key={idx}
                  className="rounded-2xl border-2 border-[#E2F0DF] bg-white p-3.5 space-y-2.5 shadow-2xs"
                >
                  {/* Top Row: # + Title + Category + Points */}
                  <div className="grid gap-2 sm:grid-cols-12 items-center">
                    <div className="sm:col-span-6 flex items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#E6F8DF] text-xs font-extrabold text-[#1E5626]">
                        {idx + 1}
                      </span>
                      <Input
                        required
                        placeholder="ชื่อข้อตรวจ เช่น ข้อ 1 กรองยี่ห้อ Pentel หรือ ตรวจสูตร SUM"
                        value={it.title}
                        onChange={(e) => updateItem(idx, { title: e.target.value })}
                      />
                    </div>
                    <div className="sm:col-span-4">
                      <Select
                        value={it.category}
                        onChange={(e) => updateItem(idx, { category: e.target.value, rule_config: {} })}
                      >
                        {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <div className="sm:col-span-2">
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="คะแนน"
                        value={it.max_points}
                        onChange={(e) => updateItem(idx, { max_points: Number(e.target.value) })}
                      />
                    </div>
                  </div>

                  {/* Category-Specific Clear Controls */}
                  {it.category === "formula" && (
                    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-[#F7FBF6] border border-[#E4F2E1] p-2.5 text-xs">
                      <span className="font-bold text-[#234B2B]">แท็บ:</span>
                      {sampleInfo && sampleInfo.sheet_names.length > 0 ? (
                        <Select
                          value={it.sheet_name || ""}
                          onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                          className="h-8 w-40 text-xs"
                        >
                          <option value="">(สแกนอัตโนมัติ)</option>
                          {sampleInfo.sheet_names.map((sn) => (
                            <option key={sn} value={sn}>
                              {sn}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          value={it.sheet_name || ""}
                          onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                          placeholder="เว้นว่าง = หาเอง"
                          className="h-8 w-36 text-xs"
                        />
                      )}

                      <span className="font-bold text-[#234B2B]">เซลล์/ช่วง:</span>
                      <Input
                        value={it.target_cell || ""}
                        onChange={(e) => updateItem(idx, { target_cell: e.target.value })}
                        placeholder="เช่น E2:E31 หรือเว้นว่าง"
                        className="h-8 w-36 text-xs font-mono"
                      />

                      <span className="font-bold text-[#234B2B]">ฟังก์ชันบังคับ:</span>
                      <Input
                        value={
                          Array.isArray(it.rule_config.required_functions)
                            ? (it.rule_config.required_functions as string[]).join(", ")
                            : ""
                        }
                        onChange={(e) => {
                          const fns = e.target.value
                            .split(",")
                            .map((s) => s.trim().toUpperCase())
                            .filter(Boolean);
                          updateItem(idx, {
                            rule_config: { ...it.rule_config, required_functions: fns },
                          });
                        }}
                        placeholder="เช่น SUM, IF"
                        className="h-8 w-36 text-xs font-mono"
                      />

                      {Boolean(it.rule_config.expected_formulas_by_cell) && (
                        <Badge tone="mint">✓ ล็อกสูตรเฉลยรายเซลล์เป๊ะ 100%</Badge>
                      )}
                    </div>
                  )}

                  {it.category === "structure" && (
                    <div className="rounded-xl border border-[#D7EED2] bg-[#F5FCF3] p-2.5 space-y-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-[#1B4D23]">แท็บที่ตรวจ:</span>
                        {sampleInfo && sampleInfo.sheet_names.length > 0 ? (
                          <Select
                            value={it.sheet_name || ""}
                            onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                            className="h-8 w-44 text-xs bg-white"
                          >
                            <option value="">-- เลือกแท็บ --</option>
                            {sampleInfo.sheet_names.map((sn) => (
                              <option key={sn} value={sn}>
                                {sn}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <Input
                            value={it.sheet_name || ""}
                            onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                            placeholder="เช่น ข้อที่1, ข้อที่5"
                            className="h-8 w-40 text-xs bg-white"
                          />
                        )}

                        {hasAnswerKeyFilter ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone="mint">
                              🎯 เทียบแถวที่กรองตรงกับไฟล์เฉลยเป๊ะ 100% (แสดง {(it.rule_config.expected_visible_row_numbers as number[]).length} รายการ)
                            </Badge>
                            <button
                              type="button"
                              onClick={() =>
                                updateItem(idx, {
                                  rule_config: {
                                    require_autofilter: true,
                                    filter_conditions: [{ column: "", operator: "equals", value: "" }],
                                  },
                                })
                              }
                              className="text-[11px] font-semibold text-sky-700 underline cursor-pointer"
                            >
                              เปลี่ยนเป็นกำหนดเงื่อนไขคอลัมน์เอง
                            </button>
                          </div>
                        ) : (
                          <label className="inline-flex items-center gap-1.5 font-semibold text-[#1B4D23]">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_no_active_filter)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: e.target.checked
                                    ? {
                                        require_no_active_filter: true,
                                        expected_visible_rows: Number(it.rule_config.expected_visible_rows || 30),
                                      }
                                    : {
                                        require_autofilter: true,
                                        filter_conditions: [{ column: "", operator: "equals", value: "" }],
                                      },
                                })
                              }
                            />
                            โจทย์ให้ยกเลิกตัวกรองทั้งหมด
                          </label>
                        )}

                        {Boolean(it.rule_config.require_no_active_filter) && (
                          <div className="inline-flex items-center gap-1">
                            <span>ต้องแสดงครบ:</span>
                            <Input
                              type="number"
                              value={Number(it.rule_config.expected_visible_rows ?? 30)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, expected_visible_rows: Number(e.target.value) },
                                })
                              }
                              className="h-8 w-20 text-xs bg-white"
                            />
                            <span>รายการ</span>
                          </div>
                        )}
                      </div>

                      {!hasAnswerKeyFilter && !it.rule_config.require_no_active_filter && (
                        <div className="space-y-1.5">
                          {(Array.isArray(it.rule_config.filter_conditions)
                            ? (it.rule_config.filter_conditions as { column?: string; operator?: string; value?: string | number }[])
                            : []
                          ).map((fc, fcIdx, arr) => (
                            <div key={fcIdx} className="flex flex-wrap items-center gap-1.5">
                              {sheetCols.length > 0 ? (
                                <Select
                                  value={fc.column || ""}
                                  onChange={(e) => {
                                    const next = [...arr];
                                    next[fcIdx] = { ...fc, column: e.target.value };
                                    updateItem(idx, {
                                      rule_config: { ...it.rule_config, require_autofilter: true, filter_conditions: next },
                                    });
                                  }}
                                  className="h-8 w-48 text-xs bg-white"
                                >
                                  <option value="">-- เลือกคอลัมน์ --</option>
                                  {sheetCols.map((colName) => (
                                    <option key={colName} value={colName}>
                                      {colName}
                                    </option>
                                  ))}
                                </Select>
                              ) : (
                                <Input
                                  value={fc.column || ""}
                                  onChange={(e) => {
                                    const next = [...arr];
                                    next[fcIdx] = { ...fc, column: e.target.value };
                                    updateItem(idx, {
                                      rule_config: { ...it.rule_config, require_autofilter: true, filter_conditions: next },
                                    });
                                  }}
                                  placeholder="ชื่อคอลัมน์ เช่น ยอดขาย, ประเภท"
                                  className="h-8 w-44 text-xs bg-white"
                                />
                              )}

                              <Select
                                value={fc.operator || "equals"}
                                onChange={(e) => {
                                  const next = [...arr];
                                  next[fcIdx] = { ...fc, operator: e.target.value };
                                  updateItem(idx, {
                                    rule_config: { ...it.rule_config, require_autofilter: true, filter_conditions: next },
                                  });
                                }}
                                className="h-8 w-44 text-xs bg-white"
                              >
                                <option value="equals">เท่ากับ (=)</option>
                                <option value="not_equals">ไม่เท่ากับ (≠)</option>
                                <option value="starts_with">ขึ้นต้นด้วย</option>
                                <option value="ends_with">ลงท้ายด้วย</option>
                                <option value="contains">มีคำว่า</option>
                                <option value="gt">มากกว่า (&gt;)</option>
                                <option value="gte">ตั้งแต่ (&gt;=)</option>
                                <option value="lt">น้อยกว่า (&lt;)</option>
                                <option value="lte">ไม่เกิน (&lt;=)</option>
                              </Select>

                              <Input
                                value={String(fc.value ?? "")}
                                onChange={(e) => {
                                  const raw = e.target.value;
                                  const isNumOp = ["gt", "gte", "lt", "lte"].includes(fc.operator || "");
                                  const parsedVal =
                                    isNumOp && raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
                                  const next = [...arr];
                                  next[fcIdx] = { ...fc, value: parsedVal };
                                  updateItem(idx, {
                                    rule_config: { ...it.rule_config, require_autofilter: true, filter_conditions: next },
                                  });
                                }}
                                placeholder="ค่าที่ต้องการ เช่น 50, Pentel"
                                className="h-8 w-44 text-xs bg-white"
                              />

                              <button
                                type="button"
                                onClick={() => {
                                  const next = arr.filter((_, i) => i !== fcIdx);
                                  updateItem(idx, { rule_config: { ...it.rule_config, filter_conditions: next } });
                                }}
                                className="rounded-lg px-2 py-1 text-rose-600 hover:bg-rose-50 cursor-pointer"
                              >
                                ลบ
                              </button>
                            </div>
                          ))}
                          <button
                            type="button"
                            onClick={() => {
                              const curr = Array.isArray(it.rule_config.filter_conditions)
                                ? (it.rule_config.filter_conditions as Record<string, unknown>[])
                                : [];
                              updateItem(idx, {
                                rule_config: {
                                  ...it.rule_config,
                                  require_autofilter: true,
                                  filter_conditions: [...curr, { column: "", operator: "equals", value: "" }],
                                },
                              });
                            }}
                            className="text-[11px] font-bold text-[#257A33] hover:underline cursor-pointer"
                          >
                            + เพิ่มเงื่อนไขกรองในแท็บนี้ (เช่น กรอง 2 คอลัมน์พร้อมกัน)
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {it.category === "chart" && (
                    <div className="rounded-xl bg-[#F4F9FF] border border-[#D6E8FC] p-3 space-y-2.5 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-[#164E78]">แท็บ:</span>
                        {sampleInfo && sampleInfo.sheet_names.length > 0 ? (
                          <Select
                            value={it.sheet_name || ""}
                            onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                            className="h-8 w-36 text-xs bg-white"
                          >
                            <option value="">(หาทุกแท็บ)</option>
                            {sampleInfo.sheet_names.map((sn) => (
                              <option key={sn} value={sn}>
                                {sn}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <Input
                            value={it.sheet_name || ""}
                            onChange={(e) => updateItem(idx, { sheet_name: e.target.value })}
                            placeholder="เว้นว่าง = หาทุกแท็บ"
                            className="h-8 w-36 text-xs bg-white"
                          />
                        )}

                        <span className="font-bold text-[#164E78]">ประเภทแผนภูมิ:</span>
                        <Select
                          value={String(it.rule_config.chart_type || "bar_or_column")}
                          onChange={(e) =>
                            updateItem(idx, { rule_config: { ...it.rule_config, chart_type: e.target.value } })
                          }
                          className="h-8 w-52 text-xs bg-white"
                        >
                          <option value="bar_or_column">คอลัมน์หรือแท่งก็ได้ (ยืดหยุ่น)</option>
                          <option value="column">แผนภูมิคอลัมน์แนวตั้ง (Column)</option>
                          <option value="bar">แผนภูมิแท่งแนวนอน (Bar)</option>
                          <option value="pie">แผนภูมิวงกลม (Pie)</option>
                          <option value="doughnut">แผนภูมิโดนัท (Doughnut)</option>
                          <option value="line">แผนภูมิเส้น (Line)</option>
                          <option value="area">แผนภูมิพื้นที่ (Area)</option>
                          <option value="scatter">แผนภูมิกระจาย (XY Scatter)</option>
                        </Select>

                        <span className="font-bold text-[#164E78]">ช่วงข้อมูล:</span>
                        <Input
                          value={String(it.rule_config.required_data_range || "")}
                          onChange={(e) =>
                            updateItem(idx, {
                              rule_config: { ...it.rule_config, required_data_range: e.target.value },
                            })
                          }
                          placeholder="เช่น A1:B10 (ไม่บังคับ)"
                          className="h-8 w-36 text-xs bg-white font-mono"
                        />
                      </div>

                      <div className="pt-1.5 border-t border-[#DCEBFA] space-y-2">
                        <p className="font-bold text-[#164E78]">
                          📌 เลือกองค์ประกอบของแผนภูมิที่ต้องการตรวจ (Chart Elements):
                        </p>
                        <div className="grid gap-2 sm:grid-cols-3">
                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_title || it.rule_config.expected_title)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: {
                                    ...it.rule_config,
                                    require_title: e.target.checked,
                                    ...(e.target.checked ? {} : { expected_title: "" }),
                                  },
                                })
                              }
                            />
                            ชื่อแผนภูมิ (Chart Title)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_x_axis_title || it.rule_config.x_axis_title)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: {
                                    ...it.rule_config,
                                    require_x_axis_title: e.target.checked,
                                    ...(e.target.checked ? {} : { x_axis_title: "" }),
                                  },
                                })
                              }
                            />
                            ชื่อแกนแนวนอน (แกน X)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_y_axis_title || it.rule_config.y_axis_title)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: {
                                    ...it.rule_config,
                                    require_y_axis_title: e.target.checked,
                                    ...(e.target.checked ? {} : { y_axis_title: "" }),
                                  },
                                })
                              }
                            />
                            ชื่อแกนแนวตั้ง (แกน Y)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_data_labels)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, require_data_labels: e.target.checked },
                                })
                              }
                            />
                            ป้ายกำกับข้อมูล (Data Labels)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_percent_labels)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, require_percent_labels: e.target.checked },
                                })
                              }
                            />
                            แสดงเปอร์เซ็นต์ % (กราฟวงกลม)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_legend || it.rule_config.legend_position)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: {
                                    ...it.rule_config,
                                    require_legend: e.target.checked,
                                    ...(e.target.checked ? {} : { legend_position: "" }),
                                  },
                                })
                              }
                            />
                            คำอธิบายแผนภูมิ (Legend)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_data_table)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, require_data_table: e.target.checked },
                                })
                              }
                            />
                            ตารางข้อมูลใต้กราฟ (Data Table)
                          </label>

                          <label className="inline-flex items-center gap-1.5 font-medium text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(it.rule_config.require_gridlines)}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, require_gridlines: e.target.checked },
                                })
                              }
                            />
                            เส้นตารางในกราฟ (Gridlines)
                          </label>
                        </div>

                        {/* Optional specific title / legend position inputs when checked */}
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          {Boolean(it.rule_config.require_title || it.rule_config.expected_title) && (
                            <Input
                              value={String(it.rule_config.expected_title || "")}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, expected_title: e.target.value },
                                })
                              }
                              placeholder="คำที่ต้องมีในชื่อแผนภูมิ (เว้นว่าง = ตั้งชื่ออะไรก็ได้)"
                              className="h-8 w-72 text-xs bg-white"
                            />
                          )}
                          {Boolean(it.rule_config.require_legend || it.rule_config.legend_position) && (
                            <Select
                              value={String(it.rule_config.legend_position || "")}
                              onChange={(e) =>
                                updateItem(idx, {
                                  rule_config: { ...it.rule_config, legend_position: e.target.value },
                                })
                              }
                              className="h-8 w-48 text-xs bg-white"
                            >
                              <option value="">ตำแหน่ง Legend: ตำแหน่งใดก็ได้</option>
                              <option value="r">ตำแหน่ง Legend: ด้านขวา</option>
                              <option value="b">ตำแหน่ง Legend: ด้านล่าง</option>
                              <option value="t">ตำแหน่ง Legend: ด้านบน</option>
                              <option value="l">ตำแหน่ง Legend: ด้านซ้าย</option>
                            </Select>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {it.category === "style" && (
                    <div className="flex flex-wrap items-center gap-4 rounded-xl bg-[#FFF9FB] border border-[#FBD5E3] p-2.5 text-xs">
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={Boolean(it.rule_config.has_border ?? true)}
                          onChange={(e) =>
                            updateItem(idx, { rule_config: { ...it.rule_config, has_border: e.target.checked } })
                          }
                        />
                        ตีเส้นขอบตาราง
                      </label>
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={Boolean(it.rule_config.bold ?? true)}
                          onChange={(e) =>
                            updateItem(idx, { rule_config: { ...it.rule_config, bold: e.target.checked } })
                          }
                        />
                        ตัวหนาหัวตาราง
                      </label>
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={Boolean(it.rule_config.has_fill_color ?? true)}
                          onChange={(e) =>
                            updateItem(idx, { rule_config: { ...it.rule_config, has_fill_color: e.target.checked } })
                          }
                        />
                        เติมสีตกแต่ง (สีใดก็ได้)
                      </label>
                    </div>
                  )}

                  {/* Bottom Item Controls */}
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#5C7061]">
                    <div className="flex flex-wrap items-center gap-4">
                      <label className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={it.allow_partial_credit}
                          onChange={(e) => updateItem(idx, { allow_partial_credit: e.target.checked })}
                        />
                        ให้คะแนนบางส่วนได้
                      </label>
                      <label className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={it.zero_on_error}
                          onChange={(e) => updateItem(idx, { zero_on_error: e.target.checked })}
                        />
                        ผิดได้ 0 ทันที
                      </label>
                    </div>
                    {items.length > 1 && (
                      <button
                        type="button"
                        onClick={() => {
                          setDryRunResult(null);
                          setItems(items.filter((_, i) => i !== idx));
                        }}
                        className="text-rose-600 font-semibold hover:underline cursor-pointer"
                      >
                        ลบข้อนี้
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-[#E5F2E1]">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setOpenBuilder(false);
                setEditingRubricId(null);
              }}
            >
              ยกเลิก
            </Button>
            <Button type="submit" size="lg" loading={saving} disabled={exceeds}>
              <CheckCircle2 className="h-4 w-4" />
              {editingRubricId ? "บันทึกการแก้ไขเกณฑ์" : "บันทึกชุดเกณฑ์"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Preview Modal */}
      <Modal
        open={Boolean(previewRubric)}
        onClose={() => setPreviewRubric(null)}
        title={`รายละเอียดเกณฑ์: ${previewRubric?.name || ""}`}
        maxWidth="max-w-2xl"
      >
        {previewRubric && (
          <div className="space-y-3">
            <p className="text-sm text-[#5C7061]">
              คะแนนรวม: <strong>{previewRubric.allocated_points} / {previewRubric.total_points}</strong> (เวอร์ชัน{" "}
              {previewRubric.current_version})
            </p>
            <div className="divide-y divide-[#E5F2E1] rounded-2xl border border-[#DCEFD6]">
              {previewRubric.items.map((item, idx) => (
                <div key={idx} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-bold text-[#172B1C]">{item.title}</p>
                    <p className="text-xs text-[#5C7061]">
                      {CATEGORY_LABELS[item.category] || item.category}
                      {item.sheet_name ? ` • แท็บ: ${item.sheet_name}` : ""}
                      {item.target_cell ? ` • เซลล์: ${item.target_cell}` : ""}
                    </p>
                  </div>
                  <Badge tone="mint">{item.max_points} คะแนน</Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
