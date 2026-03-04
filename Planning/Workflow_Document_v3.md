# Monday.com BI Agent — Complete Workflow Document (v3)
**Stack:** Svelte (frontend, Vercel) · Python FastAPI (backend, Railway) · Groq (Llama 4 Scout) · Monday.com GraphQL API
**Model:** `meta-llama/llama-4-scout-17b-16e-instruct`
**Constraint:** Free tier only. No caching. All queries live.

---

## 1. What We're Actually Working With

Before anything architectural, understanding the data is the most important thing.
The agent's entire intelligence depends on knowing what's real, what's missing,
and what's structurally broken in this dataset.

### 1.1 Deals Board — Ground Truth

**346 rows** across three lifecycle states:

| Status | Count | What it means |
|---|---|---|
| Won | 165 | Closed successfully — deal converted |
| Dead | 127 | Lost, irrelevant, or abandoned |
| Open | 49 | Active pipeline — the most important set |
| On Hold / Blank | 5 | Ambiguous |

**Sectors present:** Mining (106), Renewables (111), Railways (40), Powerline (26),
DSP (7), Construction (9), Tender (5), Others (28), Aviation (1), Manufacturing (2),
Security & Surveillance (1)

**Deal stages (full pipeline alphabet):**
```
A. Lead Generated
B. Sales Qualified Leads
C. Demo Done
D. Feasibility
E. Proposal/Commercials Sent
F. Negotiations
G. Project Won
H. Work Order Received
I. POC
J. Invoice sent
K. Amount Accrued
L. Project Lost
M. Projects On Hold
N. Not relevant at the moment
O. Not Relevant at all
```
Plus non-standard values: "Project Completed" (used in Won deals)

**Critical Data Quality Issues in Deals:**
1. **Two duplicate header rows embedded mid-file** (at rows 51 and 180). The "Deal
   Name" column contains column header text for those rows. Must be filtered out
   before any analysis.
2. **181/346 rows have no Deal Value** — over half the dataset. Most are Won deals at
   "A. Lead Generated" stage (bulk-imported historical wins with no value recorded).
   This is expected, not an error. Infer that value wasn't captured, not that it's zero.
3. **318/346 rows have no actual Close Date** — normal for Open/Dead deals. Close Date
   only exists for truly closed (Won) deals.
