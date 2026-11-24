"""Rubric Builder & Versioning API (Multi-Tenant Isolated)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import get_current_teacher
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.storage import storage_service
from backend.app.models.models import Assignment, GradingRubric, ReferenceFile, RubricItem, RubricVersion, User
from backend.app.schemas.schemas import RubricCreate, RubricUpdate
from excel_engine.exceptions import ExcelEngineError
from excel_engine.readers import extract_workbook_metadata, validate_excel_file

router = APIRouter(prefix="/rubrics", tags=["Rubrics"])
settings = get_settings()


def _sanitize_item_rule_cfg(rc: dict | None) -> dict:
    out = dict(rc or {})
    fcs = out.get("filter_conditions")
    if isinstance(fcs, list):
        cleaned = []
        for c in fcs:
            c2 = dict(c)
            if str(c2.get("operator") or "").lower() in ("gt", "gte", "lt", "lte", "between") and str(c2.get("column") or "").strip() in ("ประเภท", "ประเภทสินค้า", "หมวดหมู่", "ยี่ห้อ", "ผู้จำหน่าย"):
                c2["column"] = "ยอดขาย (ชิ้น)"
            cleaned.append(c2)
        out["filter_conditions"] = cleaned
    return out


def _serialize_rubric(r: GradingRubric) -> dict:
    enabled_sum = sum(float(i.max_points) for i in r.items if i.is_enabled)
    return {
        "id": r.id,
        "assignment_id": r.assignment_id,
        "name": r.name,
        "description": r.description,
        "total_points": r.total_points,
        "allocated_points": round(enabled_sum, 2),
        "current_version": r.current_version,
        "is_template": r.is_template,
        "enabled_categories": r.enabled_categories,
        "items": [
            {
                "id": i.id,
                "order_index": i.order_index,
                "title": i.title,
                "description": i.description,
                "category": i.category,
                "sheet_name": i.sheet_name,
                "target_cell": i.target_cell,
                "rule_config": _sanitize_item_rule_cfg(i.rule_config),
                "max_points": i.max_points,
                "min_points": i.min_points,
                "allow_partial_credit": i.allow_partial_credit,
                "weight_importance": i.weight_importance,
                "zero_on_error": i.zero_on_error,
                "is_enabled": i.is_enabled,
            }
            for i in r.items
        ],
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _validate_items_budget(total_points: float, items: list) -> None:
    enabled_sum = sum(float(i.max_points) for i in items if i.is_enabled)
    if round(enabled_sum, 2) > round(total_points, 2):
        raise HTTPException(
            status_code=400,
            detail=f"คะแนนรวมของเกณฑ์ย่อย ({enabled_sum:.2f}) เกินคะแนนเต็มที่กำหนด ({total_points:.2f})",
        )
    for item in items:
        if item.min_points > item.max_points:
            raise HTTPException(
                status_code=400,
                detail=f"เกณฑ์ '{item.title}' มีคะแนนขั้นต่ำมากกว่าคะแนนสูงสุด",
            )


def _create_version_snapshot(db: Session, owner_user_id: str, rubric: GradingRubric, note: str | None) -> RubricVersion:
    snap = _serialize_rubric(rubric)
    ver = RubricVersion(
        owner_user_id=owner_user_id,
        rubric_id=rubric.id,
        version_number=rubric.current_version,
        total_points=rubric.total_points,
        snapshot_json=snap,
        change_note=note or f"เวอร์ชัน {rubric.current_version}",
    )
    db.add(ver)
    return ver


@router.get("")
def list_rubrics(
    assignment_id: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = (
        db.query(GradingRubric)
        .options(selectinload(GradingRubric.items))
        .filter(
            GradingRubric.owner_user_id == current_teacher.id,
            GradingRubric.deleted_at.is_(None),
        )
    )
    if assignment_id:
        q = q.filter(GradingRubric.assignment_id == assignment_id)
    rubrics = q.order_by(GradingRubric.updated_at.desc()).all()
    return [_serialize_rubric(r) for r in rubrics]


@router.get("/{rubric_id}")
def get_rubric(
    rubric_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    r = (
        db.query(GradingRubric)
        .filter(
            GradingRubric.id == rubric_id,
            GradingRubric.owner_user_id == current_teacher.id,
            GradingRubric.deleted_at.is_(None),
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="ไม่พบชุดเกณฑ์การตรวจนี้")
    return _serialize_rubric(r)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rubric(
    payload: RubricCreate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    _validate_items_budget(payload.total_points, payload.items)

    rubric = GradingRubric(
        owner_user_id=current_teacher.id,
        assignment_id=payload.assignment_id,
        name=payload.name.strip(),
        description=payload.description,
        total_points=payload.total_points,
        current_version=1,
        is_template=payload.is_template,
        enabled_categories=payload.enabled_categories,
    )
    db.add(rubric)
    db.flush()

    for idx, item in enumerate(payload.items):
        db.add(
            RubricItem(
                owner_user_id=current_teacher.id,
                rubric_id=rubric.id,
                order_index=item.order_index or idx,
                title=item.title.strip(),
                description=item.description,
                category=item.category,
                sheet_name=item.sheet_name,
                target_cell=item.target_cell,
                rule_config=item.rule_config,
                max_points=item.max_points,
                min_points=item.min_points,
                allow_partial_credit=item.allow_partial_credit,
                weight_importance=item.weight_importance,
                zero_on_error=item.zero_on_error,
                is_enabled=item.is_enabled,
            )
        )
    db.flush()
    db.expire(rubric, ["items"])
    db.refresh(rubric)
    _create_version_snapshot(db, current_teacher.id, rubric, payload.change_note)
    db.commit()
    db.expire(rubric, ["items"])
    db.refresh(rubric)
    return _serialize_rubric(rubric)


@router.put("/{rubric_id}")
def update_rubric(
    rubric_id: str,
    payload: RubricUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    rubric = (
        db.query(GradingRubric)
        .filter(
            GradingRubric.id == rubric_id,
            GradingRubric.owner_user_id == current_teacher.id,
            GradingRubric.deleted_at.is_(None),
        )
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="ไม่พบชุดเกณฑ์การตรวจ")

    new_total = payload.total_points if payload.total_points is not None else rubric.total_points
    if payload.items is not None:
        _validate_items_budget(new_total, payload.items)

    if payload.name is not None:
        rubric.name = payload.name.strip()
    if payload.description is not None:
        rubric.description = payload.description
    if "assignment_id" in payload.model_fields_set:
        rubric.assignment_id = payload.assignment_id
    if payload.total_points is not None:
        rubric.total_points = payload.total_points
    if payload.is_template is not None:
        rubric.is_template = payload.is_template
    if payload.enabled_categories is not None:
        rubric.enabled_categories = payload.enabled_categories

    if payload.items is not None:
        db.query(RubricItem).filter(RubricItem.rubric_id == rubric.id).delete(synchronize_session=False)
        db.flush()
        new_items = [
            RubricItem(
                owner_user_id=current_teacher.id,
                rubric_id=rubric.id,
                order_index=idx,
                title=item.title.strip(),
                description=item.description,
                category=item.category,
                sheet_name=item.sheet_name,
                target_cell=item.target_cell,
                rule_config=item.rule_config,
                max_points=item.max_points,
                min_points=item.min_points,
                allow_partial_credit=item.allow_partial_credit,
                weight_importance=item.weight_importance,
                zero_on_error=item.zero_on_error,
                is_enabled=item.is_enabled,
            )
            for idx, item in enumerate(payload.items)
        ]
        db.add_all(new_items)

    rubric.current_version += 1
    rubric.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.expire(rubric, ["items"])
    db.refresh(rubric)
    _create_version_snapshot(db, current_teacher.id, rubric, payload.change_note)
    db.commit()
    db.expire(rubric, ["items"])
    db.refresh(rubric)
    return _serialize_rubric(rubric)


class ExpandRubricTextRequest(BaseModel):
    prompt_text: str
    total_points: float = 20.0
    sample_metadata: dict[str, Any] | None = None


@router.post("/expand-text")
def expand_natural_language_rubric(
    payload: ExpandRubricTextRequest,
    current_teacher: User = Depends(get_current_teacher),
):
    """Expand casual/free-form Thai or English rubric descriptions into structured Excel grading rules."""
    text = (payload.prompt_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="กรุณาพิมพ์รายละเอียดเกณฑ์ที่ต้องการตรวจ")

    # 1. Detect total score if mentioned (e.g. "เต็ม 20 คะแนน", "รวม 15")
    total_pts = float(payload.total_points or 20.0)
    m_total = re.search(r"(?:คะแนนเต็ม|เต็ม|รวมทั้งหมด|รวม)\s*(\d+(?:\.\d+)?)", text)
    if m_total:
        parsed_total = float(m_total.group(1))
        if parsed_total > 0:
            total_pts = parsed_total

    # Collect sample workbook formulas/sheets if attached
    sample_sheets = (payload.sample_metadata or {}).get("sheets", [])
    default_sheet = sample_sheets[0]["name"] if sample_sheets else "Scores"
    sample_formulas: list[dict[str, Any]] = []
    for sh in sample_sheets:
        for f in sh.get("formulas", []):
            sample_formulas.append({"sheet": sh["name"], "cell": f["cell"], "formula": f["formula"]})

    def _find_sample_formula(func_name: str) -> tuple[str, str, str | None]:
        for sf in sample_formulas:
            if f"{func_name}(" in sf["formula"].upper():
                return sf["sheet"], sf["cell"], sf["formula"]
        return default_sheet, "", None

    def _extract_points_near(keyword_pattern: str) -> float | None:
        m = re.search(rf"(?:{keyword_pattern})[^\n,;]*?(\d+(?:\.\d+)?)\s*(?:คะแนน|แต้ม|pts?|points?)", text, re.IGNORECASE)
        return float(m.group(1)) if m else None

    items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    # 1.5 Multi-Tab / Numbered Filter Exercises Parser (e.g. "ข้อ 1 ... ข้อ 2 ... ข้อ 6 ยกเลิกตัวกรอง")
    numbered_blocks = list(re.finditer(r"(?:^|\n)\s*[-•*]?\s*ข้อ\s*(\d+)[^\n]*", text))
    if len(numbered_blocks) >= 2 and re.search(r"กรอง|filter|ตัวกรอง|ยกเลิกตัวกรอง", text, re.IGNORECASE):
        for b_idx, m_blk in enumerate(numbered_blocks):
            q_num = int(m_blk.group(1))
            start = m_blk.start()
            end = numbered_blocks[b_idx + 1].start() if b_idx + 1 < len(numbered_blocks) else len(text)
            blk_text = text[start:end].strip()
            first_line = blk_text.splitlines()[0].lstrip("-•* ").strip()

            # Pick matching sheet name from attached sample workbook if available, else "ข้อ N"
            tab_name = f"ข้อ {q_num}"
            if sample_sheets:
                if 0 <= q_num - 1 < len(sample_sheets):
                    tab_name = sample_sheets[q_num - 1]["name"]
                for sh in sample_sheets:
                    if re.search(rf"(?:ข้อ(?:ที่)?\s*|^){q_num}(?:\D|$)", sh["name"]):
                        tab_name = sh["name"]
                        break

            # Case 1: Clear filter exercise
            if re.search(r"ยกเลิกตัวกรอง|ล้างตัวกรอง|เอาตัวกรองออก|แสดง.*ปกติ", blk_text, re.IGNORECASE):
                m_vis = re.search(r"(?:ครบ(?:ทั้ง)?|จำนวน|ทั้งหมด)\s*(\d+)\s*(?:รายการ|แถว|คน)", blk_text)
                rule_cfg: dict[str, Any] = {"require_no_active_filter": True}
                if m_vis:
                    rule_cfg["expected_visible_rows"] = int(m_vis.group(1))
                items.append({
                    "title": first_line[:90],
                    "description": f"ตรวจแท็บ '{tab_name}': ยกเลิกตัวกรองทั้งหมด" + (f" และแสดงครบ {m_vis.group(1)} รายการ" if m_vis else ""),
                    "category": "structure",
                    "sheet_name": tab_name,
                    "target_cell": "",
                    "rule_config": rule_cfg,
                    "explicit_points": _extract_points_near(re.escape(first_line[:20])),
                })
                continue

            # Case 2: Active filter conditions (supports text, numeric, exact, and multi-column AND!)
            conds: list[dict[str, Any]] = []
            col_hint_map = [
                (r"ยี่ห้อ", "ยี่ห้อ"),
                (r"ผู้จำหน่าย|จำหน่ายโดย", "ผู้จำหน่าย"),
                (r"ประเภท|หมวดหมู่", "ประเภท"),
                (r"ชื่อสินค้า|ชื่อ", "ชื่อสินค้า"),
                (r"ยอดขาย|จำนวนขาย|จำนวน", "ยอดขาย"),
                (r"ราคา", "ราคา"),
            ]

            def _guess_col(snippet: str) -> str:
                # Pick the RIGHTMOST (closest) column keyword appearing immediately before the condition!
                best_label = ""
                best_pos = -1
                for pat, col_label in col_hint_map:
                    for m_col in re.finditer(pat, snippet, re.IGNORECASE):
                        if m_col.end() > best_pos:
                            best_pos = m_col.end()
                            best_label = col_label
                return best_label

            # Text Filter: starts_with / ends_with / contains / not_contains
            m_starts = re.search(r"ขึ้นต้นด้วย(?:คำว่า)?\s*[`\"'“”]?([^`\"'“”\n,]+)[`\"'“”]?", blk_text)
            if m_starts:
                val = m_starts.group(1).strip().split()[0]
                local_ctx = blk_text[max(0, m_starts.start() - 40) : m_starts.start()]
                conds.append({"column": _guess_col(local_ctx) or "ชื่อสินค้า", "operator": "starts_with", "value": val})

            m_ends = re.search(r"ลงท้ายด้วย(?:คำว่า)?\s*[`\"'“”]?([^`\"'“”\n,]+)[`\"'“”]?", blk_text)
            if m_ends:
                val = m_ends.group(1).strip().split()[0]
                local_ctx = blk_text[max(0, m_ends.start() - 40) : m_ends.start()]
                conds.append({"column": _guess_col(local_ctx) or "ชื่อสินค้า", "operator": "ends_with", "value": val})

            m_contains = re.search(r"(?:มีคำว่า|ประกอบด้วยคำว่า)\s*[`\"'“”]?([^`\"'“”\n,]+)[`\"'“”]?", blk_text)
            if m_contains:
                val = m_contains.group(1).strip().split()[0]
                local_ctx = blk_text[max(0, m_contains.start() - 40) : m_contains.start()]
                conds.append({"column": _guess_col(local_ctx) or "ชื่อสินค้า", "operator": "contains", "value": val})

            # Numeric Filter: between / gte / gt / lte / lt
            m_between = re.search(r"ระหว่าง\s*(\d+(?:\.\d+)?)\s*(?:ถึง|-)\s*(\d+(?:\.\d+)?)", blk_text)
            if m_between:
                local_ctx = blk_text[max(0, m_between.start() - 40) : m_between.start()]
                conds.append({
                    "column": _guess_col(local_ctx) or "ยอดขาย",
                    "operator": "between",
                    "value": float(m_between.group(1)),
                    "value2": float(m_between.group(2)),
                })
            else:
                m_gte = re.search(r"(?:ตั้งแต่|มากกว่าหรือเท่ากับ|>=)\s*(\d+(?:\.\d+)?)", blk_text)
                m_gt = re.search(r"(?:มากกว่า|เกิน|>)\s*(\d+(?:\.\d+)?)", blk_text)
                m_lte = re.search(r"(?:ไม่เกิน|น้อยกว่าหรือเท่ากับ|<=)\s*(\d+(?:\.\d+)?)", blk_text)
                m_lt = re.search(r"(?:น้อยกว่า|ต่ำกว่า|<)\s*(\d+(?:\.\d+)?)", blk_text)
                if m_gte:
                    local_ctx = blk_text[max(0, m_gte.start() - 40) : m_gte.start()]
                    conds.append({"column": _guess_col(local_ctx) or "ยอดขาย", "operator": "gte", "value": float(m_gte.group(1))})
                elif m_gt:
                    local_ctx = blk_text[max(0, m_gt.start() - 40) : m_gt.start()]
                    conds.append({"column": _guess_col(local_ctx) or "ยอดขาย", "operator": "gt", "value": float(m_gt.group(1))})
                elif m_lte:
                    local_ctx = blk_text[max(0, m_lte.start() - 40) : m_lte.start()]
                    conds.append({"column": _guess_col(local_ctx) or "ยอดขาย", "operator": "lte", "value": float(m_lte.group(1))})
                elif m_lt:
                    local_ctx = blk_text[max(0, m_lt.start() - 40) : m_lt.start()]
                    conds.append({"column": _guess_col(local_ctx) or "ยอดขาย", "operator": "lt", "value": float(m_lt.group(1))})

            # Exact quoted / backtick value match (e.g. `Pentel`, `ร้านดิจิทัลพลัส`, `ของใช้ในบ้าน`)
            existing_text_vals = {str(c.get("value", "")).lower() for c in conds}
            for m_q in re.finditer(r"[`\"'“”]([^`\"'“”\n]{1,60})[`\"'“”]", blk_text):
                q_val = m_q.group(1).strip()
                if q_val.lower() in existing_text_vals:
                    continue
                # Look at text immediately before the quoted value to guess column name
                prefix = blk_text[max(0, m_q.start() - 40) : m_q.start()]
                col_guess = _guess_col(prefix) or _guess_col(blk_text)
                conds.append({"column": col_guess, "operator": "equals", "value": q_val})

            rule_cfg = {"require_autofilter": True, "require_filter_applied": True}
            if conds:
                rule_cfg["filter_conditions"] = conds
            items.append({
                "title": first_line[:90],
                "description": f"ตรวจแท็บ '{tab_name}': " + (", ".join(f"{c.get('column') or 'คอลัมน์'} {c['operator']} {c['value']}" for c in conds) if conds else "กรองข้อมูลด้วย AutoFilter"),
                "category": "structure",
                "sheet_name": tab_name,
                "target_cell": "",
                "rule_config": rule_cfg,
                "explicit_points": None,
            })

    # 2. Detect Excel Formula Rules (Thai + English keywords)
    multi_tab_filter_matched = len(items) >= 2
    formula_specs = [] if multi_tab_filter_matched else [
        ("SUM", r"\bSUM\b|ผลรวม|หาผลรวม|บวกรวม", "ตรวจสูตรหาผลรวม (SUM)", "ตรวจสอบการใช้ฟังก์ชัน SUM และช่วงข้อมูลให้ถูกต้อง"),
        ("AVERAGE", r"\bAVERAGE\b|ค่าเฉลี่ย|หาค่าเฉลี่ย", "ตรวจสูตรหาค่าเฉลี่ย (AVERAGE)", "ตรวจสอบการใช้ฟังก์ชัน AVERAGE ในการหาค่าเฉลี่ย"),
        ("MAX", r"\bMAX\b|ค่าสูงสุด|มากที่สุด", "ตรวจสูตรหาค่าสูงสุด (MAX)", "ตรวจสอบการใช้ฟังก์ชัน MAX"),
        ("MIN", r"\bMIN\b|ค่าต่ำสุด|น้อยที่สุด", "ตรวจสูตรหาค่าต่ำสุด (MIN)", "ตรวจสอบการใช้ฟังก์ชัน MIN"),
        ("COUNTIF", r"\bCOUNTIF\b|นับแบบมีเงื่อนไข", "ตรวจสูตรนับตามเงื่อนไข (COUNTIF)", "ตรวจสอบฟังก์ชัน COUNTIF และเงื่อนไขที่กำหนด"),
        ("SUMIF", r"\bSUMIF\b|รวมแบบมีเงื่อนไข", "ตรวจสูตรรวมตามเงื่อนไข (SUMIF)", "ตรวจสอบฟังก์ชัน SUMIF และช่วงข้อมูล"),
        ("COUNTA", r"\bCOUNTA\b", "ตรวจสูตรนับเซลล์ที่มีข้อมูล (COUNTA)", "ตรวจสอบฟังก์ชัน COUNTA"),
        ("COUNT", r"\bCOUNT\b|นับจำนวน", "ตรวจสูตรนับจำนวนตัวเลข (COUNT)", "ตรวจสอบฟังก์ชัน COUNT"),
        ("IF", r"\bIF\b|ตัดเกรด|เงื่อนไข|ผ่านไม่ผ่าน|ผ่าน/ไม่ผ่าน", "ตรวจสูตรเงื่อนไข (IF)", "ตรวจสอบการใช้ฟังก์ชัน IF และเงื่อนไขการประเมินผล"),
        ("VLOOKUP", r"\bVLOOKUP\b|ค้นหาข้อมูล|ดึงข้อมูลจากตาราง", "ตรวจสูตรค้นหาข้อมูล (VLOOKUP)", "ตรวจสอบฟังก์ชัน VLOOKUP ช่วงตาราง และคอลัมน์ผลลัพธ์"),
        ("XLOOKUP", r"\bXLOOKUP\b", "ตรวจสูตรค้นหาข้อมูล (XLOOKUP)", "ตรวจสอบฟังก์ชัน XLOOKUP"),
        ("FILTER", r"\bFILTER\b|ฟังก์ชันกรอง|สูตรกรอง", "ตรวจสูตรกรองข้อมูล (FILTER)", "ตรวจสอบการใช้ฟังก์ชัน FILTER และเงื่อนไขการกรองข้อมูล"),
        ("SORT", r"\bSORT\b|สูตรเรียงข้อมูล", "ตรวจสูตรเรียงลำดับ (SORT)", "ตรวจสอบการใช้ฟังก์ชัน SORT"),
        ("SORTBY", r"\bSORTBY\b", "ตรวจสูตรเรียงลำดับตามเกณฑ์ (SORTBY)", "ตรวจสอบการใช้ฟังก์ชัน SORTBY"),
        ("UNIQUE", r"\bUNIQUE\b|ค่าไม่ซ้ำ", "ตรวจสูตรดึงค่าไม่ซ้ำ (UNIQUE)", "ตรวจสอบการใช้ฟังก์ชัน UNIQUE"),
        ("SUBTOTAL", r"\bSUBTOTAL\b|ผลรวมหลังกรอง", "ตรวจสูตรคำนวณหลังกรอง (SUBTOTAL)", "ตรวจสอบการใช้ฟังก์ชัน SUBTOTAL"),
        ("AGGREGATE", r"\bAGGREGATE\b", "ตรวจสูตรคำนวณขั้นสูง (AGGREGATE)", "ตรวจสอบการใช้ฟังก์ชัน AGGREGATE"),
        ("RANK", r"\bRANK\b|จัดอันดับ|ลำดับที่", "ตรวจสูตรจัดอันดับ (RANK)", "ตรวจสอบฟังก์ชัน RANK"),
    ]

    require_abs = bool(re.search(r"absolute|\$|ล็อกเซลล์|ตรึงเซลล์", text, re.IGNORECASE))
    nested_if = bool(re.search(r"if\s*ซ้อน|ซ้อน\s*if|ตัดเกรด|หลายเงื่อนไข", text, re.IGNORECASE))

    for func_name, pattern, title, desc in formula_specs:
        if re.search(pattern, text, re.IGNORECASE) and func_name not in seen_keys:
            # Avoid matching COUNT when COUNTIF/COUNTA already matched unless COUNT explicitly separate
            if func_name == "COUNT" and ("COUNTIF" in seen_keys or "COUNTA" in seen_keys) and not re.search(r"\bCOUNT\b", text, re.IGNORECASE):
                continue
            seen_keys.add(func_name)
            sh_name, cell_ref, exp_formula = _find_sample_formula(func_name)
            rule_cfg: dict[str, Any] = {"required_functions": [func_name]}
            if exp_formula:
                rule_cfg["expected_formula"] = exp_formula
            if require_abs and func_name in ("VLOOKUP", "RANK", "SUMIF", "COUNTIF"):
                rule_cfg["require_absolute_reference"] = True
            if func_name == "IF" and nested_if:
                rule_cfg["min_nested_if_depth"] = 2

            items.append({
                "title": title,
                "description": desc,
                "category": "formula",
                "sheet_name": sh_name,
                "target_cell": cell_ref or "",
                "rule_config": rule_cfg,
                "explicit_points": _extract_points_near(pattern),
            })

    # 3. Detect Value / Accuracy check
    if not multi_tab_filter_matched and re.search(r"ผลลัพธ์|คำตอบ|ค่าที่คำนวณ|ความถูกต้องของค่า|ห้ามขึ้น error", text, re.IGNORECASE):
        items.append({
            "title": "ตรวจความถูกต้องของผลลัพธ์ที่คำนวณได้",
            "description": "ตรวจสอบค่าผลลัพธ์หลังคำนวณและต้องไม่เกิดข้อผิดพลาด #DIV/0!, #VALUE!, #REF!, #NAME?",
            "category": "value",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": {"tolerance": 0.01},
            "explicit_points": _extract_points_near(r"ผลลัพธ์|คำตอบ"),
        })

    # 4. Detect Cell Position check
    if re.search(r"ตำแหน่งเซลล์|ตรงตำแหน่ง|ตรงช่อง|ไม่เลื่อนแถว", text, re.IGNORECASE):
        items.append({
            "title": "ตรวจตำแหน่งเซลล์และการวางข้อมูล",
            "description": "ตรวจสอบว่าข้อมูลและสูตรอยู่ในตำแหน่งเซลล์ที่กำหนดอย่างครบถ้วน",
            "category": "position",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": {},
            "explicit_points": _extract_points_near(r"ตำแหน่งเซลล์|ตำแหน่ง"),
        })

    # 5. Detect Styling / Decoration rules
    if not multi_tab_filter_matched and re.search(
        r"ตกแต่ง|รูปแบบ|ตาราง|เส้นขอบ|border|ตัวหนา|bold|ตัวเอียง|italic|ฟอนต์|font|สี|ไฮไลท์|ทศนิยม|เปอร์เซ็นต์|ผสานเซลล์|merge|จัดกึ่งกลาง|จัดแนว|ความกว้าง|ความสวยงาม|wrap",
        text,
        re.IGNORECASE,
    ):
        style_cfg: dict[str, Any] = {}
        desc_parts: list[str] = []
        if re.search(r"ตัวหนา|bold|หัวตาราง|ตกแต่ง", text, re.IGNORECASE):
            style_cfg["bold"] = True
            desc_parts.append("ตัวหนาหัวตาราง")
        if re.search(r"ตัวเอียง|italic", text, re.IGNORECASE):
            style_cfg["italic"] = True
            desc_parts.append("ตัวเอียง")
        if re.search(r"เส้นขอบ|border|ตีตาราง|รูปแบบตาราง|ตกแต่ง", text, re.IGNORECASE):
            style_cfg["has_border"] = True
            desc_parts.append("เส้นขอบตาราง")
        if re.search(r"สีพื้นหลัง|ใส่สี|เติมสี|ไฮไลท์|ตกแต่ง", text, re.IGNORECASE):
            style_cfg["has_fill_color"] = True
            desc_parts.append("สีพื้นหลังตกแต่ง")
        if re.search(r"จัดกึ่งกลาง|กึ่งกลาง|center", text, re.IGNORECASE):
            style_cfg["alignment_horizontal"] = "center"
            desc_parts.append("จัดกึ่งกลาง")
        if re.search(r"ผสานเซลล์|merge", text, re.IGNORECASE):
            style_cfg["require_any_merge"] = True
            desc_parts.append("ผสานเซลล์หัวเรื่อง")
        if re.search(r"ปรับความกว้าง|ความกว้างคอลัมน์|autofit", text, re.IGNORECASE):
            style_cfg["require_adjusted_column_width"] = True
            desc_parts.append("ปรับความกว้างคอลัมน์")
        if re.search(r"ตัดข้อความ|wrap", text, re.IGNORECASE):
            style_cfg["wrap_text"] = True
            desc_parts.append("ตัดข้อความ (Wrap Text)")
        if re.search(r"ทศนิยม|2 ตำแหน่ง|สกุลเงิน|บาท|คอมม่า", text, re.IGNORECASE):
            style_cfg["number_format"] = "#,##0.00"
            desc_parts.append("รูปแบบตัวเลขทศนิยม 2 ตำแหน่ง")
        elif re.search(r"เปอร์เซ็นต์|%", text, re.IGNORECASE):
            style_cfg["number_format"] = "0.00%"
            desc_parts.append("รูปแบบเปอร์เซ็นต์")
        if not style_cfg:
            style_cfg = {
                "match_reference_layout_ignore_color": True,
                "bold": True,
                "has_border": True,
                "has_fill_color": True,
            }
            desc_parts = ["ตกแต่งเรียบร้อย", "เส้นขอบเรียบร้อยเหมือนต้นฉบับ", "เลือกใช้สีได้อย่างอิสระ"]
        elif re.search(r"ความสวยงาม|ตกแต่ง|เหมือนต้นฉบับ|สีไม่ต้องเหมือน", text, re.IGNORECASE):
            style_cfg["match_reference_layout_ignore_color"] = True
            desc_parts.append("เทียบโครงสร้างต้นฉบับ (เลือกใช้สีเองได้)")

        items.append({
            "title": "ความสวยงามและการตกแต่ง (เส้นและโครงสร้างเหมือนต้นฉบับ เลือกสีเองได้)",
            "description": "ตรวจสอบ: " + ", ".join(desc_parts),
            "category": "style",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": style_cfg,
            "explicit_points": _extract_points_near(r"ตกแต่ง|รูปแบบ|ตาราง|ความสวยงาม|เส้นขอบ|ทศนิยม|สี"),
        })

    # 6. Detect Worksheet Structure
    if not multi_tab_filter_matched and re.search(r"ชีท|sheet|แผ่นงาน|ชื่อชีท", text, re.IGNORECASE):
        m_cnt = re.search(r"(\d+)\s*(?:ชีท|sheet|แผ่นงาน)", text, re.IGNORECASE)
        struct_cfg: dict[str, Any] = {"no_hidden_sheets": True}
        if m_cnt:
            struct_cfg["exact_sheet_count"] = int(m_cnt.group(1))
        elif sample_sheets:
            struct_cfg["required_sheets"] = [s["name"] for s in sample_sheets]
            struct_cfg["exact_sheet_count"] = len(sample_sheets)
        items.append({
            "title": "ตรวจโครงสร้างและชื่อ Worksheet",
            "description": "ตรวจสอบจำนวนแผ่นงาน ชื่อแผ่นงาน และการไม่ซ่อนแผ่นงาน",
            "category": "structure",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": struct_cfg,
            "explicit_points": _extract_points_near(r"ชีท|sheet|แผ่นงาน|โครงสร้าง"),
        })

    # 6b. Detect AutoFilter / Data Filter tool on table
    if not multi_tab_filter_matched and re.search(r"ตัวกรอง|กรองข้อมูล|autofilter|เปิด\s*filter|ปุ่มกรอง|คัดกรอง", text, re.IGNORECASE):
        require_applied = bool(re.search(r"กรองตามเงื่อนไข|กรองเฉพาะ|คัดกรองเฉพาะ|filter\s*applied|กรองข้อมูลแล้ว", text, re.IGNORECASE))
        af_cfg: dict[str, Any] = {"require_autofilter": True}
        if require_applied:
            af_cfg["require_filter_applied"] = True
        items.append({
            "title": "ตรวจการเปิดและใช้งานตัวกรองข้อมูล (AutoFilter)" if require_applied else "ตรวจการเปิดตัวกรองข้อมูล (AutoFilter)",
            "description": "ตรวจสอบการเปิดปุ่ม Filter (Data > Filter) บนหัวตาราง" + (" และมีการกรองข้อมูลตามเงื่อนไข" if require_applied else ""),
            "category": "structure",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": af_cfg,
            "explicit_points": _extract_points_near(r"ตัวกรอง|กรองข้อมูล|autofilter|filter|คัดกรอง"),
        })

    # 7. Detect Chart & Chart Elements
    if re.search(r"แผนภูมิ|กราฟ|chart", text, re.IGNORECASE):
        chart_type = "bar_or_column"
        if re.search(r"วงกลม|pie", text, re.IGNORECASE):
            chart_type = "pie"
        elif re.search(r"โดนัท|doughnut|donut", text, re.IGNORECASE):
            chart_type = "doughnut"
        elif re.search(r"กราฟเส้น|แผนภูมิเส้น|\bline\b", text, re.IGNORECASE):
            chart_type = "line"
        elif re.search(r"พื้นที่|\barea\b", text, re.IGNORECASE):
            chart_type = "area"
        elif re.search(r"กระจาย|\bscatter\b", text, re.IGNORECASE):
            chart_type = "scatter"
        elif re.search(r"แท่งแนวนอน|\bbar\b", text, re.IGNORECASE):
            chart_type = "bar"
        elif re.search(r"คอลัมน์|แท่งแนวตั้ง|\bcolumn\b", text, re.IGNORECASE):
            chart_type = "column"

        chart_cfg: dict[str, Any] = {"chart_type": chart_type}
        elem_desc: list[str] = [f"ประเภท {chart_type}"]
        if re.search(r"ชื่อแผนภูมิ|ชื่อกราฟ|หัวเรื่องกราฟ|chart\s*title|องค์ประกอบ", text, re.IGNORECASE):
            chart_cfg["require_title"] = True
            elem_desc.append("ชื่อแผนภูมิ")
        if re.search(r"ชื่อแกน\s*x|แกนแนวนอน|ชื่อแกน|องค์ประกอบ", text, re.IGNORECASE) and chart_type not in ("pie", "doughnut"):
            chart_cfg["require_x_axis_title"] = True
            elem_desc.append("ชื่อแกนแนวนอน")
        if re.search(r"ชื่อแกน\s*y|แกนแนวตั้ง|ชื่อแกน|องค์ประกอบ", text, re.IGNORECASE) and chart_type not in ("pie", "doughnut"):
            chart_cfg["require_y_axis_title"] = True
            elem_desc.append("ชื่อแกนแนวตั้ง")
        if re.search(r"เปอร์เซ็นต์บนกราฟ|แสดง\s*%|ร้อยละบนกราฟ", text, re.IGNORECASE):
            chart_cfg["require_percent_labels"] = True
            elem_desc.append("ป้ายเปอร์เซ็นต์ (%)")
        elif re.search(r"ป้ายกำกับข้อมูล|data\s*labels?|ตัวเลขบนกราฟ|แสดงค่าข้อมูล|องค์ประกอบ", text, re.IGNORECASE):
            chart_cfg["require_data_labels"] = True
            elem_desc.append("ป้ายกำกับข้อมูล (Data Labels)")
        if re.search(r"คำอธิบายแผนภูมิ|legend|สัญลักษณ์แทนข้อมูล|องค์ประกอบ", text, re.IGNORECASE):
            chart_cfg["require_legend"] = True
            elem_desc.append("คำอธิบายแผนภูมิ (Legend)")
        if re.search(r"ตารางข้อมูลใต้กราฟ|data\s*table", text, re.IGNORECASE):
            chart_cfg["require_data_table"] = True
            elem_desc.append("ตารางข้อมูลใต้กราฟ")

        items.append({
            "title": f"ตรวจแผนภูมิและองค์ประกอบแผนภูมิ ({chart_type})",
            "description": "ตรวจสอบ: " + ", ".join(elem_desc),
            "category": "chart",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": chart_cfg,
            "explicit_points": _extract_points_near(r"แผนภูมิ|กราฟ|chart|องค์ประกอบ"),
        })

    # 8. Detect Added Data / Completeness / Sorting according to instructions
    if not multi_tab_filter_matched and re.search(
        r"ใส่ข้อมูลเพิ่ม|เพิ่มข้อมูล|กรอกข้อมูล|เพิ่มแถว|เพิ่มรายการ|เพิ่มคอลัมน์|เพิ่มช่อง|เติมข้อมูล|เรียงลำดับ|เรียงจากมากไปน้อย|เรียงจากน้อยไปมาก|ครบถ้วน|หัวตาราง|ข้อมูลครบ|ตามคำสั่ง",
        text,
        re.IGNORECASE,
    ):
        comp_cfg: dict[str, Any] = {}
        desc_parts_comp: list[str] = []

        m_rows = re.search(r"(?:อย่างน้อย|เพิ่ม|กรอก|ใส่|ครบ)\s*(\d+)\s*(?:แถว|รายการ|คน|ข้อมูล|record)", text, re.IGNORECASE)
        if m_rows:
            comp_cfg["min_data_rows"] = int(m_rows.group(1))
            desc_parts_comp.append(f"มีข้อมูลอย่างน้อย {m_rows.group(1)} รายการ")
        elif re.search(r"ใส่ข้อมูลเพิ่ม|เพิ่มข้อมูล|กรอกข้อมูล|เพิ่มแถว|เพิ่มรายการ|เติมข้อมูล", text, re.IGNORECASE):
            comp_cfg["min_data_rows"] = 5
            desc_parts_comp.append("มีการใส่ข้อมูลเพิ่มครบตามคำสั่ง")

        m_cols = re.search(r"(?:อย่างน้อย|เพิ่ม|ครบ)\s*(\d+)\s*(?:คอลัมน์|ช่อง|column)", text, re.IGNORECASE)
        if m_cols:
            comp_cfg["min_columns"] = int(m_cols.group(1))
            desc_parts_comp.append(f"มีอย่างน้อย {m_cols.group(1)} คอลัมน์")

        # Extract any quoted keywords instructed to be added (e.g. เพิ่มคอลัมน์ "หมายเหตุ" หรือ 'สรุปผล')
        quoted_kws = re.findall(r'["\'“”]([^"\'“”]{1,50})["\'“”]', text)
        if quoted_kws:
            comp_cfg["required_keywords"] = quoted_kws
            desc_parts_comp.append("พบข้อความที่สั่งให้เพิ่ม: " + ", ".join(quoted_kws))

        if re.search(r"มากไปน้อย|desc", text, re.IGNORECASE):
            comp_cfg["sorted_column"] = "B"
            comp_cfg["sort_direction"] = "desc"
            desc_parts_comp.append("เรียงข้อมูลจากมากไปน้อย")
        elif re.search(r"น้อยไปมาก|asc", text, re.IGNORECASE):
            comp_cfg["sorted_column"] = "B"
            comp_cfg["sort_direction"] = "asc"
            desc_parts_comp.append("เรียงข้อมูลจากน้อยไปมาก")

        items.append({
            "title": "ตรวจการใส่ข้อมูลเพิ่มและความครบถ้วนตามคำสั่ง",
            "description": "ตรวจสอบ: " + (", ".join(desc_parts_comp) if desc_parts_comp else "จำนวนข้อมูล หัวตาราง และการกรอกข้อมูลเพิ่มตามโจทย์"),
            "category": "completeness",
            "sheet_name": default_sheet,
            "target_cell": "",
            "rule_config": comp_cfg,
            "explicit_points": _extract_points_near(r"ใส่ข้อมูลเพิ่ม|เพิ่มข้อมูล|กรอกข้อมูล|เรียงลำดับ|ครบถ้วน|ตามคำสั่ง"),
        })

    # Fallback: if user wrote very general prose without specific keywords, split by comma/newline
    if not items:
        chunks = [c.strip() for c in re.split(r"[\n,،]+", text) if len(c.strip()) >= 2]
        for ch in chunks[:8]:
            items.append({
                "title": ch[:80],
                "description": f"เกณฑ์ที่ขยายจากคำอธิบาย: {ch}",
                "category": "formula" if "=" in ch else "completeness",
                "sheet_name": default_sheet,
                "target_cell": "",
                "rule_config": {},
                "explicit_points": None,
            })

    # 9. Smart point distribution so total matches total_pts cleanly
    explicit_sum = sum(i["explicit_points"] for i in items if i["explicit_points"] is not None)
    unassigned = [i for i in items if i["explicit_points"] is None]
    remaining = max(0.0, total_pts - explicit_sum)

    if unassigned:
        each = round(remaining / len(unassigned), 2) if remaining > 0 else 1.0
        running = explicit_sum
        for idx, it in enumerate(unassigned):
            if idx == len(unassigned) - 1 and remaining > 0:
                it["max_points"] = max(0.5, round(total_pts - running, 2))
            else:
                it["max_points"] = max(0.5, each)
                running += it["max_points"]

    final_items = []
    for idx, it in enumerate(items):
        pts = it["explicit_points"] if it["explicit_points"] is not None else it.get("max_points", 2.0)
        final_items.append({
            "order_index": idx,
            "title": it["title"],
            "description": it["description"],
            "category": it["category"],
            "sheet_name": it["sheet_name"],
            "target_cell": it["target_cell"],
            "rule_config": it["rule_config"],
            "max_points": round(float(pts), 2),
            "min_points": 0.0,
            "allow_partial_credit": True,
            "weight_importance": "high" if it["category"] == "formula" else "normal",
            "zero_on_error": False,
            "is_enabled": True,
        })

    final_sum = round(sum(i["max_points"] for i in final_items), 2)
    return {
        "total_points": max(total_pts, final_sum),
        "items": final_items,
        "summary_th": f"ขยายความจากข้อความของคุณเป็นเกณฑ์ตรวจละเอียดทั้งหมด {len(final_items)} ข้อ (รวม {final_sum} คะแนน) สามารถปรับแก้เซลล์ สูตร หรือคะแนนแต่ละข้อเพิ่มเติมได้ทันที",
    }


@router.post("/inspect-sample")
async def inspect_sample_excel_for_rubric(
    file: UploadFile = File(...),
    assignment_id: str | None = Form(default=None),
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Upload a sample/reference Excel file in the Rubric Builder to inspect sheets, formulas, charts and auto-suggest rubric items."""
    content = await file.read()
    filename = file.filename or "sample.xlsx"
    storage_path = storage_service.save_bytes(
        user_id=current_teacher.id,
        folder="references",
        filename=filename,
        content=content,
        content_type=file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    local_path = storage_service.get_local_path(storage_path, current_teacher.id)

    try:
        sec = validate_excel_file(local_path, max_file_size_mb=settings.EXCEL_MAX_FILE_SIZE_MB)
        metadata = extract_workbook_metadata(local_path)
    except ExcelEngineError as exc:
        storage_service.delete_file(storage_path, current_teacher.id)
        raise HTTPException(status_code=400, detail=exc.message)

    saved_reference_id = None
    if assignment_id:
        assign = (
            db.query(Assignment)
            .filter(
                Assignment.id == assignment_id,
                Assignment.owner_user_id == current_teacher.id,
                Assignment.deleted_at.is_(None),
            )
            .first()
        )
        if assign:
            db.query(ReferenceFile).filter(
                ReferenceFile.assignment_id == assign.id,
                ReferenceFile.owner_user_id == current_teacher.id,
            ).update({"is_active": False})
            ref = ReferenceFile(
                owner_user_id=current_teacher.id,
                assignment_id=assign.id,
                original_filename=filename,
                storage_path=storage_path,
                file_size_bytes=sec.file_size_bytes,
                sha256_hash=sec.sha256_hash,
                sheet_metadata=metadata,
                has_macros=sec.has_macros,
                is_active=True,
            )
            db.add(ref)
            db.commit()
            db.refresh(ref)
            saved_reference_id = ref.id

    suggested_items: list[dict] = []
    idx = 0
    sheets_meta = metadata.get("sheets", [])
    any_sheet_filtered = any(int(s.get("hidden_row_count") or 0) > 0 for s in sheets_meta)
    columns_by_sheet: dict[str, list[str]] = {}

    for sheet in sheets_meta:
        sname = sheet["name"]
        columns_by_sheet[sname] = [h["value"] for h in sheet.get("headers", []) if h.get("value")]

        # 1) Grouped Formula Rules (100% exact per-cell formula ground-truth!)
        for fg in sheet.get("formula_groups", [])[:25]:
            fn_label = ", ".join(fg.get("functions") or []) or "สูตรคำนวณ"
            col_hdr = fg.get("column_header") or fg.get("range")
            suggested_items.append({
                "order_index": idx,
                "title": f"ตรวจสูตร {fn_label} — {col_hdr} ({fg['range']} แท็บ {sname})",
                "description": f"ตรวจสูตร {fn_label} ในช่วง {fg['range']} เทียบไฟล์เฉลยเป๊ะทุกเซลล์",
                "category": "formula",
                "sheet_name": sname,
                "target_cell": fg["range"],
                "rule_config": {
                    "required_functions": fg.get("functions") or [],
                    "expected_formula": fg["first_formula"],
                    "expected_formulas_by_cell": fg.get("formulas_by_cell") or {},
                },
                "max_points": 2.0,
                "min_points": 0.0,
                "allow_partial_credit": True,
                "weight_importance": "high",
                "zero_on_error": False,
                "is_enabled": True,
            })
            idx += 1

        # 2) AutoFilter Ground-Truth Rules per tab!
        af_ref = sheet.get("auto_filter_ref")
        hid_cnt = int(sheet.get("hidden_row_count") or 0)
        vis_nums = sheet.get("visible_row_numbers") or []
        vis_keys = sheet.get("visible_first_col_keys") or []
        if hid_cnt > 0:
            suggested_items.append({
                "order_index": idx,
                "title": f"ตรวจตัวกรองข้อมูลแท็บ {sname} (แสดง {len(vis_nums)} รายการตามเฉลย)",
                "description": f"เทียบแถวที่กรองแสดงในแท็บ '{sname}' ให้ตรงกับไฟล์เฉลยเป๊ะ 100% ({len(vis_nums)} รายการ)",
                "category": "structure",
                "sheet_name": sname,
                "target_cell": "",
                "rule_config": {
                    "require_autofilter": True,
                    "expected_visible_row_numbers": vis_nums,
                    "expected_visible_keys": vis_keys,
                },
                "max_points": 2.0,
                "min_points": 0.0,
                "allow_partial_credit": True,
                "weight_importance": "high",
                "zero_on_error": False,
                "is_enabled": True,
            })
            idx += 1
        elif any_sheet_filtered and len(sheets_meta) >= 2 and len(vis_nums) > 0:
            # Unfiltered tab in a multi-tab filter workbook (e.g. ข้อ 6 ยกเลิกตัวกรอง แสดงครบ 30 รายการ!)
            suggested_items.append({
                "order_index": idx,
                "title": f"ตรวจการยกเลิกตัวกรองแท็บ {sname} (แสดงครบ {len(vis_nums)} รายการ)",
                "description": f"ตรวจสอบว่าแท็บ '{sname}' ยกเลิกตัวกรองและแสดงข้อมูลครบทั้ง {len(vis_nums)} รายการ",
                "category": "structure",
                "sheet_name": sname,
                "target_cell": "",
                "rule_config": {
                    "require_no_active_filter": True,
                    "expected_visible_rows": len(vis_nums),
                },
                "max_points": 2.0,
                "min_points": 0.0,
                "allow_partial_credit": True,
                "weight_importance": "normal",
                "zero_on_error": False,
                "is_enabled": True,
            })
            idx += 1
        elif af_ref and not any_sheet_filtered:
            suggested_items.append({
                "order_index": idx,
                "title": f"ตรวจการเปิดปุ่มตัวกรอง (AutoFilter) แท็บ {sname}",
                "description": f"ตรวจสอบการเปิดใช้งาน AutoFilter ในแท็บ '{sname}'",
                "category": "structure",
                "sheet_name": sname,
                "target_cell": "",
                "rule_config": {"require_autofilter": True},
                "max_points": 2.0,
                "min_points": 0.0,
                "allow_partial_credit": True,
                "weight_importance": "normal",
                "zero_on_error": False,
                "is_enabled": True,
            })
            idx += 1

        # 3) Chart & Chart Elements Ground-Truth Rules from Answer Key (forgiving on wording!)
        for ch_idx, ch in enumerate(sheet.get("charts", []), start=1):
            ch_cfg: dict[str, Any] = {"chart_type": ch.get("type") or "bar_or_column"}
            # Require presence of title/elements that exist in Answer Key WITHOUT locking exact wording!
            if ch.get("has_title") and str(ch.get("title") or "").lower() not in {"", "chart title", "ชื่อแผนภูมิ"}:
                ch_cfg["require_title"] = True
            if ch.get("has_x_axis_title") and str(ch.get("x_axis_title") or "").lower() not in {"", "axis title", "ชื่อแกน"}:
                ch_cfg["require_x_axis_title"] = True
            if ch.get("has_y_axis_title") and str(ch.get("y_axis_title") or "").lower() not in {"", "axis title", "ชื่อแกน"}:
                ch_cfg["require_y_axis_title"] = True
            if ch.get("has_percent_labels"):
                ch_cfg["require_percent_labels"] = True
            elif ch.get("has_data_labels"):
                ch_cfg["require_data_labels"] = True
            if ch.get("has_legend") and int(ch.get("series_count") or 0) > 1:
                ch_cfg["require_legend"] = True
            if ch.get("has_data_table"):
                ch_cfg["require_data_table"] = True

            suggested_items.append({
                "order_index": idx,
                "title": f"ตรวจแผนภูมิที่ {ch_idx}: {ch.get('title') or ch.get('type')} (แท็บ {sname})",
                "description": "ตรวจสอบประเภทแผนภูมิและองค์ประกอบตามเฉลย (ยืดหยุ่นข้อความชื่อกราฟ/ชื่อแกน)",
                "category": "chart",
                "sheet_name": sname,
                "target_cell": "",
                "rule_config": ch_cfg,
                "max_points": 2.0,
                "min_points": 0.0,
                "allow_partial_credit": True,
                "weight_importance": "normal",
                "zero_on_error": False,
                "is_enabled": True,
            })
            idx += 1

    # Fallback if plain data sheet without formulas/filters/charts
    if not suggested_items and metadata.get("sheet_names"):
        suggested_items.append({
            "order_index": 0,
            "title": "ตรวจโครงสร้าง Worksheet ครบตามต้นฉบับ",
            "category": "structure",
            "sheet_name": metadata["sheet_names"][0],
            "target_cell": "",
            "rule_config": {
                "required_sheets": metadata["sheet_names"],
                "exact_sheet_count": metadata["sheet_count"],
            },
            "max_points": 20.0,
            "min_points": 0.0,
            "allow_partial_credit": True,
            "weight_importance": "normal",
            "zero_on_error": False,
            "is_enabled": True,
        })
    elif suggested_items:
        # Auto-balance points cleanly to 20.0 so teacher doesn't have to calculate by hand!
        target_total = 20.0
        base_pts = int((target_total / len(suggested_items)) * 100) / 100.0
        running_pts = 0.0
        for s_i, s_it in enumerate(suggested_items):
            if s_i == len(suggested_items) - 1:
                s_it["max_points"] = round(target_total - running_pts, 2)
            else:
                s_it["max_points"] = base_pts
                running_pts = round(running_pts + base_pts, 2)

    return {
        "filename": filename,
        "storage_path": storage_path,
        "saved_reference_id": saved_reference_id,
        "has_macros": sec.has_macros,
        "warnings": sec.warnings,
        "sheet_metadata": metadata,
        "columns_by_sheet": columns_by_sheet,
        "suggested_items": suggested_items,
    }


class TestRubricSampleRequest(BaseModel):
    storage_path: str
    total_points: float = 20.0
    items: list[dict[str, Any]]


@router.post("/test-sample")
def dry_run_rubric_against_sample(
    payload: TestRubricSampleRequest,
    current_teacher: User = Depends(get_current_teacher),
):
    """Run the REAL ExcelGradingEngine on the teacher's Answer Key file to verify 100% accuracy before saving."""
    from excel_engine.models import RubricConfig, RubricItemConfig
    from excel_engine.scoring.engine import ExcelGradingEngine

    try:
        local_path = storage_service.get_local_path(payload.storage_path, current_teacher.id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์เฉลยที่แนบไว้ กรุณาอัปโหลดไฟล์เฉลยใหม่อีกครั้ง")

    cfg_items = [
        RubricItemConfig(
            id=str(it.get("id") or f"item_{idx}"),
            title=str(it.get("title") or f"ข้อที่ {idx + 1}"),
            category=str(it.get("category") or "formula"),
            sheet_name=it.get("sheet_name") or None,
            target_cell=it.get("target_cell") or None,
            rule_config=it.get("rule_config") or {},
            max_points=float(it.get("max_points") or 0.0),
            min_points=float(it.get("min_points") or 0.0),
            allow_partial_credit=bool(it.get("allow_partial_credit", True)),
            weight_importance=str(it.get("weight_importance") or "normal"),
            zero_on_error=bool(it.get("zero_on_error", False)),
            is_enabled=bool(it.get("is_enabled", True)),
        )
        for idx, it in enumerate(payload.items)
    ]
    rubric_cfg = RubricConfig(
        id="dry_run_preview",
        name="Dry Run Test",
        version=1,
        total_points=float(payload.total_points),
        items=cfg_items,
    )
    engine = ExcelGradingEngine(
        libreoffice_bin=settings.LIBREOFFICE_BIN,
        max_file_size_mb=settings.EXCEL_MAX_FILE_SIZE_MB,
        recalc_timeout_seconds=settings.EXCEL_RECALC_TIMEOUT_SECONDS,
        enable_libreoffice=False,
    )
    try:
        out = engine.grade(
            student_file_path=local_path,
            rubric=rubric_cfg,
            reference_file_path=local_path,
        )
    except ExcelEngineError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    return {
        "auto_score": out.auto_score,
        "max_score": out.max_score,
        "percentage": out.percentage,
        "all_passed": all(d.passed for d in out.details),
        "details": [
            {
                "item_title": d.item_title,
                "earned_points": d.earned_points,
                "max_points": d.max_points,
                "passed": d.passed,
                "reason": d.reason,
                "suggestion": d.suggestion,
            }
            for d in out.details
        ],
    }


@router.post("/{rubric_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_rubric(
    rubric_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    orig = (
        db.query(GradingRubric)
        .filter(
            GradingRubric.id == rubric_id,
            GradingRubric.owner_user_id == current_teacher.id,
            GradingRubric.deleted_at.is_(None),
        )
        .first()
    )
    if not orig:
        raise HTTPException(status_code=404, detail="ไม่พบชุดเกณฑ์ต้นฉบับ")

    cloned = GradingRubric(
        owner_user_id=current_teacher.id,
        assignment_id=orig.assignment_id,
        name=f"{orig.name} (สำเนา)",
        description=orig.description,
        total_points=orig.total_points,
        current_version=1,
        is_template=orig.is_template,
        enabled_categories=list(orig.enabled_categories or []),
    )
    db.add(cloned)
    db.flush()

    for i in orig.items:
        db.add(
            RubricItem(
                owner_user_id=current_teacher.id,
                rubric_id=cloned.id,
                order_index=i.order_index,
                title=i.title,
                description=i.description,
                category=i.category,
                sheet_name=i.sheet_name,
                target_cell=i.target_cell,
                rule_config=dict(i.rule_config or {}),
                max_points=i.max_points,
                min_points=i.min_points,
                allow_partial_credit=i.allow_partial_credit,
                weight_importance=i.weight_importance,
                zero_on_error=i.zero_on_error,
                is_enabled=i.is_enabled,
            )
        )
    db.flush()
    db.refresh(cloned)
    _create_version_snapshot(db, current_teacher.id, cloned, f"คัดลอกจาก '{orig.name}'")
    db.commit()
    db.refresh(cloned)
    return _serialize_rubric(cloned)


@router.get("/{rubric_id}/versions")
def list_rubric_versions(
    rubric_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    versions = (
        db.query(RubricVersion)
        .filter(
            RubricVersion.rubric_id == rubric_id,
            RubricVersion.owner_user_id == current_teacher.id,
        )
        .order_by(RubricVersion.version_number.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "total_points": v.total_points,
            "change_note": v.change_note,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.delete("/{rubric_id}")
def delete_rubric(
    rubric_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    rubric = (
        db.query(GradingRubric)
        .filter(GradingRubric.id == rubric_id, GradingRubric.owner_user_id == current_teacher.id)
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="ไม่พบชุดเกณฑ์การตรวจ")
    rubric.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "ลบเกณฑ์การตรวจเรียบร้อยแล้ว"}
