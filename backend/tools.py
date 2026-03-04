TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_board_schema",
            "description": (
                "Get the list of columns (their IDs, titles, and types) for a Monday.com board. "
                "Call this first to learn the exact column titles before running any analysis. "
                "Use the returned column titles as keys in filters and group_by parameters."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The Monday.com board ID (numeric string).",
                    }
                },
                "required": ["board_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_deals_analysis",
            "description": (
                "Run a server-side analysis on the Deals board. "
                "Fetches data from Monday.com, applies filters, groups, and computes metrics using pandas. "
                "Returns only the computed result — never raw rows. "
                "Use this for pipeline overviews, sector breakdowns, win/loss rates, stage distributions, "
                "owner performance, and any other Deals-based metric."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "description": (
                            "Key-value pairs to filter rows before analysis. "
                            "Keys are column titles (e.g. 'Deal Status', 'Sector/service'). "
                            "Values are strings or lists of strings for multi-value filters. "
                            'Example: { "Deal Status": "Open", "Sector/service": ["Mining", "Renewables"] }'
                        ),
                    },
                    "group_by": {
                        "type": "string",
                        "description": (
                            "Column title to group results by. "
                            "Example: 'Deal Stage', 'Sector/service', 'Owner code', 'Closure Probability'"
                        ),
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of metrics to compute. Supported values: "
                            "'count' (number of rows), "
                            "'total_value' (sum of Masked Deal value, excluding nulls), "
                            "'avg_value' (mean of Masked Deal value, excluding nulls), "
                            "'null_value_count' (rows with no deal value), "
                            "'overdue_count' (open deals where Tentative Close Date is in the past), "
                            "'win_rate' (Won / (Won + Dead) as a percentage — a data_note flags bulk-imported records), "
                            "'weighted_pipeline_value' (sum of deal values × Closure Probability weight: High=0.8, Medium=0.5, Low=0.2, unknown=0.3), "
                            "'avg_deal_age_days' (mean days since Created Date for deals in the filtered set; also returns max_deal_age_days). "
                            "Always include 'count'. Include 'null_value_count' when computing value metrics."
                        ),
                    },
                    "date_range": {
                        "type": "object",
                        "description": (
                            "Optional time window filter applied before computing metrics. "
                            "Fields: 'column' (valid options: 'Created Date', 'Tentative Close Date', 'Close Date (A)'), "
                            "'from' (YYYY-MM-DD, inclusive), 'to' (YYYY-MM-DD, inclusive). "
                            'Example: { "column": "Created Date", "from": "2025-10-01", "to": "2025-12-31" }'
                        ),
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Metric to sort results by, descending. Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of groups to return. Optional. Use for 'top N' queries.",
                    },
                },
                "required": ["metrics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_workorders_analysis",
            "description": (
                "Run a server-side analysis on the Work Orders board. "
                "Fetches data from Monday.com, applies filters, groups, and computes metrics using pandas. "
                "Returns only the computed result — never raw rows. "
                "Use this for billing analysis, collections, AR, execution status, "
                "and any other Work Orders-based metric."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "description": (
                            "Key-value pairs to filter rows. "
                            "Keys are column titles (e.g. 'Execution Status', 'WO Status (billed)'). "
                            "Values are strings or lists of strings."
                        ),
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Column title to group by. Example: 'Execution Status', 'BD/KAM Personnel code'",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of metrics to compute. Supported values: "
                            "'count' (number of work orders), "
                            "'total_contract_value' (sum of Amount excl GST), "
                            "'total_billed' (sum of Billed Value excl GST), "
                            "'total_collected' (sum of Collected Amount incl GST), "
                            "'total_receivable' (sum of Amount Receivable), "
                            "'total_unbilled' (sum of Amount to be billed excl GST), "
                            "'billing_coverage' (total_billed / total_contract_value as %), "
                            "'collection_rate' (total_collected / total_billed as %). "
                            "Always include 'count'."
                        ),
                    },
                    "date_range": {
                        "type": "object",
                        "description": (
                            "Optional time window filter applied before computing metrics. "
                            "Fields: 'column' (valid options: 'Date of PO/LOI', 'Probable Start Date', 'Probable End Date'), "
                            "'from' (YYYY-MM-DD, inclusive), 'to' (YYYY-MM-DD, inclusive)."
                        ),
                    },
                    "sort_by": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["metrics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cross_board_analysis",
            "description": (
                "Join the Deals and Work Orders boards on Deal Name and run a combined analysis. "
                "Use this when the question requires data from both boards together — "
                "e.g. which won deals have work orders, deal value vs WO contract value, "
                "or execution status of deals in a specific sector. "
                "Join key: Deals.'Deal Name' = WorkOrders.'Deal name masked' (case-insensitive). "
                "Always reports orphaned WOs (Golden fish, Octopus, Whale, Turtle, Dolphin, GG go)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deals_filters": {
                        "type": "object",
                        "description": "Filters to apply to the Deals side before joining.",
                    },
                    "wo_filters": {
                        "type": "object",
                        "description": "Filters to apply to the Work Orders side before joining.",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Metrics to compute on the joined dataset. Supported: "
                            "'match_count' (deals with a matching WO), "
                            "'unmatched_deals_count' (deals with no WO), "
                            "'orphaned_wo_count' (WOs with no deal record), "
                            "'total_deal_value' (sum of deal values for matched records), "
                            "'total_wo_value' (sum of WO contract values for matched records), "
                            "'value_realization_rate' (total_wo_value / total_deal_value as %)."
                        ),
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Column from Deals side to group joined results by. Optional.",
                    },
                },
                "required": ["metrics"],
            },
        },
    },
]
