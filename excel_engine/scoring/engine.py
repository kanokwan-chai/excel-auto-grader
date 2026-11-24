"""Main Excel Grading Engine Orchestrator.

Pipeline:
1. Validate student file security (magic bytes, size, zip bomb, macro detection)
2. Recalculate formulas via LibreOffice Headless in isolated temp workspace (never runs macros)
3. Open student workbook (data_only=False for formulas, data_only=True for recalculated values)
4. Optionally open reference workbook for formula/value comparison
5. Dispatch each enabled rubric item to the appropriate checker
6. Aggregate scores, build evidence & Thai explanations, clean up temporary files
"""

from __future__ import annotations

import gc
import shutil
import tempfile
from pathlib import Path

from excel_engine.chart_checker import check_chart_item
from excel_engine.exceptions import ExcelEngineError
from excel_engine.formula_checker import check_formula_item
from excel_engine.models import RubricConfig, RubricItemResult, WorkbookGradingOutput
from excel_engine.readers import load_workbooks, recalculate_workbook, validate_excel_file
from excel_engine.scoring.scorer import aggregate_scores, validate_rubric_totals
from excel_engine.style_checker import (
    check_completeness_item,
    check_position_item,
    check_structure_item,
    check_style_item,
)
from excel_engine.value_checker import check_value_item


class ExcelGradingEngine:
    def __init__(
        self,
        libreoffice_bin: str = "soffice",
        max_file_size_mb: int = 15,
        recalc_timeout_seconds: int = 30,
        enable_libreoffice: bool = True,
    ) -> None:
        self.libreoffice_bin = libreoffice_bin
        self.max_file_size_mb = max_file_size_mb
        self.recalc_timeout_seconds = recalc_timeout_seconds
        self.enable_libreoffice = enable_libreoffice

    def grade(
        self,
        student_file_path: str | Path,
        rubric: RubricConfig,
        reference_file_path: str | Path | None = None,
        run_gc: bool = True,
    ) -> WorkbookGradingOutput:
        rubric_validation_errors = validate_rubric_totals(rubric)
        if rubric_validation_errors:
            raise ExcelEngineError("; ".join(rubric_validation_errors), code="INVALID_RUBRIC")

        security_report = validate_excel_file(
            student_file_path,
            max_file_size_mb=self.max_file_size_mb,
        )
        warnings = list(security_report.warnings)

        temp_dir = tempfile.mkdtemp(prefix="excel_grader_run_")
        student_loaded = None
        ref_loaded = None
        recalculated = False

        try:
            enabled_categories = set(rubric.enabled_categories)
            active_cats = {
                item.category
                for item in rubric.items
                if item.is_enabled and item.category in enabled_categories
            }
            needs_value_recalc = "value" in active_cats
            needs_formula_wb = bool(active_cats & {"formula", "style", "structure", "chart"}) or not active_cats
            needs_value_wb = bool(active_cats & {"value", "position", "structure", "completeness"})

            value_file_path: Path = Path(student_file_path)
            if self.enable_libreoffice and needs_value_recalc:
                try:
                    value_file_path, recalculated, lo_warn = recalculate_workbook(
                        student_file_path,
                        temp_dir,
                        libreoffice_bin=self.libreoffice_bin,
                        timeout_seconds=self.recalc_timeout_seconds,
                    )
                    if lo_warn:
                        warnings.append(lo_warn)
                except ExcelEngineError as exc:
                    warnings.append(f"ไม่สามารถคำนวณสูตรใหม่ด้วย LibreOffice: {exc.message}")
                    value_file_path = Path(student_file_path)

            student_loaded = load_workbooks(
                formula_file_path=student_file_path,
                value_file_path=value_file_path,
                load_formula=needs_formula_wb,
                load_value=needs_value_wb,
            )

            needs_ref = bool(active_cats & {"formula", "value", "position", "style"})
            if needs_ref and reference_file_path and Path(reference_file_path).exists():
                ref_loaded = load_workbooks(
                    reference_file_path,
                    load_formula=bool(active_cats & {"formula", "style"}),
                    load_value=bool(active_cats & {"value", "position"}),
                )

            results: list[RubricItemResult] = []

            for item in rubric.items:
                if not item.is_enabled or item.category not in enabled_categories:
                    continue

                if item.category == "formula":
                    res = check_formula_item(
                        item,
                        student_loaded.formula_wb,
                        ref_loaded.formula_wb if ref_loaded else None,
                    )
                elif item.category == "value":
                    res = check_value_item(
                        item,
                        student_loaded.value_wb,
                        ref_loaded.value_wb if ref_loaded else None,
                    )
                elif item.category == "position":
                    res = check_position_item(
                        item,
                        student_loaded.value_wb,
                        ref_loaded.value_wb if ref_loaded else None,
                    )
                elif item.category == "style":
                    res = check_style_item(
                        item,
                        student_loaded.formula_wb,
                        ref_loaded.formula_wb if ref_loaded else None,
                    )
                elif item.category == "structure":
                    res = check_structure_item(item, student_loaded.formula_wb, student_loaded.value_wb)
                elif item.category == "chart":
                    res = check_chart_item(item, student_loaded.formula_wb)
                elif item.category == "completeness":
                    res = check_completeness_item(item, student_loaded.value_wb)
                else:
                    continue

                results.append(res)

            auto_score, max_score, percentage, all_errors = aggregate_scores(rubric, results)

            return WorkbookGradingOutput(
                auto_score=auto_score,
                max_score=max_score,
                percentage=percentage,
                recalculated_with_libreoffice=recalculated,
                security_report=security_report,
                details=results,
                errors=all_errors,
                warnings=warnings,
            )
        finally:
            if student_loaded:
                student_loaded.close()
            if ref_loaded:
                ref_loaded.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
            if run_gc:
                gc.collect()
