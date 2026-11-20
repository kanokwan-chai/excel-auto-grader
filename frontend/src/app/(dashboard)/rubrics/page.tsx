"use client";

import React, { useEffect, useState } from "react";
import { ClipboardCopy, ClipboardPaste, Copy, Eye, FileSpreadsheet, Pencil, Plus, Scale, Sparkles, Trash2, Upload } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { AssignmentItem, Rubric, RubricItem } from "@/types";
import { useToast } from "@/components/ui/toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  Modal,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";

const CATEGORY_LABELS: Record<string, string> = {
  formula: "A. ตรวจสูตร Excel",
  value: "B. ตรวจผลลัพธ์",
  position: "C. ตรวจตำแหน่งเซลล์",
  style: "D. ตรวจรูปแบบเซลล์",
  structure: "E. ตรวจโครงสร้าง Worksheet",
  chart: "F. ตรวจแผนภูมิ",
  completeness: "G. ตรวจความครบถ้วน",
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

/**
 * Parse pasted rubric text from:
 * 1) JSON exported/copied from another rubric
 * 2) Pipe-separated or Tab-separated (copied from Excel / Word / ChatGPT):
 *    - 6 cols: ชื่อเกณฑ์ | category | sheet | cell | formula/expected | points
 *    - 2 cols: ชื่อเกณฑ์ | points
 */
function parsePastedRubricText(raw: string): { items: RubricItem[]; totalPoints?: number; name?: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { items: [] };

  // 1. Try JSON first
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      const arr = Array.isArray(parsed) ? parsed : parsed.items;
      if (Array.isArray(arr)) {
        const mapped: RubricItem[] = arr.map((it: Partial<RubricItem>, idx: number) => ({
          order_index: idx,
          title: String(it.title || `เกณฑ์ข้อที่ ${idx + 1}`),
          category: VALID_CATEGORIES.has(String(it.category)) ? String(it.category) : "formula",
          sheet_name: it.sheet_name || "Scores",
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

  // 2. Line-by-line parser (Tab or | separated)
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

    // Skip header row like "รายการตรวจ | คะแนน"
    if (parts[0].includes("รายการ") && (parts[parts.length - 1].includes("คะแนน") || parts[1].includes("คะแนน"))) {
      continue;
    }

    const lastNum = parseFloat(parts[parts.length - 1]);
    const points = Number.isFinite(lastNum) ? lastNum : 2;
    const title = parts[0].replace(/^[-•*\d.)\s]+/, "").trim() || parts[0];

    let category = "formula";
    let sheet_name = "Scores";
    let target_cell = "";
    let rule_config: Record<string, unknown> = {};

    if (parts.length >= 6) {
      category = VALID_CATEGORIES.has(parts[1].toLowerCase()) ? parts[1].toLowerCase() : "formula";
      sheet_name = parts[2] || "Scores";
      target_cell = parts[3] || "";
      const expected = parts[4] || "";
      if (category === "formula") rule_config = { expected_formula: expected };
      else if (category === "style") rule_config = { number_format: expected };
      else if (category === "chart") rule_config = { chart_type: expected };
      else rule_config = { expected_value: expected };
    } else if (parts.length >= 3) {
      const maybeCat = parts[1].toLowerCase();
      if (VALID_CATEGORIES.has(maybeCat)) category = maybeCat;
      if (parts.length >= 4 && parts[2].startsWith("=")) {
        rule_config = { expected_formula: parts[2] };
      }
    } else {
      // Infer category from Thai title keywords
      const t = title.toLowerCase();
      if (t.includes("แผนภูมิ") || t.includes("กราฟ") || t.includes("chart")) category = "chart";
      else if (t.includes("รูปแบบ") || t.includes("ตาราง") || t.includes("สี") || t.includes("ฟอนต์")) category = "style";
      else if (t.includes("ตำแหน่ง")) category = "position";
      else if (t.includes("ผลลัพธ์")) category = "value";
      else if (t.includes("sheet") || t.includes("แผ่นงาน")) category = "structure";
      else category = "formula";
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
  const [name, setName] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [totalPoints, setTotalPoints] = useState("20");
  const [items, setItems] = useState<RubricItem[]>([makeEmptyItem(0)]);
  const [saving, setSaving] = useState(false);

  // Paste, Free-form Expander, Custom Formulas & Sample Excel states
  const [showPasteBox, setShowPasteBox] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [freeformText, setFreeformText] = useState("");
  const [expanding, setExpanding] = useState(false);
  const [customFormulaInput, setCustomFormulaInput] = useState("");
  const [extraFormulas, setExtraFormulas] = useState<string[]>([]);
  const [sampleUploading, setSampleUploading] = useState(false);
  const [sampleInfo, setSampleInfo] = useState<{
    filename: string;
    sheet_names: string[];
    formula_count: number;
    sheet_metadata: Record<string, unknown>;
    suggested_items: RubricItem[];
  } | null>(null);

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

  const allocated = items.filter((i) => i.is_enabled).reduce((sum, i) => sum + Number(i.max_points || 0), 0);
  const exceeds = allocated > Number(totalPoints || 0);

  const updateItem = (index: number, patch: Partial<RubricItem>) => {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  };

  const toggleFormulaPreset = (funcName: string) => {
    const clean = funcName.trim().toUpperCase();
    if (!clean) return;
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
        description: `ระบบตรวจอัตโนมัติเทียบไฟล์ตัวอย่าง: ฟังก์ชัน ${clean}`,
        category: "formula",
        sheet_name: "",
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
    const alreadyInItems = items.some(
      (it) =>
        it.category === "formula" &&
        Array.isArray(it.rule_config.required_functions) &&
        (it.rule_config.required_functions as string[]).includes(clean)
    );
    if (!alreadyInItems) {
      toggleFormulaPreset(clean);
    }
    setCustomFormulaInput("");
    toast(`เพิ่มสูตร ${clean} เข้าในเกณฑ์แล้ว`);
  };

  const handleAutoDistributePoints = () => {
    const total = Number(totalPoints || 0);
    const enabledIndices = items.map((it, idx) => (it.is_enabled ? idx : -1)).filter((i) => i >= 0);
    if (total <= 0 || enabledIndices.length === 0) {
      toast("กรุณากรอกคะแนนรวมและมีข้อเกณฑ์อย่างน้อย 1 ข้อ", "error");
      return;
    }
    const base = Math.floor((total / enabledIndices.length) * 100) / 100;
    let running = 0;
    setItems((prev) =>
      prev.map((it, idx) => {
        if (!it.is_enabled) return it;
        const pos = enabledIndices.indexOf(idx);
        const pts =
          pos === enabledIndices.length - 1
            ? Math.round((total - running) * 100) / 100
            : base;
        running = Math.round((running + pts) * 100) / 100;
        return { ...it, max_points: pts };
      })
    );
    toast(`เฉลี่ยคะแนนรวม ${total} คะแนน ให้ทั้ง ${enabledIndices.length} ข้อเรียบร้อยแล้ว`);
  };

  const handleApplyPaste = () => {
    const parsed = parsePastedRubricText(pasteText);
    if (parsed.items.length === 0) {
      toast("ไม่พบรายการเกณฑ์ในข้อความที่วาง ลองวางในรูปแบบ 'ชื่อเกณฑ์ | คะแนน' หรือคัดลอกจากตาราง Excel", "error");
      return;
    }
    setItems(parsed.items);
    const sumPts = parsed.items.reduce((s, it) => s + Number(it.max_points || 0), 0);
    if (parsed.totalPoints) setTotalPoints(String(parsed.totalPoints));
    else if (sumPts > Number(totalPoints || 0)) setTotalPoints(String(sumPts));
    if (parsed.name && !name) setName(parsed.name);
    setShowPasteBox(false);
    setPasteText("");
    toast(`นำเข้าเกณฑ์จากการวางสำเร็จ ${parsed.items.length} ข้อ`);
  };

  const handleSampleFileUpload = async (file: File | null) => {
    if (!file) return;
    setSampleUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (assignmentId) fd.append("assignment_id", assignmentId);
      const res = await apiRequest<{
        filename: string;
        sheet_metadata: { sheet_names: string[]; sheets: { formula_count: number }[] };
        suggested_items: RubricItem[];
      }>("/rubrics/inspect-sample", { method: "POST", body: fd });

      const formulaTotal = (res.sheet_metadata.sheets || []).reduce((s, sh) => s + (sh.formula_count || 0), 0);
      setSampleInfo({
        filename: res.filename,
        sheet_names: res.sheet_metadata.sheet_names || [],
        formula_count: formulaTotal,
        sheet_metadata: res.sheet_metadata as unknown as Record<string, unknown>,
        suggested_items: res.suggested_items || [],
      });
      toast(`วิเคราะห์ไฟล์ตัวอย่าง "${res.filename}" สำเร็จ พบ ${formulaTotal} สูตร`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "ไม่สามารถอ่านไฟล์ตัวอย่างได้", "error");
    } finally {
      setSampleUploading(false);
    }
  };

  const handleExpandFreeform = async () => {
    if (!freeformText.trim()) {
      toast("กรุณาพิมพ์รายละเอียดเกณฑ์แบบรวม ๆ ก่อนครับ", "error");
      return;
    }
    setExpanding(true);
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
      toast(err instanceof Error ? err.message : "ไม่สามารถขยายความเกณฑ์ได้", "error");
    } finally {
      setExpanding(false);
    }
  };

  const handleUseSuggestedItems = () => {
    if (!sampleInfo || sampleInfo.suggested_items.length === 0) return;
    setItems(sampleInfo.suggested_items);
    const sumPts = sampleInfo.suggested_items.reduce((s, it) => s + Number(it.max_points || 0), 0);
    if (sumPts > Number(totalPoints || 0)) setTotalPoints(String(sumPts));
    toast(`ดึงข้อเกณฑ์จากไฟล์ตัวอย่างแล้ว ${sampleInfo.suggested_items.length} ข้อ`);
  };

  const handleCopyRubricClipboard = async (r: Rubric) => {
    const payload = JSON.stringify(
      { name: r.name, total_points: r.total_points, items: r.items },
      null,
      2
    );
    try {
      await navigator.clipboard.writeText(payload);
      toast(`คัดลอกเกณฑ์ "${r.name}" ลงคลิปบอร์ดแล้ว (นำไปวางในหน้าสร้างเกณฑ์ได้เลย)`);
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
    setFreeformText("");
    setShowPasteBox(false);
    setOpenBuilder(true);
  };

  const openEditModal = (r: Rubric) => {
    setEditingRubricId(r.id);
    setName(r.name);
    setAssignmentId(r.assignment_id || "");
    setTotalPoints(String(r.total_points));
    setItems(
      r.items.length > 0
        ? r.items.map((it, idx) => ({ ...it, order_index: idx }))
        : [makeEmptyItem(0)]
    );
    setSampleInfo(null);
    setFreeformText("");
    setShowPasteBox(false);
    setOpenBuilder(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (exceeds) {
      toast("คะแนนรวมของเกณฑ์ย่อยเกินคะแนนเต็มที่กำหนด", "error");
      return;
    }
    setSaving(true);
    try {
      const endpoint = editingRubricId ? `/rubrics/${editingRubricId}` : "/rubrics";
      const method = editingRubricId ? "PUT" : "POST";
      await apiRequest(endpoint, {
        method,
        body: JSON.stringify({
          name,
          assignment_id: assignmentId || null,
          total_points: Number(totalPoints),
          items,
          change_note: editingRubricId ? "แก้ไขเกณฑ์การตรวจ" : "สร้างชุดเกณฑ์ใหม่",
        }),
      });
      toast(
        editingRubricId
          ? "บันทึกการแก้ไขเกณฑ์และอัปเดตเวอร์ชันใหม่เรียบร้อยแล้ว"
          : "บันทึกเกณฑ์การตรวจพร้อมสร้างเวอร์ชันใหม่สำเร็จ"
      );
      setOpenBuilder(false);
      setEditingRubricId(null);
      setName("");
      setSampleInfo(null);
      setItems([makeEmptyItem(0)]);
      load();
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
        <div>
          <h1 className="text-2xl font-bold text-violet-950">เกณฑ์การตรวจ (Rubric Builder)</h1>
          <p className="text-sm text-slate-500">
            คัดลอก-วางเกณฑ์จากข้อความ/Excel ได้ทันที และแนบไฟล์ตัวอย่าง Excel เพื่อดึงสูตรเฉลยอัตโนมัติ
          </p>
        </div>
        <Button onClick={openCreateModal}>
          <Plus className="h-4 w-4" /> สร้างชุดเกณฑ์ใหม่
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <Skeleton className="h-56" />
      ) : rubrics.length === 0 ? (
        <EmptyState
          title="ยังไม่มีชุดเกณฑ์การตรวจ"
          description="สร้างชุดเกณฑ์ใหม่ด้วยการพิมพ์เอง คัดลอก-วางข้อความ หรือแนบไฟล์ตัวอย่าง Excel"
          action={<Button onClick={() => setOpenBuilder(true)}>สร้างเกณฑ์แรก</Button>}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rubrics.map((r) => (
            <Card key={r.id} className="space-y-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-fuchsia-100 text-fuchsia-700">
                    <Scale className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-violet-950">{r.name}</h3>
                    <p className="text-xs text-slate-500">
                      เวอร์ชัน {r.current_version} • {r.items.length} รายการตรวจ
                    </p>
                  </div>
                </div>
                <Badge tone="lavender">
                  {r.allocated_points}/{r.total_points} คะแนน
                </Badge>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {r.items.slice(0, 5).map((i, idx) => (
                  <Badge key={idx} tone="sky">
                    {i.title} ({i.max_points})
                  </Badge>
                ))}
              </div>

              <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-violet-50">
                <Button size="sm" variant="primary" onClick={() => openEditModal(r)}>
                  <Pencil className="h-3.5 w-3.5" /> แก้ไขเกณฑ์
                </Button>
                <Button size="sm" variant="outline" onClick={() => setPreviewRubric(r)}>
                  <Eye className="h-3.5 w-3.5" /> ดูตัวอย่าง
                </Button>
                <Button size="sm" variant="secondary" onClick={() => handleCopyRubricClipboard(r)}>
                  <ClipboardCopy className="h-3.5 w-3.5" /> คัดลอกเกณฑ์
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

      {/* Rubric Builder Modal (Create / Edit) */}
      <Modal
        open={openBuilder}
        onClose={() => {
          setOpenBuilder(false);
          setEditingRubricId(null);
        }}
        title={editingRubricId ? "แก้ไขชุดเกณฑ์การตรวจ (บันทึกเป็นเวอร์ชันใหม่)" : "สร้างชุดเกณฑ์การตรวจ (Rubric Builder)"}
        maxWidth="max-w-4xl"
      >
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-semibold">ชื่อชุดเกณฑ์ *</label>
              <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="เกณฑ์ตรวจใบงาน Excel บทที่ 1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold">คะแนนเต็ม *</label>
              <Input type="number" step="0.5" required value={totalPoints} onChange={(e) => setTotalPoints(e.target.value)} />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold">ผูกกับงาน (ไม่บังคับ — หากเลือก ระบบจะบันทึกไฟล์ตัวอย่างเป็นไฟล์เฉลยของงานนี้ให้ด้วย)</label>
            <Select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}>
              <option value="">-- ใช้เป็นเกณฑ์กลาง --</option>
              {assignments.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
            </Select>
          </div>

          {/* Sample Excel File Attachment Box */}
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-emerald-900">
                <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
                <span className="text-xs font-bold">แนบไฟล์ตัวอย่าง Excel เฉลยต้นฉบับ (.xlsx / .xls / .xlsm)</span>
              </div>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700">
                <Upload className="h-3.5 w-3.5" />
                {sampleUploading ? "กำลังวิเคราะห์ไฟล์..." : "เลือกไฟล์ตัวอย่าง"}
                <input
                  type="file"
                  accept=".xlsx,.xls,.xlsm"
                  className="hidden"
                  disabled={sampleUploading}
                  onChange={(e) => handleSampleFileUpload(e.target.files?.[0] || null)}
                />
              </label>
            </div>
            {sampleInfo ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white px-3 py-2 text-xs border border-emerald-100">
                <div>
                  <p className="font-semibold text-emerald-950">ไฟล์ตัวอย่าง: {sampleInfo.filename}</p>
                  <p className="text-slate-500">
                    Sheet: {sampleInfo.sheet_names.join(", ") || "-"} • พบสูตรทั้งหมด {sampleInfo.formula_count} สูตร
                  </p>
                </div>
                {sampleInfo.suggested_items.length > 0 && (
                  <Button type="button" size="sm" variant="mint" onClick={handleUseSuggestedItems}>
                    <Sparkles className="h-3.5 w-3.5" /> ดึงเป็นข้อเกณฑ์อัตโนมัติ ({sampleInfo.suggested_items.length} ข้อ)
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-xs text-emerald-800/80">
                อัปโหลดไฟล์ Excel เฉลยที่ทำเสร็จแล้ว เพื่อให้ระบบดึงชื่อ Sheet, เซลล์ และสูตรมาสร้างเกณฑ์ให้อัตโนมัติ
              </p>
            )}
          </div>

          {/* Smart Free-Form Rubric Expander Box */}
          <div className="rounded-2xl border border-violet-200 bg-gradient-to-r from-violet-50/80 to-pink-50/70 p-4 space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-bold text-violet-950">
                <Sparkles className="h-4 w-4 text-violet-600" />
                พิมพ์เกณฑ์แบบภาษาพูดรวม ๆ แล้วให้ระบบขยายความเป็นข้อเกณฑ์ให้อัตโนมัติ
              </p>
            </div>
            <Textarea
              rows={3}
              value={freeformText}
              onChange={(e) => setFreeformText(e.target.value)}
              placeholder="พิมพ์รวม ๆ ได้เลย เช่น: งานนี้เต็ม 20 คะแนน ตรวจสูตร SUM หาผลรวม, AVERAGE ค่าเฉลี่ย, IF ตัดเกรดผ่านไม่ผ่าน, ใส่เส้นขอบตาราง ตัวหนาหัวตาราง ทศนิยม 2 ตำแหน่ง แล้วก็ทำกราฟแท่ง 1 อัน"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-slate-500">
                เคล็ดลับ: หากแนบไฟล์ตัวอย่าง Excel ด้านบนด้วย ระบบจะจับคู่ชื่อ Sheet, เซลล์ และสูตรจากไฟล์ตัวอย่างให้เอง
              </p>
              <Button type="button" size="sm" loading={expanding} onClick={handleExpandFreeform}>
                <Sparkles className="h-3.5 w-3.5" /> ขยายความเป็นเกณฑ์ตรวจอัตโนมัติ
              </Button>
            </div>
          </div>

          {/* Quick Formula Checklist + Custom Formula Adder */}
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-3.5 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-bold text-indigo-950">
                ติ๊กเลือกสูตร Excel ที่ต้องการตรวจ (ไม่ต้องระบุเซลล์ ระบบจะไปสแกนเทียบไฟล์ตัวอย่างให้อัตโนมัติ)
              </p>
            </div>
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
                    className={`inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs font-semibold transition ${
                      checked
                        ? "border-violet-600 bg-violet-600 text-white shadow-xs"
                        : "border-violet-200 bg-white text-violet-900 hover:bg-violet-50"
                    }`}
                  >
                    <span>{checked ? "✓" : "+"}</span>
                    <span>{fn}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex gap-2 pt-1">
              <Input
                value={customFormulaInput}
                onChange={(e) => setCustomFormulaInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddCustomFormula();
                  }
                }}
                placeholder="พิมพ์ชื่อสูตรเพิ่มเติมเอง เช่น PMT, STDEV, MEDIAN, PROPER..."
                className="h-9 text-xs"
              />
              <Button type="button" size="sm" variant="secondary" onClick={handleAddCustomFormula}>
                <Plus className="h-3.5 w-3.5" /> เพิ่มสูตรเอง
              </Button>
            </div>
          </div>

          {/* Toolbar: Budget + Auto-Distribute + Paste Rubric + Add Item */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-violet-50 px-4 py-2.5 text-xs">
            <span>
              จัดสรรคะแนนแล้ว: <strong className={exceeds ? "text-rose-600" : "text-violet-900"}>{allocated}</strong> / {totalPoints} คะแนน
            </span>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  setItems((prev) => [
                    ...(prev.length === 1 && !prev[0].title.trim() ? [] : prev),
                    {
                      order_index: prev.length,
                      title: "ความสวยงามและการตกแต่ง (เส้นและรูปแบบเหมือนต้นฉบับ เลือกสีเองได้)",
                      description: "ตรวจเส้นขอบ ตัวหนา ผสานเซลล์ รูปแบบตัวเลขเทียบต้นฉบับ แต่ไม่บังคับสีให้เหมือนต้นฉบับ",
                      category: "style",
                      sheet_name: "",
                      target_cell: "",
                      rule_config: {
                        match_reference_layout_ignore_color: true,
                        bold: true,
                        has_border: true,
                        has_fill_color: true,
                      },
                      max_points: 2,
                      min_points: 0,
                      allow_partial_credit: true,
                      weight_importance: "normal",
                      zero_on_error: false,
                      is_enabled: true,
                    },
                  ])
                }
              >
                <Sparkles className="h-3.5 w-3.5" /> + ความสวยงาม (เลือกสีเองได้)
              </Button>
              <Button type="button" size="sm" variant="mint" onClick={handleAutoDistributePoints}>
                <Sparkles className="h-3.5 w-3.5" /> เฉลี่ยคะแนนให้เอง
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setShowPasteBox(!showPasteBox)}>
                <ClipboardPaste className="h-3.5 w-3.5" /> วางเกณฑ์ (Copy-Paste)
              </Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => setItems([...items, makeEmptyItem(items.length)])}>
                <Plus className="h-3.5 w-3.5" /> เพิ่มข้อเกณฑ์
              </Button>
            </div>
          </div>

          {/* Paste Rubric Drawer */}
          {showPasteBox && (
            <div className="rounded-2xl border border-sky-200 bg-sky-50/50 p-4 space-y-2.5">
              <p className="text-xs font-bold text-sky-950">วางเกณฑ์จากคลิปบอร์ด (รองรับตาราง Excel, ข้อความ `|` หรือ JSON จากปุ่มคัดลอกเกณฑ์)</p>
              <Textarea
                rows={5}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder={`ตัวอย่างแบบสั้น (รายการ | คะแนน):\nสูตร SUM | 3\nสูตร AVERAGE | 3\nสูตร IF | 4\nแผนภูมิ | 2\n\nหรือแบบละเอียด (ชื่อ | หมวด | Sheet | เซลล์ | สูตร | คะแนน):\nสูตร SUM | formula | Scores | B6 | =SUM(B2:B5) | 3`}
              />
              <div className="flex justify-end gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => setShowPasteBox(false)}>ปิด</Button>
                <Button type="button" size="sm" onClick={handleApplyPaste}>นำเข้าเกณฑ์ที่วาง</Button>
              </div>
            </div>
          )}

          {/* Rubric Items Editor (Clean Mode — Auto-Matches Sample File without requiring Cell/Sheet/Formula input) */}
          <div className="space-y-3 max-h-[38vh] overflow-y-auto pr-1">
            {items.map((it, idx) => (
              <div key={idx} className="rounded-2xl border border-violet-100 bg-white p-3.5 space-y-2">
                <div className="grid gap-2 sm:grid-cols-4">
                  <Input
                    required
                    placeholder="ชื่อรายการตรวจ เช่น ตรวจสูตร SUM"
                    value={it.title}
                    onChange={(e) => updateItem(idx, { title: e.target.value })}
                    className="sm:col-span-2"
                  />
                  <Select value={it.category} onChange={(e) => updateItem(idx, { category: e.target.value })}>
                    {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </Select>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="คะแนน"
                    value={it.max_points}
                    onChange={(e) => updateItem(idx, { max_points: Number(e.target.value) })}
                  />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
                  <div className="flex flex-wrap items-center gap-4">
                    <span className="rounded-lg bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                      ตรวจอัตโนมัติเทียบไฟล์ตัวอย่าง
                    </span>
                    <label className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={it.allow_partial_credit}
                        onChange={(e) => updateItem(idx, { allow_partial_credit: e.target.checked })}
                      />
                      ให้คะแนนบางส่วน
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
                      onClick={() => setItems(items.filter((_, i) => i !== idx))}
                      className="text-rose-500 hover:underline"
                    >
                      ลบข้อนี้
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-2 pt-2">
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
            <Button type="submit" loading={saving} disabled={exceeds}>
              {editingRubricId ? "บันทึกการแก้ไขเกณฑ์" : "บันทึกชุดเกณฑ์"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Preview Modal */}
      <Modal open={Boolean(previewRubric)} onClose={() => setPreviewRubric(null)} title={`ตัวอย่างเกณฑ์: ${previewRubric?.name || ""}`} maxWidth="max-w-2xl">
        {previewRubric && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              คะแนนรวม: <strong>{previewRubric.allocated_points} / {previewRubric.total_points}</strong> (เวอร์ชัน {previewRubric.current_version})
            </p>
            <div className="divide-y divide-violet-100 rounded-2xl border border-violet-100">
              {previewRubric.items.map((item, idx) => (
                <div key={idx} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-semibold text-violet-950">{item.title}</p>
                    <p className="text-xs text-slate-500">
                      {CATEGORY_LABELS[item.category] || item.category} • Sheet: {item.sheet_name || "-"} • เซลล์: {item.target_cell || "-"}
                    </p>
                  </div>
                  <Badge tone="lavender">{item.max_points} คะแนน</Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
