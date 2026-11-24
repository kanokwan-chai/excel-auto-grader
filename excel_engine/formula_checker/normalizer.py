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


def _strip_outer_parens(expr: str) -> str:
    s = expr.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        wraps_all = True
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(s) - 1:
                    wraps_all = False
                    break
        if wraps_all and depth == 0:
            s = s[1:-1].strip()
        else:
            break
    return s


_SINGLE_CELL_RE = re.compile(r"^(?:(?:'[^']+'|[A-Z0-9_.\u0E00-\u0E7F]+)!)?[A-Z]{1,3}[0-9]+$")
_RANGE_CELL_RE = re.compile(r"^((?:'[^']+'|[A-Z0-9_.\u0E00-\u0E7F]+)!)?([A-Z]{1,3}[0-9]+:[A-Z]{1,3}[0-9]+)$")


def _expand_ref_token(tok: str) -> list[str] | None:
    """Expand 'C4' -> ['C4'], 'C4:E4' -> ['C4','D4','E4'], 'Sheet1!C4:E4' -> ['Sheet1!C4',...]."""
    t = _strip_outer_parens(tok).replace("$", "")
    if _SINGLE_CELL_RE.fullmatch(t):
        return [t]
    m_rng = _RANGE_CELL_RE.fullmatch(t)
    if m_rng:
        prefix = m_rng.group(1) or ""
        rng = m_rng.group(2)
        try:
            from openpyxl.utils import get_column_letter, range_boundaries

            min_c, min_r, max_c, max_r = range_boundaries(rng)
            if (max_c - min_c + 1) * (max_r - min_r + 1) > 2000:
                return None
            return [
                f"{prefix}{get_column_letter(c)}{r}"
                for r in range(min_r, max_r + 1)
                for c in range(min_c, max_c + 1)
            ]
        except Exception:
            return None
    return None


def _extract_sum_terms(expr_no_eq: str) -> list[str] | None:
    """
    Extract sorted list of summed cell coordinates from either:
    - SUM(C4:E4), SUM(C4,D4,E4), SUM(C4+D4+E4), SUM(C4:D4,E4)
    - Pure addition chain: C4+D4+E4, (C4+D4+E4)
    Returns sorted list of expanded cell refs (preserving duplicates), or None if not a pure sum.
    """
    s = _strip_outer_parens(expr_no_eq.replace("$", ""))
    if s.startswith("SUM(") and s.endswith(")"):
        inner = _strip_outer_parens(s[4:-1])
        # Support SUM(C4,D4,E4), SUM(C4:E4), and even SUM(C4+D4+E4)
        if any(op in inner for op in ("-", "*", "/", "(", ")")):
            return None
        raw_parts: list[str] = []
        for comma_part in inner.split(","):
            for plus_part in comma_part.split("+"):
                p = plus_part.strip()
                if not p:
                    return None
                raw_parts.append(p)
        expanded: list[str] = []
        for part in raw_parts:
            cells = _expand_ref_token(part)
            if not cells:
                return None
            expanded.extend(cells)
        return sorted(expanded) if expanded else None

    if "+" in s and not any(op in s for op in ("-", "*", "/", "(", ")", ",")):
        expanded = []
        for part in s.split("+"):
            cells = _expand_ref_token(part.strip())
            if not cells:
                return None
            expanded.extend(cells)
        return sorted(expanded) if len(expanded) >= 2 else None

    return None


def _extract_product_terms(expr_no_eq: str) -> list[str] | None:
    """
    Extract sorted list of multiplied cell/number operands from:
    - B4*F4, F4*B4, (B4*F4), SUM(B4*F4), PRODUCT(B4,F4), PRODUCT(B4:C4)
    """
    s = _strip_outer_parens(expr_no_eq.replace("$", ""))
    if s.startswith("SUM(") and s.endswith(")") and "*" in s:
        s = _strip_outer_parens(s[4:-1])
    if s.startswith("PRODUCT(") and s.endswith(")"):
        inner = _strip_outer_parens(s[8:-1])
        if any(op in inner for op in ("+", "-", "/", "(", ")")):
            return None
        parts = [p.strip() for chunk in inner.split(",") for p in chunk.split("*") if p.strip()]
    elif "*" in s and not any(op in s for op in ("+", "-", "/", "(", ")", ",")):
        parts = [p.strip() for p in s.split("*") if p.strip()]
    else:
        return None

    if len(parts) < 2:
        return None
    expanded: list[str] = []
    for p in parts:
        cells = _expand_ref_token(p)
        if cells:
            expanded.extend(cells)
        elif re.fullmatch(r"\d+(?:\.\d+)?", p):
            expanded.append(str(float(p)))
        else:
            return None
    return sorted(expanded)


def is_pure_addition_formula(formula: str) -> bool:
    """Return True if formula is a pure addition of >=2 cell references (e.g. =C4+D4+E4)."""
    norm = normalize_formula(formula, preserve_absolute=False)
    s = _strip_outer_parens(norm[1:])
    if "+" not in s or any(op in s for op in ("-", "*", "/", "(", ")", ",")):
        return False
    terms = _extract_sum_terms(s)
    return bool(terms and len(terms) >= 2)


def are_formulas_equivalent(
    actual_formula: str,
    expected_formula: str,
    strict_reference_mode: bool = False,
) -> tuple[bool, str]:
    """
    Compare two formulas carefully.
    Returns (is_equivalent, match_reason).
    Supports:
    - Exact / absolute-insensitive match
    - SUM(C4:E4) == C4+D4+E4 == (C4+D4+E4) == SUM(C4,D4,E4) == SUM(C4+D4+E4)
    - B4*F4 == F4*B4 == PRODUCT(B4,F4) == SUM(B4*F4)
    """
    a = analyze_formula(actual_formula)
    e = analyze_formula(expected_formula)

    if a.normalized == e.normalized:
        return True, "exact_normalized_match"

    if not strict_reference_mode and a.normalized_no_abs == e.normalized_no_abs:
        return True, "normalized_ignore_absolute_match"

    if not strict_reference_mode:
        # 1. Pure sum equivalence: =C4+D4+E4 <-> =SUM(C4:E4) <-> =SUM(C4,D4,E4)
        sum_a = _extract_sum_terms(a.normalized_no_abs[1:])
        sum_e = _extract_sum_terms(e.normalized_no_abs[1:])
        if sum_a is not None and sum_e is not None and sum_a == sum_e:
            return True, "sum_addition_equivalent_match"

        # 2. Pure product equivalence: =F4*B4 <-> =B4*F4 <-> =PRODUCT(B4,F4) <-> =SUM(B4*F4)
        prod_a = _extract_product_terms(a.normalized_no_abs[1:])
        prod_e = _extract_product_terms(e.normalized_no_abs[1:])
        if prod_a is not None and prod_e is not None and prod_a == prod_e:
            return True, "commutative_product_match"

        # 3. General simple commutative addition (e.g. A1+10 vs 10+A1)
        if _check_simple_commutative_addition(a.normalized_no_abs[1:], e.normalized_no_abs[1:]):
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
