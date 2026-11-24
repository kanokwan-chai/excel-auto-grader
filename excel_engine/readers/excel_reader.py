"""OpenPyXL Workbook Reader for both formulas (data_only=False) and values (data_only=True)."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook

from excel_engine.exceptions import CorruptedExcelError
from excel_engine.formula_checker.normalizer import analyze_formula


def resolve_worksheet_forgiving(
    wb: Workbook,
    requested_name: str | None,
    reference_wb: Workbook | None = None,
) -> tuple[Any | None, str]:
    """
    Forgiving worksheet resolver for student workbooks.
    Handles common Thai/English student typos ('ขแ5' for 'ข้อ 5', 'คะเเนน' for 'คะแนน',
    extra spaces/dots, default 'Sheet1' on single-sheet workbooks, or matching tab position).
    Returns (worksheet_or_None, resolved_sheet_name).
    """
    import difflib
    import unicodedata

    names = list(wb.sheetnames)
    if not names:
        return None, requested_name or ""

    # 1) If workbook has only 1 sheet, always forgive sheet naming!
    if len(names) == 1:
        return wb[names[0]], names[0]

    if not requested_name or not requested_name.strip():
        return wb[names[0]], names[0]

    req = requested_name.strip()
    if req in wb.sheetnames:
        return wb[req], req

    # Explicit physical tab position syntax: 'แท็บ 2', 'แท็บที่ 2', 'แผ่นที่ 2', 'Tab 2' -> 2nd tab (index 1)
    m_pos = re.match(r"^(?:แท็บ(?:ที่)?|แผ่น(?:งาน)?ที่|tab)\s*(\d+)$", req, re.IGNORECASE)
    if m_pos:
        pos_idx = int(m_pos.group(1)) - 1
        if 0 <= pos_idx < len(names):
            return wb[names[pos_idx]], names[pos_idx]

    def _norm_th(s: str) -> str:
        t = unicodedata.normalize("NFC", s).replace("เเ", "แ")
        t = re.sub(r"[\s._\-()/:]+", "", t).lower()
        return t

    norm_req = _norm_th(req)
    # 2) Normalized exact / substring match
    for n in names:
        if _norm_th(n) == norm_req:
            return wb[n], n
    for n in names:
        nn = _norm_th(n)
        if norm_req and nn and (norm_req in nn or nn in norm_req):
            return wb[n], n

    # 3) Exercise/Tab number match: e.g. 'ข้อที่ 5' matches 'ขแ5', 'ขเอ 5', 'ขอ5', '5', 'Sheet5'
    nums = re.findall(r"\d+", req)
    if nums:
        target_num = nums[-1]
        num_candidates = [
            n for n in names if re.search(rf"(?<!\d){re.escape(target_num)}(?!\d)", n)
        ]
        if len(num_candidates) == 1:
            return wb[num_candidates[0]], num_candidates[0]
        if len(num_candidates) > 1:
            best_c = max(
                num_candidates,
                key=lambda cand: difflib.SequenceMatcher(None, norm_req, _norm_th(cand)).ratio(),
            )
            return wb[best_c], best_c

    # 4) Same tab position as reference workbook when sheet counts match
    if reference_wb is not None and req in reference_wb.sheetnames:
        ref_idx = list(reference_wb.sheetnames).index(req)
        if len(names) == len(reference_wb.sheetnames) and 0 <= ref_idx < len(names):
            return wb[names[ref_idx]], names[ref_idx]

    # 5) Fuzzy string similarity for general Thai/English typos (e.g. 'สรุปผบ' vs 'สรุปผล')
    best_name = None
    best_score = 0.0
    for n in names:
        score = difflib.SequenceMatcher(None, norm_req, _norm_th(n)).ratio()
        if score > best_score:
            best_score = score
            best_name = n
    if best_name and best_score >= 0.48:
        return wb[best_name], best_name

    # 6) Number-to-tab-order fallback (e.g. 'ข้อ 3' -> 3rd tab)
    if nums:
        idx = int(nums[-1]) - 1
        if 0 <= idx < len(names):
            return wb[names[idx]], names[idx]

    return None, req


@dataclass
class LoadedWorkbooks:
    formula_wb: Workbook
    value_wb: Workbook

    def close(self) -> None:
        try:
            self.formula_wb.close()
        except Exception:
            pass
        if self.value_wb is not self.formula_wb:
            try:
                self.value_wb.close()
            except Exception:
                pass


_BLOATED_SHEET_XML_BYTES = 1_500_000  # 1.5 MB uncompressed sheet XML -> student formatted 100k+ empty rows
_BLOATED_MEDIA_BYTES = 2_000_000      # 2 MB embedded image inside xlsx
_MAX_SANITIZED_ROW = 1500
_RE_DIMENSION_TAG = re.compile(rb"<(?:[A-Za-z0-9_]+:)?dimension\b[^>]*/>")
_RE_SHEETDATA_OPEN = re.compile(rb"<(?:[A-Za-z0-9_]+:)?sheetData(?:\s[^>]*)?>")
_RE_SHEETDATA_CLOSE = re.compile(rb"</(?:[A-Za-z0-9_]+:)?sheetData>")
_RE_ROW_OPEN = re.compile(rb"<(?:[A-Za-z0-9_]+:)?row\b")
_RE_ROW_NUM = re.compile(rb'\br="(\d+)"')
_RE_EMPTY_FAR_CELL = re.compile(rb'<c\s+r="[A-Z]{2,}\d+"[^>]*/>')


def _trim_bloated_sheet_xml(raw_stream: Any, max_row: int = _MAX_SANITIZED_ROW) -> bytes:
    """
    Stream-filter a bloated worksheet XML (e.g. 50 MB+ from Ctrl+A formatting 1,048,576 empty rows)
    keeping all rows <= max_row AND preserving 100% of <autoFilter>, <mergeCells>, <drawing> (charts), etc.
    Uses tiny RAM so Render 512MB never OOM-kills openpyxl.
    """
    out = bytearray()
    buf = b""
    state = "BEFORE"  # BEFORE -> IN_DATA -> AFTER
    eof = False

    def _refill() -> bool:
        nonlocal buf, eof
        if eof:
            return False
        chunk = raw_stream.read(262144)
        if not chunk:
            eof = True
            return False
        buf += chunk
        return True

    while True:
        if state == "BEFORE":
            m_open = _RE_SHEETDATA_OPEN.search(buf)
            if not m_open:
                if _refill():
                    continue
                out.extend(_RE_DIMENSION_TAG.sub(b"", buf))
                break
            prefix = _RE_DIMENSION_TAG.sub(b"", buf[: m_open.end()])
            out.extend(prefix)
            buf = buf[m_open.end() :]
            if m_open.group(0).endswith(b"/>"):
                state = "AFTER"
            else:
                state = "IN_DATA"
            continue

        if state == "IN_DATA":
            # Look for either next <row or </sheetData>
            m_close = _RE_SHEETDATA_CLOSE.search(buf)
            m_row = _RE_ROW_OPEN.search(buf)

            if m_close and (not m_row or m_close.start() < m_row.start()):
                out.extend(buf[: m_close.end()])
                buf = buf[m_close.end() :]
                state = "AFTER"
                continue

            if not m_row:
                if _refill():
                    continue
                out.extend(buf)
                break

            # Discard whitespace/junk before <row if any, keep from m_row.start()
            if m_row.start() > 0:
                buf = buf[m_row.start() :]

            gt_pos = buf.find(b">")
            while gt_pos == -1:
                if not _refill():
                    break
                gt_pos = buf.find(b">")
            if gt_pos == -1:
                break

            open_tag = buf[: gt_pos + 1]
            is_self_closing = open_tag.endswith(b"/>")

            if is_self_closing:
                row_end = gt_pos + 1
            else:
                # Find matching closing </row> (or </x:row>)
                close_pos = buf.find(b"</row>", gt_pos + 1)
                close_len = 6
                if close_pos == -1:
                    m_xclose = re.search(rb"</[A-Za-z0-9_]+:row>", buf[gt_pos + 1 :])
                    if m_xclose:
                        close_pos = gt_pos + 1 + m_xclose.start()
                        close_len = m_xclose.end() - m_xclose.start()
                while close_pos == -1:
                    if not _refill():
                        break
                    close_pos = buf.find(b"</row>", gt_pos + 1)
                    close_len = 6
                    if close_pos == -1:
                        m_xclose = re.search(rb"</[A-Za-z0-9_]+:row>", buf[gt_pos + 1 :])
                        if m_xclose:
                            close_pos = gt_pos + 1 + m_xclose.start()
                            close_len = m_xclose.end() - m_xclose.start()
                if close_pos == -1:
                    break
                row_end = close_pos + close_len

            m_rnum = _RE_ROW_NUM.search(open_tag)
            rnum = int(m_rnum.group(1)) if m_rnum else 0
            if rnum <= max_row:
                row_bytes = buf[:row_end]
                # If a single row is bloated (>15KB from formatting 16,384 empty cols), strip empty far cells
                if len(row_bytes) > 15000:
                    row_bytes = _RE_EMPTY_FAR_CELL.sub(b"", row_bytes)
                out.extend(row_bytes)
            buf = buf[row_end:]
            continue

        # state == "AFTER": stream-copy remaining bytes verbatim (preserves autoFilter, drawings/charts, tables!)
        if buf:
            out.extend(buf)
            buf = b""
        if not _refill():
            break

    return bytes(out)


def _sanitize_bloated_xlsx_if_needed(src_path: str | Path) -> tuple[Path, Path | None]:
    """
    If an .xlsx contains bloated worksheet XML (>1.5 MB uncompressed, e.g. Ctrl+A formatted 1M empty rows)
    or giant embedded photos (>2 MB), produce a lightweight sanitized temp .xlsx so openpyxl never OOMs.
    Returns (path_to_open, temp_path_to_delete_or_None).
    """
    p = Path(src_path)
    if p.suffix.lower() not in {".xlsx", ".xlsm"}:
        return p, None

    try:
        with zipfile.ZipFile(p, "r") as zf:
            infos = zf.infolist()
            needs_trim = any(
                (
                    info.filename.lower().startswith("xl/worksheets/sheet")
                    and info.filename.lower().endswith(".xml")
                    and info.file_size > _BLOATED_SHEET_XML_BYTES
                )
                or (
                    info.filename.lower().startswith("xl/media/")
                    and info.file_size > _BLOATED_MEDIA_BYTES
                )
                for info in infos
            )
            if not needs_trim:
                return p, None

            tmp_fd, tmp_name = tempfile.mkstemp(prefix="eag_trim_", suffix=".xlsx")
            os.close(tmp_fd)
            tmp_path = Path(tmp_name)

            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for info in infos:
                    lname = info.filename.lower()
                    if lname.startswith("xl/media/") and info.file_size > _BLOATED_MEDIA_BYTES:
                        continue
                    if lname.startswith("xl/worksheets/sheet") and lname.endswith(".xml") and info.file_size > _BLOATED_SHEET_XML_BYTES:
                        with zf.open(info, "r") as zstream:
                            trimmed = _trim_bloated_sheet_xml(zstream)
                        zout.writestr(info.filename, trimmed)
                    else:
                        zout.writestr(info.filename, zf.read(info.filename))

            return tmp_path, tmp_path
    except Exception:
        return p, None


def load_workbooks(
    formula_file_path: str | Path,
    value_file_path: str | Path | None = None,
    load_formula: bool = True,
    load_value: bool = True,
) -> LoadedWorkbooks:
    """
    Open the Excel workbook for formula inspection (data_only=False)
    and/or value inspection (data_only=True).
    Automatically stream-trims bloated worksheet XML (e.g. 1M empty formatted rows)
    so openpyxl never OOM-crashes on Render 512MB RAM!
    """
    val_path = value_file_path or formula_file_path
    same_path = str(Path(val_path).resolve()) == str(Path(formula_file_path).resolve())
    tmp_files: list[Path] = []
    try:
        open_f_path, tmp_f = _sanitize_bloated_xlsx_if_needed(formula_file_path)
        if tmp_f:
            tmp_files.append(tmp_f)
        if same_path:
            open_v_path = open_f_path
        else:
            open_v_path, tmp_v = _sanitize_bloated_xlsx_if_needed(val_path)
            if tmp_v:
                tmp_files.append(tmp_v)

        formula_wb: Workbook | None = None
        value_wb: Workbook | None = None

        if load_formula:
            formula_wb = openpyxl.load_workbook(
                open_f_path,
                data_only=False,
                keep_vba=False,
            )
        if load_value:
            value_wb = openpyxl.load_workbook(
                open_v_path,
                data_only=True,
                keep_vba=False,
            )

        if formula_wb is None and value_wb is not None:
            formula_wb = value_wb
        elif value_wb is None and formula_wb is not None:
            value_wb = formula_wb
        elif formula_wb is None and value_wb is None:
            formula_wb = openpyxl.load_workbook(open_f_path, data_only=False, keep_vba=False)
            value_wb = formula_wb

        return LoadedWorkbooks(formula_wb=formula_wb, value_wb=value_wb)
    except Exception as exc:
        raise CorruptedExcelError(
            f"ไม่สามารถเปิดอ่านไฟล์ Excel ได้ (ไฟล์อาจเสียหายหรือติดรหัสผ่าน): {exc}"
        ) from exc
    finally:
        for tf in tmp_files:
            try:
                tf.unlink(missing_ok=True)
            except Exception:
                pass


def extract_workbook_metadata(file_path: str | Path) -> dict[str, Any]:
    """Inspect a reference/answer-key workbook: sheets, headers, grouped formulas, AutoFilter ground-truth, charts."""
    loaded = load_workbooks(file_path)
    try:
        sheets_info: list[dict[str, Any]] = []
        for sheet_name in loaded.formula_wb.sheetnames:
            f_ws = loaded.formula_wb[sheet_name]
            v_ws = loaded.value_wb[sheet_name]

            max_r = min(f_ws.max_row or 0, 500)
            max_c = min(f_ws.max_column or 0, 50)

            # Detect AutoFilter ref (sheet or Table)
            af_ref: str | None = None
            af_obj = getattr(f_ws, "auto_filter", None)
            if af_obj and getattr(af_obj, "ref", None):
                af_ref = str(af_obj.ref)
            elif getattr(f_ws, "tables", None):
                for tbl in f_ws.tables.values():
                    taf = getattr(tbl, "autoFilter", None)
                    if taf and getattr(taf, "ref", None):
                        af_ref = str(taf.ref)
                        break

            # Detect header row (from AutoFilter start row or first row with >=2 cells)
            header_row = 1
            af_end_row: int | None = None
            if af_ref:
                m_af = re.match(r"^[A-Za-z]+(\d+):[A-Za-z]+(\d+)$", af_ref.replace("$", "").strip())
                if m_af:
                    header_row = int(m_af.group(1))
                    if int(m_af.group(2)) > header_row:
                        af_end_row = int(m_af.group(2))
            else:
                for r_try in range(1, min(max_r, 10) + 1):
                    non_empty = [
                        f_ws.cell(row=r_try, column=c_i).value
                        for c_i in range(1, max_c + 1)
                        if f_ws.cell(row=r_try, column=c_i).value is not None
                    ]
                    if len(non_empty) >= 2:
                        header_row = r_try
                        break

            headers: list[dict[str, Any]] = []
            header_map_by_col: dict[int, str] = {}
            for col_idx in range(1, max_c + 1):
                h_cell = v_ws.cell(row=header_row, column=col_idx)
                h_val = h_cell.value if h_cell.value is not None else f_ws.cell(row=header_row, column=col_idx).value
                if h_val is not None and str(h_val).strip() != "":
                    col_let = get_column_letter(col_idx)
                    h_str = str(h_val).strip()
                    headers.append({"cell": f"{col_let}{header_row}", "col": col_let, "value": h_str})
                    header_map_by_col[col_idx] = h_str

            formulas: list[dict[str, Any]] = []
            col_formula_runs: dict[int, list[tuple[int, str, str, list[str]]]] = {}

            for row_idx in range(1, max_r + 1):
                for col_idx in range(1, max_c + 1):
                    cell = f_ws.cell(row=row_idx, column=col_idx)
                    val_cell = v_ws.cell(row=row_idx, column=col_idx)
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        funcs = analyze_formula(cell.value).functions
                        formulas.append(
                            {
                                "cell": cell.coordinate,
                                "formula": cell.value,
                                "functions": funcs,
                                "cached_value": val_cell.value,
                            }
                        )
                        col_formula_runs.setdefault(col_idx, []).append(
                            (row_idx, cell.coordinate, cell.value, funcs)
                        )

            # Group contiguous formulas in the same column sharing the same function signature
            formula_groups: list[dict[str, Any]] = []
            for col_idx, entries in sorted(col_formula_runs.items()):
                entries.sort(key=lambda x: x[0])
                col_let = get_column_letter(col_idx)
                col_header = header_map_by_col.get(col_idx, f"คอลัมน์ {col_let}")
                curr_group: list[tuple[int, str, str, list[str]]] = []
                for entry in entries:
                    if not curr_group:
                        curr_group = [entry]
                    else:
                        prev_r, _, _, prev_funcs = curr_group[-1]
                        if entry[0] == prev_r + 1 and entry[3] == prev_funcs:
                            curr_group.append(entry)
                        else:
                            formula_groups.append(_pack_formula_group(col_let, col_header, curr_group))
                            curr_group = [entry]
                if curr_group:
                    formula_groups.append(_pack_formula_group(col_let, col_header, curr_group))

            # Inspect visible vs hidden data rows for exact AutoFilter ground-truth
            scan_end = min(max_r, af_end_row) if af_end_row else max_r
            visible_row_nums: list[int] = []
            hidden_row_nums: list[int] = []
            visible_keys: list[str] = []
            all_keys: list[str] = []
            for r_i in range(header_row + 1, scan_end + 1):
                has_data = any(
                    (v_ws.cell(row=r_i, column=c_i).value is not None and str(v_ws.cell(row=r_i, column=c_i).value).strip() != "")
                    or (f_ws.cell(row=r_i, column=c_i).value is not None and str(f_ws.cell(row=r_i, column=c_i).value).strip() != "")
                    for c_i in range(1, max_c + 1)
                )
                if not has_data:
                    continue
                k_raw = v_ws.cell(row=r_i, column=1).value
                if k_raw is None:
                    k_raw = f_ws.cell(row=r_i, column=1).value
                k_str = str(k_raw).strip() if k_raw is not None else ""
                if k_str:
                    all_keys.append(k_str)
                is_hid = bool(getattr(f_ws.row_dimensions[r_i], "hidden", False))
                if is_hid:
                    hidden_row_nums.append(r_i)
                else:
                    visible_row_nums.append(r_i)
                    if k_str:
                        visible_keys.append(k_str)

            # Use first-column keys only if they are unique across all data rows (like Product ID / Student Code)
            unique_first_col = len(all_keys) > 0 and len(set(all_keys)) == len(all_keys)

            from excel_engine.chart_checker.checker import inspect_chart_elements_summary

            charts = [
                inspect_chart_elements_summary(ch, wb=loaded.value_wb)
                for ch in getattr(f_ws, "_charts", [])
            ]

            sheets_info.append(
                {
                    "name": sheet_name,
                    "sheet_state": f_ws.sheet_state,
                    "max_row": f_ws.max_row,
                    "max_column": f_ws.max_column,
                    "header_row": header_row,
                    "headers": headers,
                    "formula_count": len(formulas),
                    "formulas": formulas[:200],
                    "formula_groups": formula_groups,
                    "auto_filter_ref": af_ref,
                    "visible_row_numbers": visible_row_nums,
                    "hidden_row_count": len(hidden_row_nums),
                    "visible_first_col_keys": visible_keys if unique_first_col else [],
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


def _pack_formula_group(
    col_let: str,
    col_header: str,
    group: list[tuple[int, str, str, list[str]]],
) -> dict[str, Any]:
    first_coord = group[0][1]
    last_coord = group[-1][1]
    rng = first_coord if len(group) == 1 else f"{first_coord}:{last_coord}"
    funcs = group[0][3]
    return {
        "column": col_let,
        "column_header": col_header,
        "range": rng,
        "count": len(group),
        "first_formula": group[0][2],
        "functions": funcs,
        "formulas_by_cell": {coord: f_str for _, coord, f_str, _ in group[:120]},
    }


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
