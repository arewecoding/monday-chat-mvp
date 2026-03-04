"""
Data cleaning functions for Deals and Work Orders DataFrames.
Encodes all cleaning rules from Section 5 of the Workflow Document.
Raw DataFrames never leave the server — only compact result dicts do.
"""

import pandas as pd
from datetime import date

TODAY = date.today()

# WO names that have no matching Deal record (known orphans from Workflow Doc §1.2)
ORPHANED_WOS = {"golden fish", "octopus", "whale", "turtle", "dolphin", "gg go"}

# Literal strings that indicate a duplicate header row in the Deals board
HEADER_LITERALS = {"deal stage", "deal status"}


# ── Deals Board ──────────────────────────────────────────────────────────────


def clean_deals_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all Deals board cleaning rules from Section 5.1 of the Workflow Document.
    Adds a canonical '_deal_value' column and an 'is_overdue' boolean column.
    """
    df = df.copy()

    # 1. Drop duplicate header rows
    #    Any row where Deal Stage or Deal Status literally says "Deal Stage"/"Deal Status"
    for col in ["Deal Stage", "Deal Status"]:
        if col in df.columns:
            mask = df[col].astype(str).str.strip().str.lower().isin(HEADER_LITERALS)
            df = df[~mask]

    # 2. Drop rows with blank Deal Name
    if "Deal Name" in df.columns:
        df = df[df["Deal Name"].astype(str).str.strip() != ""]
        df = df[df["Deal Name"].notna()]

    # 3. Normalize Deal Status and Deal Stage (strip whitespace)
    for col in [
        "Deal Status",
        "Deal Stage",
        "Sector/service",
        "Owner code",
        "Closure Probability",
    ]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", "")

    # 4. Parse Deal Value to float → stored in canonical '_deal_value' column
    value_col = _find_col(
        df,
        [
            "Masked Deal value",
            "Masked Deal Value",
            "Deal Value (Masked)",
            "Deal value",
            "Deal Value",
        ],
    )
    if value_col:
        df["_deal_value"] = pd.to_numeric(
            df[value_col].replace("", pd.NA), errors="coerce"
        )
    else:
        df["_deal_value"] = pd.NA

    # 5. Parse date columns
    for date_col in ["Close Date (A)", "Tentative Close Date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)

    # 6. Add is_overdue flag
    #    Open or On Hold deals where Tentative Close Date is before today
    df["is_overdue"] = False
    if "Deal Status" in df.columns and "Tentative Close Date" in df.columns:
        open_mask = df["Deal Status"].isin(["Open", "On Hold"])
        past_mask = df["Tentative Close Date"].dt.date < TODAY
        df["is_overdue"] = open_mask & past_mask.fillna(False)

    return df


# ── Work Orders Board ─────────────────────────────────────────────────────────


def clean_workorders_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all Work Orders board cleaning rules from Section 5.2 of the Workflow Document.
    Adds canonical financial columns: _contract_value, _billed, _collected,
    _receivable, _unbilled.
    """
    df = df.copy()

    # 1. Drop rows where every cell is blank (CSV export artifact — first blank row)
    df = df[
        ~df.astype(str).apply(lambda r: r.str.strip().isin(["", "nan"]).all(), axis=1)
    ]

    # 2. Replace #VALUE! cells with NaN (Excel formula error in SDPLDEAL-085)
    df = df.replace("#VALUE!", pd.NA)
    df = df.replace(r"#VALUE!", pd.NA, regex=False)

    # 3. Normalize Execution Status and Billing Status
    if "Execution Status" in df.columns:
        df["Execution Status"] = df["Execution Status"].astype(str).str.strip()
        df["Execution Status"] = df["Execution Status"].replace("nan", "")

    if "Billing Status" in df.columns:
        bs = df["Billing Status"].astype(str).str.strip()
        bs = bs.replace("BIlled", "Fully Billed")
        # "Billed- Visit 1/2/3/..." → "Partially Billed"
        bs = bs.str.replace(
            r"^Billed[-–\s]*Visit\s*\d*$", "Partially Billed", regex=True
        )
        bs = bs.replace("nan", "")
        df["Billing Status"] = bs

    # 4. Identify and cast financial columns → canonical private columns
    #    Multiple name variants are tried to handle minor import differences.
    _map_financial(
        df,
        "_contract_value",
        [
            "Amount in Rupees (Excl of GST) (Masked)",
            "Amount in Rupees (Excl of GST)(Masked)",
            "Amount (Excl of GST) (Masked)",
        ],
    )
    _map_financial(
        df,
        "_billed",
        [
            "Billed Value in Rupees (Excl of GST.) (Masked)",
            "Billed Value in Rupees (Excl of GST.)(Masked)",
            "Billed Value (Excl of GST.) (Masked)",
            "Billed Value (Excl GST) (Masked)",
        ],
    )
    _map_financial(
        df,
        "_collected",
        [
            "Collected Amount in Rupees (Incl of GST.) (Masked)",
            "Collected Amount in Rupees (Incl of GST.)(Masked)",
            "Collected Amount (Incl GST) (Masked)",
        ],
    )
    _map_financial(
        df,
        "_receivable",
        [
            "Amount Receivable (Masked)",
            "Amount Receivable(Masked)",
            "Amount Receivable",
        ],
    )
    _map_financial(
        df,
        "_unbilled",
        [
            "Amount to be billed in Rs. (Exl. of GST)",
            "Amount to be billed in Rs. (Excl. of GST)",
            "Amount to be billed (Excl GST)",
        ],
    )

    return df


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_col(df: pd.DataFrame, candidates: list) -> str | None:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    # Fallback: partial match (case-insensitive)
    for c in candidates:
        for col in df.columns:
            if c.lower() in col.lower():
                return col
    return None


def _map_financial(df: pd.DataFrame, canonical: str, candidates: list) -> None:
    """
    Find the first matching column from candidates, cast it to float,
    and store the result in df[canonical]. In-place.
    """
    col = _find_col(df, candidates)
    if col:
        df[canonical] = pd.to_numeric(df[col].replace("", pd.NA), errors="coerce")
    else:
        df[canonical] = pd.NA
