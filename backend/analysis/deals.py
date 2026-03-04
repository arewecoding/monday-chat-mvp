"""
analysis/deals.py — Server-side analysis for the Deals board.
Fetches, cleans, filters, and computes metrics using pandas.
Raw rows never leave this module.
"""

import pandas as pd

from monday import get_all_deals
from clean import clean_deals_df

# Valid columns the LLM can use in date_range filters
VALID_DATE_COLS = ["Created Date", "Tentative Close Date", "Close Date (A)"]

# Closure Probability → probability weight mapping (Workflow Doc §3.2)
PROBABILITY_WEIGHTS = {
    "High": 0.8,
    "Medium": 0.5,
    "Low": 0.2,
    "": 0.3,  # unknown → conservative estimate
}


# ── Entry point ───────────────────────────────────────────────────────────────


def execute_deals_analysis(args: dict) -> dict:
    """Fetch Deals board, clean, filter, compute metrics; returns compact result dict."""
    df = clean_deals_df(pd.DataFrame(get_all_deals()))
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
        results = _deals_grouped(df, group_by, metrics, notes)
    else:
        results = [_deals_single(df, metrics, notes)]

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


def _deals_grouped(df: pd.DataFrame, group_by: str, metrics: list, notes: list) -> list:
    """Group df by a column and compute metrics per group; returns list of result dicts."""
    working = df.copy()
    working[group_by] = working[group_by].replace("", "(unknown)").fillna("(unknown)")

    unknown_n = int((working[group_by] == "(unknown)").sum())
    if unknown_n:
        notes.append(f"{unknown_n} rows had no '{group_by}' — shown as '(unknown)'")

    results = []
    for group_val, group_df in working.groupby(group_by, sort=False):
        row = {group_by: group_val}
        row.update(_deals_single(group_df, metrics, []))
        results.append(row)
    return results


# ── Metric computation ────────────────────────────────────────────────────────


def _deals_single(df: pd.DataFrame, metrics: list, notes: list) -> dict:
    """Compute all requested scalar metrics over df; returns flat result dict."""
    result = {}

    if "count" in metrics:
        result["count"] = int(len(df))

    # Value-based metrics
    if any(
        m in metrics
        for m in (
            "total_value",
            "avg_value",
            "null_value_count",
            "weighted_pipeline_value",
        )
    ):
        values = (
            df["_deal_value"].dropna()
            if "_deal_value" in df.columns
            else pd.Series([], dtype=float)
        )
        null_count = int(len(df) - len(values))
        if "total_value" in metrics:
            result["total_value"] = float(values.sum()) if len(values) else 0.0
        if "avg_value" in metrics:
            result["avg_value"] = (
                round(float(values.mean()), 2) if len(values) else None
            )
        if "null_value_count" in metrics:
            result["null_value_count"] = null_count
        elif null_count:
            notes.append(
                f"{null_count} rows had no Deal Value — excluded from value metrics"
            )

    if "overdue_count" in metrics and "is_overdue" in df.columns:
        result["overdue_count"] = int(df["is_overdue"].sum())

    if "win_rate" in metrics and "Deal Status" in df.columns:
        result.update(_compute_win_rate(df, notes))

    if "weighted_pipeline_value" in metrics:
        result["weighted_pipeline_value"] = compute_weighted_pipeline(df)

    if "avg_deal_age_days" in metrics:
        result.update(compute_avg_deal_age(df))

    return result


def _compute_win_rate(df: pd.DataFrame, notes: list) -> dict:
    """Compute won/dead/win_rate and append a bulk-import caveat note if applicable."""
    won = int((df["Deal Status"] == "Won").sum())
    dead = int((df["Deal Status"] == "Dead").sum())
    total_closed = won + dead

    bulk_n = count_bulk_imports(df)
    if bulk_n:
        notes.append(
            f"Note: {bulk_n} Won deals appear to be bulk-imported historical records "
            f"(stage 'A. Lead Generated', no value). Win rate may be inflated."
        )

    return {
        "win_rate_pct": round(won / total_closed * 100, 1) if total_closed else None,
        "won_count": won,
        "dead_count": dead,
    }


# ── Standalone helpers (also used by improvement checklist) ──────────────────


def compute_weighted_pipeline(df: pd.DataFrame) -> float:
    """Multiply each deal's _deal_value by its Closure Probability weight and return the sum."""
    if "Closure Probability" not in df.columns or "_deal_value" not in df.columns:
        return 0.0
    weights = df["Closure Probability"].map(PROBABILITY_WEIGHTS).fillna(0.3)
    weighted = df["_deal_value"].fillna(0) * weights
    return round(float(weighted.sum()), 2)


def compute_avg_deal_age(df: pd.DataFrame) -> dict:
    """Compute average deal age in days from Created Date; returns dict with avg and max."""
    if "Created Date" not in df.columns:
        return {"avg_deal_age_days": None, "deals_with_no_created_date": len(df)}

    created = pd.to_datetime(df["Created Date"], errors="coerce")
    valid = created.dropna()
    missing_count = int(len(df) - len(valid))

    if len(valid) == 0:
        return {"avg_deal_age_days": None, "deals_with_no_created_date": missing_count}

    ages = (pd.Timestamp.today() - valid).dt.days
    return {
        "avg_deal_age_days": int(ages.mean().round()),
        "max_deal_age_days": int(ages.max()),
        "deals_with_no_created_date": missing_count,
    }


def count_bulk_imports(df: pd.DataFrame) -> int:
    """Count Won deals matching the bulk-import pattern (Lead Generated stage + no value)."""
    if not all(
        col in df.columns for col in ["Deal Status", "Deal Stage", "_deal_value"]
    ):
        return 0
    mask = (
        (df["Deal Status"] == "Won")
        & (df["Deal Stage"] == "A. Lead Generated")
        & (df["_deal_value"].isna())
    )
    return int(mask.sum())
