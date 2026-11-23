"""Careful Excel Formula Normalizer & Structural Analyzer.

Rules:
- Preserves string literals intact (never uppercases text inside quotes).
- Strips non-semantic whitespace outside string literals.
- Normalizes function names and cell references to uppercase.
- Handles quoted vs unquoted sheet names (`'Sheet 2'!A1` vs `Sheet2!A1`).
- Preserves `$` (absolute vs relative references) unless explicitly asked to ignore.
- Never equates semantically different formulas without proven equivalence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FUNC_PATTERN = re.compile(r"([A-Z][A-Z0-9_.]+)\s*\(")
RANGE_PATTERN = re.compile(
    r"(?:(?:'[^']+'|[A-Za-z0-9_.\u0E00-\u0E7F]+)!)?\$?[A-Za-z]{1,3}\$?[0-9]+(?::\$?[A-Za-z]{1,3}\$?[0-9]+)?"
)
CROSS_SHEET_PATTERN = re.compile(
    r"(?:'([^']+)'|([A-Za-z0-9_.\u0E00-\u0E7F]+))!(\$?[A-Za-z]{1,3}\$?[0-9]+(?::\$?[A-Za-z]{1,3}\$?[0-9]+)?)"
)


@dataclass
class FormulaAnalysis:
    raw: str
    normalized: str
    normalized_no_abs: str
    functions: list[str]
    references: list[str]
    cross_sheet_refs: list[tuple[str, str]]
    has_absolute_ref: bool
    nested_if_depth: int


def _strip_whitespace_outside_strings(expr: str) -> str:
    out: list[str] = []
    in_string = False
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == '"':
            out.append(ch)
            if in_string and i + 1 < n and expr[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if in_string:
            out.append(ch)
        else:
            if not ch.isspace():
                out.append(ch.upper())
        i += 1
    return "".join(out)


def _normalize_sheet_quotes(expr: str) -> str:
    """Normalize `'Sheet2'!A1` -> `SHEET2!A1` when sheet name has no spaces/special chars."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if re.fullmatch(r"[A-Z0-9_.\u0E00-\u0E7F]+", name):
            return f"{name}!"
        return f"'{name}'!"

    return re.sub(r"'([^']+)'!", repl, expr)


def _mask_string_literals(expr: str) -> str:
    """Replace string literals with empty quotes so regexes don't match inside strings."""
    return re.sub(r'"(?:[^"]|"")*"', '""', expr)


def _count_nested_if_depth(expr_masked: str) -> int:
    """Calculate maximum nesting depth of IF(...) calls."""
    max_depth = 0
    current_if_depth = 0
    paren_stack: list[bool] = []  # True if this paren belongs to an IF(
    i = 0
    n = len(expr_masked)
    while i < n:
        if expr_masked[i : i + 3] == "IF(" and (i == 0 or not expr_masked[i - 1].isalnum()):
            paren_stack.append(True)
            current_if_depth += 1
            max_depth = max(max_depth, current_if_depth)
            i += 3
            continue
        if expr_masked[i] == "(":
            paren_stack.append(False)
        elif expr_masked[i] == ")" and paren_stack:
            was_if = paren_stack.pop()
            if was_if:
                current_if_depth = max(0, current_if_depth - 1)
        i += 1
    return max_depth


def normalize_formula(formula: str, preserve_absolute: bool = True) -> str:
    """Normalize an Excel formula string carefully."""
    text = formula.strip()
    if text.startswith("="):
        text = text[1:]
    # Handle openpyxl/Excel _xlfn. / _xlws. / _xlpm. prefixes for modern dynamic-array functions (e.g. FILTER, SORT, UNIQUE, XLOOKUP, IFS)
    text = re.sub(r"(?i)(?:_xlfn\.|_xlws\.|_xlpm\.)+", "", text)
    compact = _strip_whitespace_outside_strings(text)
    compact = _normalize_sheet_quotes(compact)
    if not preserve_absolute:
        compact = compact.replace("$", "")
    return f"={compact}"


def analyze_formula(formula: str) -> FormulaAnalysis:
    norm = normalize_formula(formula, preserve_absolute=True)
    norm_no_abs = normalize_formula(formula, preserve_absolute=False)
    masked = _mask_string_literals(norm[1:])

    functions = FUNC_PATTERN.findall(masked)
    references = RANGE_PATTERN.findall(masked)

    cross_refs: list[tuple[str, str]] = []
    for m in CROSS_SHEET_PATTERN.finditer(masked):
        sheet = m.group(1) or m.group(2)
        ref = m.group(3)
        cross_refs.append((sheet, ref))

    has_abs = "$" in masked
    if_depth = _count_nested_if_depth(masked)

    return FormulaAnalysis(
        raw=formula,
        normalized=norm,
        normalized_no_abs=norm_no_abs,
        functions=functions,
        references=references,
        cross_sheet_refs=cross_refs,
        has_absolute_ref=has_abs,
        nested_if_depth=if_depth,
    )


def are_formulas_equivalent(
    actual_formula: str,
    expected_formula: str,
    strict_reference_mode: bool = False,
) -> tuple[bool, str]:
    """
    Compare two formulas carefully.
    Returns (is_equivalent, match_reason).
    """
    a = analyze_formula(actual_formula)
    e = analyze_formula(expected_formula)

    if a.normalized == e.normalized:
        return True, "exact_normalized_match"

    if not strict_reference_mode and a.normalized_no_abs == e.normalized_no_abs:
        return True, "normalized_ignore_absolute_match"

    # Safe commutative equivalence for simple 2-arg SUM/AVERAGE/MAX/MIN or A+B == B+A
    # Only when exact same function and sorted argument list for strictly commutative functions
    if _check_simple_commutative_addition(a.normalized_no_abs[1:], e.normalized_no_abs[1:]) and not strict_reference_mode:
        return True, "commutative_addition_match"

    return False, "mismatch"


def _check_simple_commutative_addition(expr_a: str, expr_b: str) -> bool:
    """Check if two pure addition expressions (e.g. A1+B1 vs B1+A1) are equivalent."""
    if any(op in expr_a for op in ("-", "*", "/", "(", ")", ",")) or any(
        op in expr_b for op in ("-", "*", "/", "(", ")", ",")
    ):
        return False
    if "+" not in expr_a or "+" not in expr_b:
        return False
    return sorted(expr_a.split("+")) == sorted(expr_b.split("+"))
