"""
analysis/crossboard.py — Server-side analysis joining Deals and Work Orders boards.
Joins on Deal Name (case-insensitive). Raw rows never leave this module.
"""

import pandas as pd

from monday import get_all_deals, get_all_workorders
from clean import clean_deals_df, clean_workorders_df, ORPHANED_WOS


# ── Entry point ───────────────────────────────────────────────────────────────


def execute_cross_board_analysis(args: dict) -> dict:
    """Join Deals + Work Orders on Deal Name; compute and return cross-board metrics."""
    deals_df, wo_df = _fetch_and_clean_both()

    deals_df = _apply_board_filters(deals_df, args.get("deals_filters", {}))
    wo_df = _apply_board_filters(wo_df, args.get("wo_filters", {}))

    # Normalise join keys: lowercase + trimmed so "Deal Name" matches "deal name masked"
    deals_df["_jk"] = deals_df["Deal Name"].astype(str).str.strip().str.lower()
    wo_df["_jk"] = wo_df["Deal name masked"].astype(str).str.strip().str.lower()

    orphaned_mask = wo_df["_jk"].isin(ORPHANED_WOS)

    merged = deals_df.merge(wo_df, on="_jk", how="outer", suffixes=("_deal", "_wo"))
    matched = merged[merged["Deal Name"].notna() & merged["Deal name masked"].notna()]
    unmatched_deals = merged[
        merged["Deal name masked"].isna() & merged["Deal Name"].notna()
    ]

    result = _compute_cross_metrics(
        matched,
        unmatched_deals,
        wo_df,
        orphaned_mask,
        args.get("metrics", ["match_count"]),
    )

    if args.get("group_by") and args["group_by"] in matched.columns:
        result["groups"] = _group_cross(matched, args["group_by"])

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fetch_and_clean_both() -> tuple:
    """Fetch and clean both boards from Monday.com; returns (deals_df, wo_df)."""
    deals_df = clean_deals_df(pd.DataFrame(get_all_deals()))
    wo_df = clean_workorders_df(pd.DataFrame(get_all_workorders()))
    return deals_df, wo_df


def _apply_board_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply simple equality/membership filters to one board's DataFrame; returns filtered df."""
    for col, val in filters.items():
        if col in df.columns:
            df = df[df[col].isin(val)] if isinstance(val, list) else df[df[col] == val]
    return df


def _compute_cross_metrics(
    matched: pd.DataFrame,
    unmatched_deals: pd.DataFrame,
    wo_df: pd.DataFrame,
    orphaned_mask: pd.Series,
    metrics: list,
) -> dict:
    """Compute all requested cross-board metrics; returns result dict with data_notes."""
    orphaned_names = list(wo_df[orphaned_mask]["Deal name masked"].unique())
    result = {
        "data_notes": [
            "Join key: Deal Name (Deals) = Deal name masked (Work Orders)",
            f"Orphaned WOs (no matching deal): {orphaned_names}",
        ]
    }

    if "match_count" in metrics:
        result["match_count"] = int(len(matched))
    if "unmatched_deals_count" in metrics:
        result["unmatched_deals_count"] = int(len(unmatched_deals))
    if "orphaned_wo_count" in metrics:
        result["orphaned_wo_count"] = int(orphaned_mask.sum())
        result["orphaned_wo_names"] = orphaned_names

    deal_vals = (
        matched["_deal_value"].dropna()
        if "_deal_value" in matched.columns
        else pd.Series([], dtype=float)
    )
    has_wo_value = "_contract_value" in matched.columns
    wo_vals = (
        matched["_contract_value"].dropna()
        if has_wo_value
        else pd.Series([], dtype=float)
    )

    if "total_deal_value" in metrics:
        result["total_deal_value"] = float(deal_vals.sum())
        result["deals_with_no_value"] = int(len(matched) - len(deal_vals))
    if "total_wo_value" in metrics:
        result["total_wo_value"] = float(wo_vals.sum()) if has_wo_value else None
    if "value_realization_rate" in metrics:
        deal_total = float(deal_vals.sum())
        wo_total = float(wo_vals.sum()) if has_wo_value else 0.0
        result["value_realization_rate_pct"] = (
            round(wo_total / deal_total * 100, 1) if deal_total > 0 else None
        )

    return result


def _group_cross(matched: pd.DataFrame, group_by: str) -> list:
    """Group matched records by a column and count per group; returns sorted list of dicts."""
    groups = [
        {group_by: val, "match_count": int(len(grp))}
        for val, grp in matched.groupby(group_by, sort=False)
    ]
    return sorted(groups, key=lambda x: x["match_count"], reverse=True)
