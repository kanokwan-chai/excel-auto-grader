"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, Code2, FileSpreadsheet, Table2 } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const PIE_COLORS = ["#8B5CF6", "#EC4899", "#10B981", "#38BDF8", "#F59E0B", "#A78BFA", "#FB7185"];

export interface PreviewChart {
  type: "bar" | "line" | "pie" | "area" | string;
  title: string;
  data: { name: string; value: number }[];
}

export interface PreviewCell {
  covered?: boolean;
  coord?: string;
  value?: string;
  formula?: string | null;
  bold?: boolean;
  italic?: boolean;
  bg_color?: string | null;
  font_color?: string | null;
  align?: string;
  has_border?: boolean;
  number_format?: string;
  row_span?: number;
  col_span?: number;
  error_msg?: string | null;
}

export interface PreviewSheet {
  name: string;
  col_headers: string[];
  rows: { row_num: number; cells: PreviewCell[] }[];
  charts: PreviewChart[];
}

export interface ExcelPreviewData {
  filename: string;
  sheet_names: string[];
  sheets: PreviewSheet[];
}

export function ExcelSpreadsheetPreview({
  data,
  focusCell,
}: {
  data: ExcelPreviewData;
  focusCell?: string | null;
}) {
  const [activeSheetIdx, setActiveSheetIdx] = useState(0);
  const [selectedCell, setSelectedCell] = useState<PreviewCell | null>(null);
  const [showFormulasInGrid, setShowFormulasInGrid] = useState(false);

  const sheet = data.sheets[activeSheetIdx] || data.sheets[0];

  useEffect(() => {
    if (!sheet) return;
    if (focusCell) {
      const cleanCoord = focusCell.includes("!") ? focusCell.split("!").pop()?.toUpperCase() : focusCell.toUpperCase();
      for (const row of sheet.rows) {
        const found = row.cells.find((c) => !c.covered && c.coord?.toUpperCase() === cleanCoord);
        if (found) {
          setSelectedCell(found);
          return;
        }
      }
    }
    const firstNonEmpty = sheet.rows
      .flatMap((r) => r.cells)
      .find((c) => !c.covered && (c.formula || c.value));
    setSelectedCell(firstNonEmpty || sheet.rows[0]?.cells[0] || null);
  }, [activeSheetIdx, focusCell, sheet]);

  if (!sheet) {
    return (
      <div className="rounded-2xl border border-violet-100 bg-slate-50 p-6 text-center text-xs text-slate-500">
        ไม่พบข้อมูลแผ่นงานในไฟล์ Excel
      </div>
    );
  }

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-xs">
      {/* Excel Top Title & Formula Mode Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-emerald-700 px-3.5 py-2 text-white">
        <div className="flex items-center gap-2 min-w-0">
          <FileSpreadsheet className="h-4 w-4 shrink-0" />
          <span className="truncate text-xs font-semibold">{data.filename}</span>
          {sheet.charts.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-600 px-2 py-0.5 text-[10px]">
              <BarChart3 className="h-3 w-3" /> {sheet.charts.length} แผนภูมิ
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setShowFormulasInGrid((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
            showFormulasInGrid
              ? "bg-white text-emerald-800"
              : "bg-emerald-600 text-white hover:bg-emerald-500"
          }`}
        >
          {showFormulasInGrid ? <Table2 className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
          {showFormulasInGrid ? "สลับดูค่าผลลัพธ์" : "แสดงสูตรทุกช่อง (=fx)"}
        </button>
      </div>

      {/* Formula Bar (fx) */}
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-1.5 text-xs">
        <div className="w-14 shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-center font-mono font-bold text-slate-800">
          {selectedCell?.coord || "A1"}
        </div>
        <span className="font-serif italic font-bold text-emerald-700 select-none">fx</span>
        <div className="flex-1 truncate rounded border border-slate-200 bg-white px-2.5 py-1 font-mono text-slate-900">
          {selectedCell?.formula ? (
            <span className="text-violet-800 font-semibold">{selectedCell.formula}</span>
          ) : (
            <span>{selectedCell?.value || "(เซลล์ว่าง)"}</span>
          )}
        </div>
        {selectedCell?.formula && (
          <span className="hidden sm:inline-block shrink-0 rounded bg-emerald-50 px-2 py-1 text-[11px] text-emerald-800">
            ค่า: <strong>{selectedCell.value}</strong>
          </span>
        )}
      </div>

      {/* Error Banner for Selected Cell */}
      {selectedCell?.error_msg && (
        <div className="flex items-center gap-2 border-b border-rose-200 bg-rose-50 px-3 py-1.5 text-xs text-rose-800">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-rose-600" />
          <span>
            <strong>ข้อผิดพลาดที่เซลล์ {selectedCell.coord}:</strong> {selectedCell.error_msg}
          </span>
        </div>
      )}

      {/* Interactive Spreadsheet Grid */}
      <div className="max-h-[52vh] overflow-auto bg-slate-100">
        <table className="border-collapse text-xs">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 w-9 border border-slate-300 bg-slate-200 py-1 text-center text-[11px] font-semibold text-slate-600">
                #
              </th>
              {sheet.col_headers.map((col) => (
                <th
                  key={col}
                  className="min-w-[88px] border border-slate-300 bg-slate-100 px-2 py-1 text-center text-[11px] font-semibold text-slate-700"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row) => (
              <tr key={row.row_num}>
                <td className="sticky left-0 z-10 border border-slate-300 bg-slate-100 px-1.5 py-1 text-center text-[11px] font-medium text-slate-600 select-none">
                  {row.row_num}
                </td>
                {row.cells.map((cell, cIdx) => {
                  if (cell.covered) return null;
                  const isSelected = selectedCell?.coord === cell.coord;
                  const display = showFormulasInGrid && cell.formula ? cell.formula : cell.value;

                  return (
                    <td
                      key={cell.coord || cIdx}
                      rowSpan={cell.row_span && cell.row_span > 1 ? cell.row_span : undefined}
                      colSpan={cell.col_span && cell.col_span > 1 ? cell.col_span : undefined}
                      onClick={() => setSelectedCell(cell)}
                      title={cell.error_msg || cell.formula || cell.value || cell.coord}
                      style={{
                        backgroundColor: cell.error_msg
                          ? "#FFE4E6"
                          : cell.bg_color || "#FFFFFF",
                        color: cell.font_color || "#1E293B",
                        textAlign: (cell.align as "left" | "center" | "right") || "left",
                      }}
                      className={`relative cursor-pointer px-2 py-1 whitespace-nowrap max-w-[200px] truncate transition-all ${
                        cell.has_border ? "border border-slate-500" : "border border-slate-200"
                      } ${cell.bold ? "font-bold" : ""} ${cell.italic ? "italic" : ""} ${
                        isSelected ? "outline outline-2 outline-emerald-600 z-10" : ""
                      } ${cell.error_msg ? "ring-1 ring-inset ring-rose-500" : ""}`}
                    >
                      {/* Small green triangle indicator on cells that contain real Excel formulas */}
                      {cell.formula && (
                        <span
                          className="absolute top-0 left-0 h-0 w-0 border-t-[6px] border-r-[6px] border-t-emerald-500 border-r-transparent"
                          title={`สูตร: ${cell.formula}`}
                        />
                      )}
                      {display}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Embedded Charts Preview (if worksheet contains Excel charts) */}
      {sheet.charts && sheet.charts.length > 0 && (
        <div className="border-t border-emerald-100 bg-violet-50/30 p-3 space-y-3">
          <p className="flex items-center gap-1.5 text-xs font-bold text-violet-950">
            <BarChart3 className="h-4 w-4 text-violet-600" />
            แผนภูมิที่ตรวจพบในแผ่นงาน ({sheet.charts.length} แผนภูมิ)
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {sheet.charts.map((ch, chIdx) => (
              <div key={chIdx} className="rounded-xl border border-violet-100 bg-white p-3">
                <p className="mb-2 text-xs font-semibold text-violet-900">
                  {ch.title} <span className="text-[10px] text-slate-400">({ch.type})</span>
                </p>
                {ch.data && ch.data.length > 0 ? (
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      {ch.type === "pie" ? (
                        <PieChart>
                          <Pie data={ch.data} dataKey="value" nameKey="name" outerRadius={62} label>
                            {ch.data.map((_, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      ) : ch.type === "line" ? (
                        <LineChart data={ch.data}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#EDE9FE" />
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip />
                          <Line type="monotone" dataKey="value" stroke="#8B5CF6" strokeWidth={2} />
                        </LineChart>
                      ) : (
                        <BarChart data={ch.data}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#EDE9FE" />
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip />
                          <Bar dataKey="value" fill="#8B5CF6" radius={[6, 6, 0, 0]} />
                        </BarChart>
                      )}
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="py-6 text-center text-[11px] text-slate-400">
                    พบแผนภูมิประเภท {ch.type} (ไม่มีค่าตัวเลขในแคชสำหรับวาดกราฟ)
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Bottom Sheet Tabs (Excel Style) */}
      <div className="flex items-center gap-1 overflow-x-auto border-t border-slate-200 bg-slate-100 px-2 py-1.5">
        {data.sheets.map((sh, idx) => (
          <button
            key={sh.name}
            type="button"
            onClick={() => setActiveSheetIdx(idx)}
            className={`rounded-t-lg border px-3 py-1 text-xs font-medium transition ${
              idx === activeSheetIdx
                ? "border-emerald-500 border-b-white bg-white text-emerald-800 shadow-xs"
                : "border-transparent text-slate-600 hover:bg-slate-200/70"
            }`}
          >
            {sh.name}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-slate-500 px-2">
          มุมเขียว = มีสูตร Excel • สีแดง = เซลล์ที่ถูกหักคะแนน
        </span>
      </div>
    </div>
  );
}
