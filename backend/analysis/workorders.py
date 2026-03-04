"""
analysis/workorders.py — Server-side analysis for the Work Orders board.
Fetches, cleans, filters, and computes financial + operational metrics using pandas.
Raw rows never leave this module.
"""

import pandas as pd

from monday import get_all_workorders
from clean import clean_workorders_df

# Valid columns the LLM can use in date_range filters
VALID_DATE_COLS = ["Date of PO/LOI", "Probable Start Date", "Probable End Date"]


# ── Entry point ───────────────────────────────────────────────────────────────


def execute_workorders_analysis(args: dict) -> dict:
    """Fetch Work Orders board, clean, filter, compute metrics; returns compact result dict."""
    df = clean_workorders_df(pd.DataFrame(get_all_workorders()))
    notes = []

    df, filter_notes = apply_column_filters(df, args.get("filters", {}))
    notes.extend(filter_notes)

    df, date_notes = apply_date_filter(df, args.get("date_range"), VALID_DATE_COLS)
    notes.extend(date_notes)

    total = len(df)
    metrics = args.get("metrics", ["count"])
    group_by = args.get("group_by")
    sort_by = args.get("sort_by")
    limit_n = args.get("limit")

    if group_by:
        if group_by not in df.columns:
            return {
                "error": f"group_by column '{group_by}' not found",
                "data_notes": notes,
            }
        results = _wo_grouped(df, group_by, metrics, notes)
    else:
        results = [_wo_single(df, metrics, notes)]

    if sort_by:
        results = sorted(results, key=lambda x: x.get(sort_by) or 0, reverse=True)
    if limit_n:
        results = results[:limit_n]

    return {
        "total_rows_after_filter": total,
        "group_by": group_by,
        "results": results,
        "data_notes": notes,
    }


# ── Filters ───────────────────────────────────────────────────────────────────


def apply_column_filters(df: pd.DataFrame, filters: dict) -> tuple:
    """Apply equality/membership column filters to df; returns (filtered_df, notes)."""
    notes = []
    for col, val in filters.items():
        if col not in df.columns:
            notes.append(f"Filter column '{col}' not found — skipped")
            continue
        df = df[df[col].isin(val)] if isinstance(val, list) else df[df[col] == val]
    return df, notes


def apply_date_filter(
    df: pd.DataFrame, date_range: dict | None, valid_cols: list
) -> tuple:
    """Filter rows to a date window; returns (filtered_df, notes). Both bounds are inclusive."""
    if not date_range:
        return df, []

    col = date_range.get("column", "")
    from_str = date_range.get("from")
    to_str = date_range.get("to")
    notes = []

    if col not in df.columns:
        notes.append(
            f"Date filter column '{col}' not found — skipped. Valid: {valid_cols}"
        )
        return df, notes

    parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
    before = len(df)

    if from_str:
        mask = parsed >= pd.Timestamp(from_str)
        df = df[mask]
        parsed = parsed[mask]
    if to_str:
        mask = parsed <= pd.Timestamp(to_str) + pd.Timedelta(days=1) - pd.Timedelta(
            seconds=1
        )
        df = df[mask]

    notes.append(f"Date filter on '{col}': {before} → {len(df)} rows retained")
    return df, notes


# ── Grouping ──────────────────────────────────────────────────────────────────


def _wo_grouped(df: pd.DataFrame, group_by: str, metrics: list, notes: list) -> list:
    """Group df by a column and compute metrics per group; returns list of result dicts."""
    working = df.copy()
    working[group_by] = working[group_by].replace("", "(unknown)").fillna("(unknown)")

    unknown_n = int((working[group_by] == "(unknown)").sum())
    if unknown_n:
        notes.append(f"{unknown_n} rows had no '{group_by}' — shown as '(unknown)'")

    results = []
    for group_val, group_df in working.groupby(group_by, sort=False):
        row = {group_by: group_val}
        row.update(_wo_single(group_df, metrics, []))
        results.append(row)
    return results


# ── Metric computation ────────────────────────────────────────────────────────


def _wo_single(df: pd.DataFrame, metrics: list, notes: list) -> dict:
    """Compute all requested scalar Work Orders metrics over df; returns flat result dict."""
    result = {}

    if "count" in metrics:
        result["count"] = int(len(df))

    # Map metric names to canonical financial column aliases set by clean_workorders_df
    financial_metrics = {
        "total_contract_value": "_contract_value",
        "total_billed": "_billed",
        "total_collected": "_collected",
        "total_receivable": "_receivable",
        "total_unbilled": "_unbilled",
    }
    for metric_name, col_name in financial_metrics.items():
        if metric_name in metrics:
            result[metric_name] = _sum_col(df, col_name)

    if "billing_coverage" in metrics:
        contract = _sum_col(df, "_contract_value")
        billed = _sum_col(df, "_billed")
        result["billing_coverage_pct"] = (
            round(billed / contract * 100, 1) if (contract and contract > 0) else None
        )

    if "collection_rate" in metrics:
        billed = _sum_col(df, "_billed")
        collected = _sum_col(df, "_collected")
        result["collection_rate_pct"] = (
            round(collected / billed * 100, 1) if (billed and billed > 0) else None
        )

    return result


def _sum_col(df: pd.DataFrame, col_name: str) -> float | None:
    """Sum a canonical financial column, skipping NaN; returns None if column absent."""
    if col_name not in df.columns:
        return None
    return float(df[col_name].dropna().sum())
