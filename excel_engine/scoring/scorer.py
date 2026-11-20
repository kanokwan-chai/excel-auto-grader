"""Score aggregation & rubric validation rules."""

from __future__ import annotations

from excel_engine.models import GradingErrorRecord, RubricConfig, RubricItemResult


def validate_rubric_totals(rubric: RubricConfig) -> list[str]:
    """Ensure enabled rubric items do not exceed total_points."""
    errors: list[str] = []
    enabled_sum = sum(item.max_points for item in rubric.items if item.is_enabled)
    if round(enabled_sum, 2) > round(rubric.total_points, 2):
        errors.append(
            f"คะแนนรวมของเกณฑ์ย่อย ({enabled_sum:.2f}) เกินคะแนนเต็มของงาน ({rubric.total_points:.2f})"
        )
    for item in rubric.items:
        if item.min_points > item.max_points:
            errors.append(
                f"เกณฑ์ '{item.title}' มีคะแนนขั้นต่ำ ({item.min_points}) มากกว่าคะแนนสูงสุด ({item.max_points})"
            )
    return errors


def aggregate_scores(
    rubric: RubricConfig,
    item_results: list[RubricItemResult],
) -> tuple[float, float, float, list[GradingErrorRecord]]:
    """
    Aggregate rubric item results into total auto_score, max_score, percentage, and flattened errors.
    Clamps final score strictly to [0, rubric.total_points].
    """
    raw_earned = sum(r.earned_points for r in item_results)
    max_score = float(rubric.total_points)
    auto_score = round(max(0.0, min(max_score, raw_earned)), 2)
    percentage = round((auto_score / max_score * 100.0) if max_score > 0 else 0.0, 2)

    all_errors: list[GradingErrorRecord] = []
    for r in item_results:
        all_errors.extend(r.errors)

    return auto_score, max_score, percentage, all_errors
