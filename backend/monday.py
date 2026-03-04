import os
import httpx

MONDAY_API = "https://api.monday.com/v2"


def gql(query: str) -> dict:
    """Send a GraphQL query to Monday.com and return the data."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": os.environ["MONDAY_API_KEY"],
        "API-Version": "2025-04",
    }
    response = httpx.post(
        MONDAY_API, json={"query": query}, headers=headers, timeout=30
    )
    data = response.json()
    if "errors" in data:
        raise Exception(f"Monday API error: {data['errors']}")
    return data["data"]


def get_board_schema(board_id: str) -> dict:
    """Get column IDs, names, and types for a board. Call this before get_board_items."""
    data = gql(f"""
        query {{
          boards(ids: [{board_id}]) {{
            name
            columns {{ id title type }}
          }}
        }}
    """)
    board = data["boards"][0]
    return {"board_name": board["name"], "columns": board["columns"]}


def get_board_items(board_id: str, column_ids: list) -> dict:
    """Fetch all rows from a board, requesting only the columns you specify."""
    ids = ", ".join(f'"{c}"' for c in column_ids)
    data = gql(f"""
        query {{
          boards(ids: [{board_id}]) {{
            items_page(limit: 500) {{
              items {{
                id
                name
                column_values(ids: [{ids}]) {{ id text }}
              }}
            }}
          }}
        }}
    """)
    items = data["boards"][0]["items_page"]["items"]
    return {"items": items}


def search_board(board_id: str, column_id: str, value: str) -> dict:
    """Fetch rows filtered by a specific column value. Efficient for sector/status filters."""
    data = gql(f"""
        query {{
          items_page_by_column_values(
            board_id: {board_id},
            limit: 500,
            columns: [{{ column_id: "{column_id}", column_values: ["{value}"] }}]
          ) {{
            items {{
              id
              name
              column_values {{ id text }}
            }}
          }}
        }}
    """)
    items = data["items_page_by_column_values"]["items"]
    return {"items": items}


# ── Server-side analysis helpers ─────────────────────────────────────────────
# These are called by the execution functions in main.py.
# Raw rows NEVER leave the server — they are only used to build DataFrames.


def get_all_items_as_dicts(board_id: str, name_col: str) -> list:
    """
    Fetch all items from a board in a single GraphQL call (schema + items combined).
    Returns a list of flat dicts with column titles as keys.
    The item's primary name field is stored under name_col.
    """
    data = gql(f"""
        query {{
          boards(ids: [{board_id}]) {{
            columns {{ id title }}
            items_page(limit: 500) {{
              items {{
                id
                name
                column_values {{ id text }}
              }}
            }}
          }}
        }}
    """)
    board = data["boards"][0]
    col_map = {col["id"]: col["title"] for col in board["columns"]}
    items = board["items_page"]["items"]

    rows = []
    for item in items:
        row = {name_col: item["name"]}
        for cv in item["column_values"]:
            title = col_map.get(cv["id"], cv["id"])
            row[title] = cv["text"] if cv["text"] else ""
        rows.append(row)
    return rows


def get_all_deals() -> list:
    """Fetch all Deals board rows as flat dicts (for server-side analysis only)."""
    return get_all_items_as_dicts(os.environ["DEALS_BOARD_ID"], name_col="Deal Name")


def get_all_workorders() -> list:
    """Fetch all Work Orders board rows as flat dicts (for server-side analysis only)."""
    return get_all_items_as_dicts(
        os.environ["WORKORDERS_BOARD_ID"], name_col="Deal name masked"
    )
