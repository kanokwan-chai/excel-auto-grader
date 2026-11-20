"""OpenPyXL Workbook Reader for both formulas (data_only=False) and values (data_only=True)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook import Workbook

from excel_engine.exceptions import CorruptedExcelError


@dataclass
class LoadedWorkbooks:
    formula_wb: Workbook
    value_wb: Workbook

    def close(self) -> None:
        try:
            self.formula_wb.close()
        except Exception:
            pass
        try:
            self.value_wb.close()
        except Exception:
            pass


def load_workbooks(
    formula_file_path: str | Path,
    value_file_path: str | Path | None = None,
) -> LoadedWorkbooks:
    """
    Open the Excel workbook for formula inspection (data_only=False)
    and value inspection (data_only=True).
    """
    val_path = value_file_path or formula_file_path
    try:
        formula_wb = openpyxl.load_workbook(
            formula_file_path,
            data_only=False,
            keep_vba=False,
        )
        value_wb = openpyxl.load_workbook(
            val_path,
            data_only=True,
            keep_vba=False,
        )
        return LoadedWorkbooks(formula_wb=formula_wb, value_wb=value_wb)
    except Exception as exc:
        raise CorruptedExcelError(
            f"ไม่สามารถเปิดอ่านไฟล์ Excel ได้ (ไฟล์อาจเสียหายหรือติดรหัสผ่าน): {exc}"
        ) from exc


def extract_workbook_metadata(file_path: str | Path) -> dict[str, Any]:
    """Inspect a reference or student workbook and return sheets, formulas, tables, charts."""
    loaded = load_workbooks(file_path)
    try:
        sheets_info: list[dict[str, Any]] = []
        for sheet_name in loaded.formula_wb.sheetnames:
            f_ws = loaded.formula_wb[sheet_name]
            v_ws = loaded.value_wb[sheet_name]

            formulas: list[dict[str, Any]] = []
            headers: list[dict[str, Any]] = []

            for row_idx in range(1, min(f_ws.max_row or 0, 500) + 1):
                for col_idx in range(1, min(f_ws.max_column or 0, 50) + 1):
                    cell = f_ws.cell(row=row_idx, column=col_idx)
                    val_cell = v_ws.cell(row=row_idx, column=col_idx)
                    if row_idx == 1 and cell.value is not None:
                        headers.append({"cell": cell.coordinate, "value": str(cell.value)})
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        formulas.append(
                            {
                                "cell": cell.coordinate,
                                "formula": cell.value,
                                "cached_value": val_cell.value,
                            }
                        )

            charts = [
                {
                    "type": type(ch).__name__,
                    "title": _extract_chart_title_simple(ch),
                }
                for ch in getattr(f_ws, "_charts", [])
            ]

            sheets_info.append(
                {
                    "name": sheet_name,
                    "sheet_state": f_ws.sheet_state,
                    "max_row": f_ws.max_row,
                    "max_column": f_ws.max_column,
                    "headers": headers,
                    "formula_count": len(formulas),
                    "formulas": formulas[:200],
                    "tables": list(f_ws.tables.keys()) if hasattr(f_ws, "tables") else [],
                    "charts": charts,
                    "merged_cells": [str(rng) for rng in f_ws.merged_cells.ranges],
                }
            )

        return {
            "sheet_count": len(loaded.formula_wb.sheetnames),
            "sheet_names": list(loaded.formula_wb.sheetnames),
            "sheets": sheets_info,
        }
    finally:
        loaded.close()


def _extract_chart_title_simple(chart: Any) -> str | None:
    title = getattr(chart, "title", None)
    if title is None:
        return None
    if isinstance(title, str):
        return title
    tx = getattr(title, "tx", None)
    if tx and getattr(tx, "rich", None):
        parts: list[str] = []
        for p in tx.rich.p or []:
            for r in p.r or []:
                if getattr(r, "t", None):
                    parts.append(r.t)
        if parts:
            return "".join(parts)
    return None