4. **258/346 rows have no Closure Probability** — particularly common in Dead deals
   (where it's irrelevant) and older Won deals.
5. **17 rows missing Owner code** — mostly older Dead deals.
6. **2 rows missing Deal Name entirely** — treat as unparseable, skip them.
7. **"Tender" is a sector** — not a deal type. Some very large deals (100M+ INR) are
   categorised here. Don't confuse with document type.
8. **"On Hold" deals** have Deal Stage "M. Projects On Hold" and no close date —
   treat these as a special sub-state of Open, not Dead.
9. **Tentative Close Dates in the past** for Open deals — this means the deal is
   overdue. Do not treat past Tentative Close Date as closed; it means slippage.
10. **Values are in Indian Rupees (INR), masked** — don't label as USD. The word
    "Masked" in the column name indicates values are scaled but proportions are real.

---

### 1.2 Work Orders Board — Ground Truth

**176 rows** (after stripping the completely blank first row — a CSV export artifact).

**Execution Statuses:**
- Completed: 117
- Ongoing: 25
- Executed until current month: 12 (recurring contracts currently active)
- Not Started: 11
- Pause / struck: 4
- Partial Completed: 2
- Details pending from Client: 1
- Blank: 4

**WO Status (billing perspective):**
- Closed: 78
- Open: 24
- Blank: 74 (mostly older or incomplete records)

**Critical Data Quality Issues in Work Orders:**
1. **Completely blank first row** — CSV export artifact. Must skip before parsing.
2. **One `#VALUE!` cell** in SDPLDEAL-085 (Luffy) — an Excel formula error exported
   as text. Treat the Amount field for this row as null.
3. **Billing Status mostly blank (148/176)** — only 28 rows have a billing status.
   The primary billing signal is the WO Status (Open/Closed) column instead.
4. **Billing Status values are inconsistent:** "Fully Billed", "BIlled" (wrong caps),
   "Partially Billed", "Not billed yet", "Not Billable", "Update Required", "Stuck",
   "Billed- Visit 3". Normalize these to: fully_billed, partially_billed,
   not_billed, not_billable, stuck, update_required.
5. **Quantity units are mixed and free-text:** "HA", "Acres", "RKM", "KM", "towers",
   "MW", "5360 HA", "98000 Acres". Never sum quantities across rows — they're
   incomparable. Count rows instead.
6. **6 Work Orders have no matching Deal record:** Golden fish, Octopus, Whale,
   Turtle, Dolphin, GG go. These are orphaned WOs. Report them as such when
   doing cross-board analysis.
7. **Nature of Work missing for some rows** (SDPLDEAL-111 through 124 range) —
   these appear to be older records imported with less structure.
8. **WOCOMPANY_XXX ≠ COMPANY_XXX** — the customer code masking scheme is
   different between the two boards. Do not attempt to join on customer code.

---

### 1.3 The Join Key (Critical)

**The only reliable join between the two boards is: Deal Name (Deals) = Deal name
masked (Work Orders)**

- 155 unique deal names exist in Deals
- 58 unique deal names exist in Work Orders
- **52 match** — these represent deals that progressed to work orders
- 6 WO names have no deal record (orphaned)
- 103 deal names have no WO yet (pipeline that hasn't converted to execution)

This join is imperfect — some deal names like "Alias_160", "Alias_162" are
anonymized aliases that may represent multiple real deals but have multiple WO
records each. The agent must handle this gracefully and report when a join
produces multiple-to-multiple matches.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (User)                           │
│   ┌──────────────────────┐    ┌──────────────────────────┐     │
│   │     Chat Panel       │    │     Action Log Panel     │     │
│   └──────────┬───────────┘    └──────────────────────────┘     │
└──────────────┼──────────────────────────────────────────────────┘
               │ POST /chat (fetch to Railway URL)
┌──────────────▼──────────────────────────────────────────────────┐
│           PYTHON FASTAPI BACKEND (Railway)                      │
│  1. Receives message + conversation history                     │
│  2. Runs tool-calling loop with Groq                            │
│  3. Executes Monday.com GraphQL calls per tool invocation       │
│  4. Streams back tool events + final answer (NDJSON)            │
└──────────┬───────────────────┬──────────────────────────────────┘
           │                   │
    GROQ API              MONDAY.COM API
  Llama 4 Scout 17B      https://api.monday.com/v2
  (tool-calling)         (GraphQL, Bearer auth)

┌─────────────────────────────────────────────────────────────────┐
│              SVELTE FRONTEND (Vercel — static)                  │
│  Pure UI: renders chat + action log, calls FastAPI backend      │
└─────────────────────────────────────────────────────────────────┘
```

**Two deployments:**
- **Vercel** — hosts the Svelte frontend as a static site
- **Railway** — hosts the Python FastAPI backend (free tier: 500 hrs/month)

The frontend's API URL points to the Railway backend via an environment variable
set in Vercel's dashboard (`PUBLIC_API_URL=https://your-app.railway.app`).

---

## 3. File Structure

```
monday-bi-agent/
│
├── backend/                          ← Python FastAPI (deploy to Railway)
│   ├── main.py                       ← FastAPI app + /chat endpoint + agent loop
│   ├── monday.py                     ← Monday.com GraphQL functions
│   ├── tools.py                      ← Tool schema definitions for Groq
│   ├── prompts.py                    ← System prompt
│   ├── requirements.txt              ← Python dependencies
│   └── .env                          ← Local secrets (never committed)
│
├── frontend/                         ← Svelte app (deploy to Vercel)
│   ├── src/
│   │   ├── App.svelte                ← Chat UI + Action Log (single component)
│   │   └── main.js                   ← Entry point
│   ├── public/
│   │   └── index.html
│   ├── .env                          ← PUBLIC_API_URL=https://your-app.railway.app
│   ├── vite.config.js
│   └── package.json
│
└── README.md
```

**Backend dependencies (`requirements.txt`):**
```
fastapi
uvicorn
groq
httpx
python-dotenv
```

**Backend env vars (set in Railway dashboard):**
```
GROQ_API_KEY=gsk_...
MONDAY_API_KEY=eyJ...
DEALS_BOARD_ID=...
WORKORDERS_BOARD_ID=...
```

**Frontend env vars (set in Vercel dashboard):**
```
PUBLIC_API_URL=https://your-app.railway.app
```

---

## 4. The Three Tools

### Tool 1: `get_board_schema`
Fetches column IDs and types for a board. Always called first.

```graphql
query {
  boards(ids: [BOARD_ID]) {
    name
    columns { id title type }
  }
}
```

### Tool 2: `get_board_items`
Fetches all rows with selected columns. Used for broad analysis.

```graphql
query {
  boards(ids: [BOARD_ID]) {
    items_page(limit: 500) {
      items {
        id
        name
        column_values(ids: ["col1", "col2"]) { id text }
      }
    }
  }
}
```

Always use `text` not `value`. `text` returns human-readable strings.
Agent selects only columns needed for the specific question.

### Tool 3: `search_board`
Filtered fetch by column value. Used for sector/status/stage filters.

```graphql
query {
  items_page_by_column_values(
    board_id: BOARD_ID,
    limit: 500,
    columns: [{ column_id: "col_id", column_values: ["filter_value"] }]
  ) {
    items { id name column_values { id text } }
  }
}
```

---

## 5. Data Cleaning Layer (In-Context, Via System Prompt)

The agent receives raw Monday.com data and must clean it before analysis.
This happens entirely in the LLM context — no pre-processing code needed.

### 5.1 Deals Board Cleaning Rules

```
BEFORE ANY ANALYSIS on Deals data:

1. REMOVE DUPLICATE HEADER ROWS
   Any row where the "Deal Stage" or "Deal Status" column contains the literal
   text "Deal Stage" or "Deal Status" is a duplicate header. Remove it entirely.

2. REMOVE BLANK DEAL NAMES
   Any row where Deal Name is empty or whitespace — skip it.

3. NORMALIZE DEAL STATUS
   Valid values: Open, Won, Dead, On Hold
   "On Hold" → treat as a sub-type of Open (not closed, not dead)
   Blank status → flag as "unknown" in your response

4. NORMALIZE DEAL STAGES
   Strip leading/trailing whitespace.
   The letter prefix (A., B., C...) is the authoritative ordering.
   "Project Completed" = treat same as "G. Project Won" or later

5. PARSE DEAL VALUES
   Strip whitespace. If empty or blank → null (do not treat as 0).
   Do NOT sum values that include nulls without noting the exclusion.
   Values are in INR (Indian Rupees), masked for confidentiality.

6. PARSE DATES
   "Close Date (A)": actual close date, blank for most → expected, not an error
   "Tentative Close Date": target/forecast date
   If Tentative Close Date is in the past for an Open deal → flag as "overdue"
   Parse any date format to a comparable value (YYYY-MM-DD).

7. NORMALIZE CLOSURE PROBABILITY
   Values: High, Medium, Low, blank
   Blank → unknown (not Low)

8. NORMALIZE SECTORS
   Strip whitespace. Treat case-insensitively.
   "Sector/service" text value in a row = duplicate header artifact, skip.

9. INTERPRET "TENDER" AS A SECTOR
   Some very large deals are in sector "Tender". This is a legitimate sector
   category in this company, not a document type.
```

### 5.2 Work Orders Board Cleaning Rules

```
BEFORE ANY ANALYSIS on Work Orders data:

1. SKIP BLANK FIRST ROW
   The very first data row (before the actual header) is completely blank.
   The Monday.com CSV export includes it as an artifact. Ignore it.

2. HANDLE #VALUE! CELLS
   If any amount field contains "#VALUE!", treat that field as null for
   that row. This is an Excel formula error. Report it to the user.
   Affected: SDPLDEAL-085 (Luffy) — Amount field null.

3. NORMALIZE EXECUTION STATUS
   Group for reporting:
   - Active: "Ongoing", "Executed until current month", "Not Started",
     "Details pending from Client"
   - Complete: "Completed", "Partial Completed"
   - Blocked: "Pause / struck"
   - Unknown: blank

4. NORMALIZE BILLING STATUS
   These values mean the same thing — normalize them:
   "BIlled" → "Fully Billed" (typo/caps issue)
   "Billed- Visit 3", "Billed- Visit 7" → "Partially Billed"
   Blank → unknown (most rows; don't treat as unbilled)
   Use WO Status (Open/Closed) as a proxy when Billing Status is blank.

5. DO NOT SUM QUANTITIES
   Quantity fields have mixed units (HA, Acres, KM, Towers, MW).
   Never aggregate them. Count work order rows instead.

6. FINANCIAL FIELDS — use the right column:
   For revenue analysis:
   - "Amount in Rupees (Excl of GST) (Masked)" = contract value
   - "Billed Value in Rupees (Excl of GST.) (Masked)" = invoiced so far
   - "Collected Amount in Rupees (Incl of GST.) (Masked)" = cash received
   - "Amount to be billed in Rs. (Exl. of GST)" = remaining to invoice
   - "Amount Receivable (Masked)" = invoiced but not yet collected (AR)
   Always specify which field you used in your response.

7. ORPHANED WORK ORDERS
   These deal names appear in Work Orders but NOT in Deals:
   Golden fish, Octopus, Whale, Turtle, Dolphin, GG go
   When doing cross-board analysis, flag these as orphaned. They may be
   old records, test data, or deals not yet added to the Deals board.
```

---

## 6. Analysis Taxonomy

The agent maps every user question to one or more analysis types. Each type
has a defined approach, required fields, and known caveats.

### Type 1: Pipeline Health Analysis
**Triggered by:** "How's our pipeline?", "What's in the funnel?",
"Pipeline overview", "Active deals"

**Data source:** Deals board, Status = Open + On Hold
**Required fields:** Deal Stage, Sector, Masked Deal Value, Closure Probability,
Tentative Close Date, Owner code

**Approach:**
1. Filter to Open + On Hold deals
2. Group by Deal Stage — show count and total value per stage
3. Calculate weighted pipeline: sum(Value × probability weight) where
   High=0.8, Medium=0.5, Low=0.2, Unknown=0.3
4. Flag overdue deals (Tentative Close Date in past)
5. Flag deals with no value (can't be weighted)

**Caveats to always report:**
- How many Open deals have no value recorded
- How many have no closure probability
- Which deals are overdue (Tentative Close Date passed)

**Insight angle:**
- Which stage has the most value stuck?
- Are high-probability deals close to closing or still early stage?
- What % of pipeline has an overdue close date?

---

### Type 2: Sectoral Performance Analysis
**Triggered by:** "Energy sector", "Mining pipeline", "Which sector is strongest?",
"Renewables performance"

**Data source:** Deals board (all statuses), optionally Work Orders for revenue
**Required fields:** Sector/service, Deal Status, Masked Deal Value, Deal Stage

**Approach:**
1. Fetch all deals, group by sector
2. For each sector: count by status (Won/Open/Dead), total value won, total
   value in pipeline, win rate (Won / (Won + Dead))
3. For cross-board: fetch matching WOs, show execution value per sector

**Caveats:**
- "Tender" sector deals are often very large single deals — don't let them
  distort per-deal averages without flagging the skew
- Many Won deals have no value — win rate by count vs. win rate by value
  are very different metrics; report both

**Insight angle:**
- Is win rate higher in certain sectors?
- Which sector has the most value stuck in mid-funnel?
- Is execution (WO board) keeping pace with deal wins?

---

### Type 3: Win/Loss Analysis
**Triggered by:** "Win rate", "Lost deals", "Why are we losing?",
"Dead deals analysis", "Conversion rate"

**Data source:** Deals board, Status = Won or Dead
**Required fields:** Deal Status, Deal Stage, Sector, Owner code,
Masked Deal Value, Tentative Close Date

**Approach:**
1. Separate Won vs Dead
2. Win rate = Won count / (Won + Dead count) — by sector, by owner
3. For Dead deals: group by final Deal Stage (where in funnel did we lose?)
4. Value lost: sum of Dead deal values (noting how many are null)
5. For Won deals with stage "A. Lead Generated" and no value: these are
   likely bulk-imported historical records — treat separately, flag to user

**Critical nuance:**
- Won deals with no value and stage "A. Lead Generated" = likely bulk import
  of historical wins without value data. Don't average these in with valued wins.
- Dead deals at stage M/N/O = abandoned before serious pursuit (not really "lost")
- Dead deals at stage L = genuinely lost (competed and failed)

**Insight angle:**
- At what funnel stage are most deals being lost?
- Is there a sector where loss rate is unusually high?
- Which owner has the best conversion rate?

---

### Type 4: Revenue & Billing Analysis
**Triggered by:** "Revenue", "How much have we billed?", "Collections",
"Outstanding payments", "AR", "Cash flow"

**Data source:** Work Orders board
**Required fields:** Amount excl GST, Billed Value excl GST, Collected Amount,
Amount Receivable, WO Status, Execution Status, Sector

**Approach:**
1. Total contracted value = sum of "Amount in Rupees (Excl of GST)"
   (skip #VALUE! and null rows, report exclusions)
2. Total billed = sum of "Billed Value in Rupees (Excl of GST)"
3. Total collected = sum of "Collected Amount (Incl of GST)"
4. Total AR (outstanding) = sum of "Amount Receivable"
5. Unbilled contracted = sum of "Amount to be billed (Excl of GST)"
6. Billing coverage = Billed / Contracted (what % has been invoiced)
7. Collection rate = Collected / Billed (what % of invoices are paid)

**Caveats:**
- Values are masked (scaled) — report relative proportions, not absolutes
- GST-inclusive vs exclusive: always use the same basis for comparisons
- Billing Status is blank for 148/176 rows — use WO Status as proxy
- POC (Proof of Concept) entries often have 0 value — flag as non-revenue

**Insight angle:**
- What's the billing gap (contracted but not yet invoiced)?
- What's the collection gap (invoiced but not yet paid)?
- Which sector has the worst collection rate?
- Are any Priority AR accounts (flagged in AR Priority column) outstanding?

---

### Type 5: Operational Performance Analysis
**Triggered by:** "Project status", "Execution health", "Stuck projects",
"Ongoing work orders", "Delivery performance"

**Data source:** Work Orders board
**Required fields:** Execution Status, WO Status, Nature of Work, Sector,
Probable Start/End Date, Data Delivery Date

**Approach:**
1. Group by Execution Status (Completed / Active / Blocked / Unknown)
2. Identify stuck/paused projects (Execution Status = "Pause / struck")
3. Identify overdue projects: Probable End Date passed but not Completed
4. Group by Nature of Work: One time, Monthly, Annual, POC
5. For recurring (Monthly/Annual): "Executed until current month" = healthy

**Critical flags:**
- "Pause / struck" execution status = projects with blockers
- "Update Required" billing status = data integrity issue in Monday.com
- "Details pending from Client" = blocked externally

**Insight angle:**
- What % of active work orders are behind schedule?
- How many projects are stuck and need attention?
- What's the mix of one-time vs recurring revenue?

---

### Type 6: Owner / Personnel Performance Analysis
**Triggered by:** "Who's performing best?", "Owner analysis", "Top sales person",
"Team performance"

**Data source:** Deals board (Owner code), Work Orders (BD/KAM Personnel code)
**Required fields:** Owner code, Deal Status, Deal Value, Deal Stage, Sector

**Approach:**
1. Group deals by Owner code
2. Per owner: count Open/Won/Dead, total won value, pipeline value, win rate
3. Closure probability distribution (how many High/Medium/Low deals)
4. Cross with WO: which owner's deals generate the most execution work?

**Caveats:**
- Owner codes are anonymized (OWNER_001 etc.) — report by code, not name
- OWNER_003 dominates the dataset — this is likely the most senior BD person
- Some rows have blank Owner — these can't be attributed

---

### Type 7: Cross-Board Analysis (Deal-to-Execution)
**Triggered by:** "Which deals became work orders?", "Deal to execution pipeline",
"Revenue realization", "Show work orders for [deal/sector]"

**Data source:** Both boards
**Join:** Deals.Deal Name = WorkOrders."Deal name masked"

**Approach:**
1. Fetch Deals with needed fields
2. Fetch Work Orders with needed fields
3. Join on deal name (case-insensitive, trimmed)
4. For matched records: show deal value vs. WO contracted value
   (these may differ — deal value is expected, WO value is actual)
5. Calculate realization rate: WO Value / Deal Value
6. Flag unmatched: deals with no WO (not yet executed) and
   WOs with no deal record (orphaned — list the 6 known ones)

**Known orphaned WOs (no deal record):**
Golden fish, Octopus, Whale, Turtle, Dolphin, GG go
These 6 should always be flagged in cross-board results.

**Insight angle:**
- What % of Won deals have a corresponding work order?
- Is the WO value close to the deal value (good estimation accuracy)?
- Which Won deals are missing WOs (revenue not yet captured)?

---

## 7. The Inference Layer

Raw analysis produces numbers. The agent's job is to produce *insights*.
This is what the system prompt must instruct for every response.

### 7.1 From Numbers to Insights — Rules

```
After computing any metric, always ask and answer:
1. "Is this good or bad?" — provide context or comparison
   e.g. "A 38% win rate on valued deals is the baseline; by sector, Mining
        sits at 42% while Powerline is at 29% — that's a gap worth noting."

2. "What's the trend signal?" — even without time series, the stage
   distribution tells a story
   e.g. "With 14 deals stuck in E. Proposal stage, the bottleneck appears
        to be at the commercial approval phase, not lead generation."

3. "What's the risk?" — flag things that look problematic
   e.g. "3 high-probability deals have tentative close dates that have
        already passed — these need follow-up."

4. "What should the founder do with this?" — one actionable takeaway
   e.g. "The Renewables sector has the most open pipeline value but the
        lowest closure probability average — worth a pipeline review call."
```

### 7.2 Handling Ambiguous Questions

Some founder-level questions are intentionally vague. The agent must resolve
ambiguity by:

1. **Making an explicit assumption** and stating it
   e.g. "I'll interpret 'pipeline' as Open deals only (49 deals), not
        including Won or Dead."

2. **Asking ONE clarifying question** if the ambiguity changes the answer
   fundamentally
   e.g. "When you say 'revenue', do you mean contracted WO value, what's
        been billed, or what's been collected? These are different numbers."

3. **Providing the most useful interpretation** if asking would be annoying
   e.g. For "how are we doing?" → don't ask, just give a multi-part
        executive summary: pipeline, recent wins, execution health.

### 7.3 Multi-Turn Context

The agent must maintain conversation state for follow-up queries:
- "Show top deals" → agent fetches and shows deals
- "Now filter by energy" → agent knows "energy" = Renewables sector in this
  company's taxonomy, re-queries with that filter
- "What about their work orders?" → agent knows "their" refers to the
  previously filtered Renewables deals, fetches matching WOs

The Groq messages array (conversation history) is passed with every request,
so Llama 4 Scout has full context. No special state management needed.

### 7.4 Data Quality Communication

The agent must always communicate data limitations. Format:
- Lead with the insight
- Follow with supporting numbers
- Close with a data caveat if relevant

Example good response format:
```
Your Mining sector pipeline is the strongest by volume — 18 open deals
totalling ~₹45M in pipeline value.

Of those 18:
• 6 are at Proposal stage (highest value concentration)
• 4 are high probability, 5 medium, 9 unknown
• 3 have overdue tentative close dates

⚠️ Data note: 7 of the 18 open Mining deals have no value recorded, so
the ₹45M figure excludes them. The real pipeline could be significantly higher.
```

---

## 8. The Agent Loop

The tool-calling loop lives in `backend/main.py`. It is the core of the agent.
Groq decides which tools to call, the backend executes them against Monday.com,
feeds results back to Groq, and repeats until Groq stops calling tools.

```
User message → POST /chat
       │
       ▼
Build: [system_prompt, ...conversation_history, user_message]
       │
       ▼
Call Groq with messages + 3 tool definitions
       │
       ▼
┌─────────────────────────────────┐
│  finish_reason == "tool_calls"  │
└──────────────┬──────────────────┘
               │ YES
               ▼
  For each tool_call:
    ① yield { type:"tool_start", tool, args } → browser (action log)
    ② Execute: monday.py → httpx → Monday.com GraphQL
    ③ yield { type:"tool_done", summary } → browser
    ④ Append tool result to messages list
               │
               ▼
  Call Groq again (now has tool results in context)
               │
               └────────────────► repeat until finish_reason == "stop"
                                          │
                                          ▼
                               yield { type:"answer", content }
                               StreamingResponse ends
```

**`backend/main.py` — core structure:**
```python
import json
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from groq import Groq
from monday import get_board_schema, get_board_items, search_board
from tools import TOOL_DEFINITIONS
from prompts import build_system_prompt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down to your Vercel URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

class ChatRequest(BaseModel):
    messages: list

def execute_tool(name: str, args: dict):
    if name == "get_board_schema":
        return get_board_schema(args["board_id"])
    elif name == "get_board_items":
        return get_board_items(args["board_id"], args["column_ids"])
    elif name == "search_board":
        return search_board(args["board_id"], args["column_id"], args["value"])
    return {"error": f"Unknown tool: {name}"}

def summarize_result(name: str, result: dict) -> str:
    if name == "get_board_schema":
        cols = len(result.get("columns", []))
        return f"{cols} columns found"
    elif name == "get_board_items":
        items = len(result.get("items", []))
        return f"{items} items returned"
    elif name == "search_board":
        items = len(result.get("items", []))
        return f"{items} matching items"
    return "Done"

async def agent_stream(messages: list):
    current_messages = [
        {"role": "system", "content": build_system_prompt()},
        *messages
    ]

    while True:
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=current_messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )

        choice = response.choices[0]

        # Groq is done — stream final answer
        if choice.finish_reason == "stop":
            yield json.dumps({
                "type": "answer",
                "content": choice.message.content
            }) + "\n"
            break

        # Groq wants to call tools
        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls
            current_messages.append(choice.message)  # append assistant turn

            for tool_call in tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                # Tell browser a tool is starting
                yield json.dumps({
                    "type": "tool_start",
                    "tool": name,
                    "args": args
                }) + "\n"

                # Execute against Monday.com
                result = execute_tool(name, args)

                # Tell browser the tool finished
                yield json.dumps({
                    "type": "tool_done",
                    "tool": name,
                    "summary": summarize_result(name, result)
                }) + "\n"

                # Feed result back into conversation
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
            # Loop back — Groq will process tool results and decide next step

@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        agent_stream(request.messages),
        media_type="application/x-ndjson"
    )
```

**`backend/monday.py` — Monday.com GraphQL calls:**
```python
import os
import httpx

MONDAY_API = "https://api.monday.com/v2"

def gql(query: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": os.environ["MONDAY_API_KEY"],
        "API-Version": "2025-04"
    }
    response = httpx.post(MONDAY_API, json={"query": query}, headers=headers)
    data = response.json()
    if "errors" in data:
        raise Exception(f"Monday API error: {data['errors']}")
    return data["data"]

def get_board_schema(board_id: str) -> dict:
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
```

**`backend/tools.py` — Tool definitions for Groq:**
```python
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_board_schema",
            "description": (
                "Get the list of columns (their IDs and human-readable names) for a "
                "Monday.com board. Always call this before get_board_items so you know "
                "which column IDs to request. Use 'deals' or 'workorders' as board_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The Monday.com board ID from environment variables."
                    }
                },
                "required": ["board_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_board_items",
            "description": (
                "Fetch all items (rows) from a Monday.com board. "
                "Pass only the column IDs you need for the analysis. "
                "Use column IDs from get_board_schema, not column titles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {"type": "string"},
                    "column_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of column IDs to fetch."
                    }
                },
                "required": ["board_id", "column_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_board",
            "description": (
                "Fetch items from a Monday.com board filtered by a specific column value. "
                "Use for sector, status, stage, or company filters. More efficient than "
                "fetching all items when you need a specific subset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {"type": "string"},
                    "column_id": {
                        "type": "string",
                        "description": "The column ID to filter by."
                    },
                    "value": {
                        "type": "string",
                        "description": "The exact value to filter for."
                    }
                },
                "required": ["board_id", "column_id", "value"]
            }
        }
    }
]
```

**`backend/prompts.py`:**
```python
import os

def build_system_prompt() -> str:
    deals_id = os.environ["DEALS_BOARD_ID"]
    wo_id = os.environ["WORKORDERS_BOARD_ID"]
    return f"""
You are a business intelligence agent for a founder/executive...
[full system prompt from Section 9, with {deals_id} and {wo_id} interpolated]
""".strip()
```

**Typical tool call sequence for a complex query:**
```
1. get_board_schema(DEALS_BOARD_ID)      → learn column IDs
2. get_board_items(DEALS_BOARD_ID, ...)  → fetch open deals
3. get_board_schema(WO_BOARD_ID)         → learn WO column IDs (if needed)
4. get_board_items(WO_BOARD_ID, ...)     → fetch WO data (if cross-board)
→ Groq reasons, cleans, analyzes, responds
```

---

## 9. The System Prompt

This is the most important artifact in the project.

```
You are a business intelligence agent for a founder/executive at a company
that does aerial survey and mapping work (drones, LiDAR, photogrammetry).

You have access to two Monday.com boards:
- DEALS board (ID: ${DEALS_BOARD_ID}): Sales pipeline — deals, companies,
  values, stages, sectors, owners, close dates.
- WORK ORDERS board (ID: ${WORKORDERS_BOARD_ID}): Project execution — work
  orders, billing, collections, execution status.

═══════════════════════════════════════════
WORKFLOW — follow every time:
═══════════════════════════════════════════
1. Call get_board_schema for any board you plan to query.
2. Call get_board_items or search_board to fetch the data.
3. Apply the cleaning rules below BEFORE any analysis.
4. Perform analysis appropriate to the question.
5. Respond with an insight-driven answer — not a raw data dump.

═══════════════════════════════════════════
DATA CLEANING — DEALS BOARD:
═══════════════════════════════════════════
- REMOVE rows where "Deal Stage" or "Deal Status" literally says
  "Deal Stage" or "Deal Status" — these are duplicate headers.
- REMOVE rows where Deal Name is blank.
- Treat blank Deal Value as null, not zero.
- Treat "On Hold" status as a sub-type of Open (not closed).
- A Tentative Close Date in the past for an Open deal = overdue deal.
- "Tender" is a valid sector name (not a document type).
- Won deals at "A. Lead Generated" with no value = bulk-imported historical
  records. Flag them but don't let them skew averages.

═══════════════════════════════════════════
DATA CLEANING — WORK ORDERS BOARD:
═══════════════════════════════════════════
- The first data row is completely blank. Skip it.
- Any amount field containing "#VALUE!" = null (Excel error).
  This affects SDPLDEAL-085. Report it to the user.
- Normalize billing status: "BIlled" → "Fully Billed".
  "Billed- Visit N" → "Partially Billed".
- DO NOT sum quantities — units are mixed (HA, KM, Towers, MW).
  Count work order rows instead.
- Use Amount (Excl GST) columns consistently — don't mix GST-in and GST-out.
- These WOs have no matching deal record (orphaned):
  Golden fish, Octopus, Whale, Turtle, Dolphin, GG go.
  Flag them when doing cross-board analysis.

═══════════════════════════════════════════
CROSS-BOARD JOIN:
═══════════════════════════════════════════
- Join key: Deals."Deal Name" = WorkOrders."Deal name masked"
- Match case-insensitively, trimmed.
- Customer codes (COMPANY_XXX vs WOCOMPANY_XXX) use different masking —
  do NOT join on customer codes.
- Always report: how many matched, how many unmatched in each direction.

═══════════════════════════════════════════
FINANCIAL FIELDS — USE IN THIS ORDER:
═══════════════════════════════════════════
For WO analysis:
  Contract value  → "Amount in Rupees (Excl of GST)"
  Billed to date  → "Billed Value in Rupees (Excl of GST)"
  Cash collected  → "Collected Amount (Incl of GST)"
  Outstanding AR  → "Amount Receivable"
  Still to bill   → "Amount to be billed (Excl of GST)"

═══════════════════════════════════════════
RESPONSE STYLE:
═══════════════════════════════════════════
- Address the founder directly. Be concise. Lead with insight.
- Support with key numbers. Close with data caveats if relevant.
- Flag risks or anomalies you spot even if not asked.
- When data is ambiguous, state your assumption explicitly.
- Use ₹ for currency (Indian Rupees, values are masked/scaled).
- Never dump a raw table unless explicitly asked.
- For follow-ups ("filter those", "now show me X"), re-query live —
  do not rely on previously fetched data.
```

---

## 10. Complete Request Lifecycle — Example

**User:** "How's our Renewables pipeline this quarter?"

```
Step 1 — Frontend sends:
  POST /api/chat { messages: [{role:"user", content:"How's our Renewables..."}] }

Step 2 — Groq decides:
  tool_calls: [get_board_schema({ board_id: DEALS_ID })]
  Action log shows: "🔍 Fetching schema for Deals board..."

Step 3 — Server executes get_board_schema → 12 columns returned
  Groq now knows: sector column = "text_xyz", stage = "status_abc", value = "numbers_1" etc.
  Action log: "✅ 12 columns found"

Step 4 — Groq decides:
  tool_calls: [search_board({ board_id: DEALS_ID, column_id: "text_xyz", value: "Renewables" })]
  Action log: "🔎 Searching Deals for sector = Renewables..."

Step 5 — Server executes search_board → 111 Renewables deals returned
  Action log: "✅ 111 deals found"

Step 6 — Groq reasons over the data:
  - Removes duplicate header rows
  - Filters to Open + On Hold only (pipeline = active)
  - Groups by Deal Stage, sums values, notes missing values
  - Calculates weighted pipeline by probability
  - Identifies overdue deals
  - finish_reason: "stop"

Step 7 — Groq responds:
  "Your Renewables pipeline has 23 active deals.

  Funnel distribution:
  • Proposal stage: 7 deals (~₹12M) — the main concentration
  • Negotiations: 4 deals (~₹8M) — close to closing
  • Early stage (Lead/SQL): 9 deals (value mostly unrecorded)
  • Feasibility: 3 deals (~₹18M) — large but uncertain

  Weighted pipeline (by probability): ~₹19M

  ⚡ Flags:
  • 4 deals have a Tentative Close Date that has already passed — overdue
  • 1 deal (COMPANY169, ₹14.7M) is at Feasibility with 'High' probability —
    your biggest near-term upside

  ⚠️ Data note: 6 of the 23 deals have no value recorded — excluded from
  value totals. Real pipeline could be higher."

Step 8 — Streams to browser. Chat panel shows response.
Action log shows 2 completed tool calls.
```

---

## 11. Frontend: Chat UI + Action Log

### Layout
```
┌────────────────────────────────────────────────────────────┐
│  📊 BI Agent               [View Monday Board ↗]           │
├──────────────────────────┬─────────────────────────────────┤
│                          │  ACTION LOG                     │
│   CHAT                   │  ─────────────────────────      │
│                          │  🔍 get_board_schema (Deals) ✅ │
│   messages here          │  🔎 search_board (Renewables)✅ │
│                          │  🤔 Analyzing 111 deals...      │
│                          │                                 │
├──────────────────────────┴─────────────────────────────────┤
│  [Type your question...]                          [Send]   │
└────────────────────────────────────────────────────────────┘
```

### Svelte State
```javascript
let messages = [];        // { role, content }[]
let actionLog = [];       // { tool, args, status: 'running'|'done', summary }[]
let isLoading = false;
let input = "";

const API_URL = import.meta.env.PUBLIC_API_URL;
```

### Fetching from the Python Backend
```javascript
async function sendMessage() {
    isLoading = true;
    messages = [...messages, { role: "user", content: input }];
    input = "";

    const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const lines = decoder.decode(value).trim().split("\n");
        for (const line of lines) {
            if (!line) continue;
            const event = JSON.parse(line);

            if (event.type === "tool_start") {
                actionLog = [...actionLog, {
                    tool: event.tool,
                    args: event.args,
                    status: "running",
                    summary: ""
                }];
            } else if (event.type === "tool_done") {
                actionLog = actionLog.map(entry =>
                    entry.tool === event.tool && entry.status === "running"
                        ? { ...entry, status: "done", summary: event.summary }
                        : entry
                );
            } else if (event.type === "answer") {
                messages = [...messages, {
                    role: "assistant",
                    content: event.content
                }];
            }
        }
    }
    isLoading = false;
}
```

### Stream Event Types (Python backend → browser, NDJSON)
```json
{ "type": "tool_start", "tool": "get_board_schema", "args": { "board_id": "..." } }
{ "type": "tool_done",  "tool": "get_board_schema", "summary": "12 columns found" }
{ "type": "tool_start", "tool": "search_board", "args": { "..." } }
{ "type": "tool_done",  "tool": "search_board", "summary": "111 items returned" }
{ "type": "answer",     "content": "Your Renewables pipeline..." }
```

---

## 12. Error Handling

| Error | Detection | Response |
|---|---|---|
| Duplicate header rows in Deals | Row where stage col = "Deal Stage" | Skip silently, clean before analysis |
| #VALUE! in WO amounts | String contains "#VALUE!" | Treat as null, report to user |
| Missing Deal Value | Empty string | Treat as null, count and report exclusions |
| Orphaned WOs (no deal record) | Name not in Deals | Flag in response |
| Monday API 401 | HTTP 401 | "Monday.com auth failed — check API key" |
| Groq 429 rate limit | HTTP 429 | "Rate limit hit, please retry in a moment" |
| Empty search results | items array empty | "No [sector] deals found. Try a different filter." |
| GraphQL errors | `json.errors` present | Throw, catch, return error message to Groq |
| Join returns no matches | matched set empty | Report: "No work orders found for these deals" |

---

## 13. Deployment

### Backend → Railway

```bash
# From the backend/ folder
# Railway detects Python automatically via requirements.txt

# Start command (set in Railway dashboard):
uvicorn main:app --host 0.0.0.0 --port $PORT

# Env vars to set in Railway dashboard:
GROQ_API_KEY=gsk_...
MONDAY_API_KEY=eyJ...
DEALS_BOARD_ID=...
WORKORDERS_BOARD_ID=...
```

Railway gives you a URL like `https://your-app.railway.app`.
Copy this — you need it for the frontend env var.

### Frontend → Vercel

```bash
# From the frontend/ folder
vercel --prod

# Env var to set in Vercel dashboard:
PUBLIC_API_URL=https://your-app.railway.app
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
# Set PUBLIC_API_URL=http://localhost:8000 in frontend/.env
```

The evaluator opens the Vercel URL. No setup required. All secrets are
in Railway/Vercel dashboards. Monday board link is visible in the header.
Every query shows a live action log. Data is fetched fresh on every question.

---

## 14. Decision Log Summary

| Decision | Choice | Rationale |
|---|---|---|
| LLM | Groq Llama 4 Scout | Free tier, 1K RPD, 30K TPM, native tool-calling |
| Backend | Python FastAPI | Developer preference; async-native; Groq SDK works seamlessly |
| Frontend | Svelte | Lightweight, reactive, no framework overhead |
| Backend hosting | Railway | Free tier, auto-detects Python, simple env var config |
| Frontend hosting | Vercel | Free, zero-config static Svelte deploy |
| Streaming | NDJSON (newline-delimited JSON) | Simple to produce in Python, simple to parse in JS |
| Cleaning | In-context (system prompt) | Faster to build; LLM handles the rules well |
| Tools | 3 focused tools | Covers all query types; avoids over-engineering |
| No caching | Enforced | Assignment requirement — live per query |
| MCP | Not used | REST API is sufficient; MCP is bonus credit |
| Join key | Deal Name (masked) | Only reliable cross-board key |
| Gemini | Dropped | 20 RPD is a demo-breaking risk |
| LangGraph | Not used | 4-hour build; raw tool loop is ~80 lines of Python |