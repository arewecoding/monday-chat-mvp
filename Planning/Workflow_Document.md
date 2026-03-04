# Monday.com BI Agent — Complete Workflow Document

**Stack:** SvelteKit · Groq (Llama 4 Scout) · Monday.com GraphQL API · Vercel  
**Model:** `meta-llama/llama-4-scout-17b-16e-instruct`  
**Constraint:** Free tier only. No caching. All queries live.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (User)                           │
│                                                                 │
│   ┌──────────────────────┐    ┌──────────────────────────┐     │
│   │     Chat Panel       │    │     Action Log Panel     │     │
│   │  (conversation UI)   │    │  (live tool call trace)  │     │
│   └──────────┬───────────┘    └──────────────────────────┘     │
│              │ POST /api/chat (user message + history)          │
└──────────────┼──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│                  SVELTEKIT SERVER (Vercel)                       │
│                                                                 │
│   src/routes/api/chat/+server.ts                                │
│                                                                 │
│   1. Receives message + conversation history                    │
│   2. Calls Groq with system prompt + tools defined              │
│   3. Groq responds with tool_call → server executes it          │
│   4. Result fed back to Groq → final answer                     │
│   5. Streams back: tool events + final text to browser          │
└──────────────┬──────────────────────────────────────────────────┘
               │
       ┌───────┴───────┐
       │               │
┌──────▼──────┐  ┌─────▼──────────────────────┐
│  GROQ API   │  │   MONDAY.COM GraphQL API    │
│             │  │                             │
│  Llama 4    │  │  POST api.monday.com/v2     │
│  Scout 17B  │  │  Auth: Bearer token (env)   │
│  (free)     │  │  Board IDs: (env)           │
└─────────────┘  └─────────────────────────────┘
```

---

## 2. Project File Structure

```
monday-bi-agent/
│
├── src/
│   ├── routes/
│   │   ├── +page.svelte              ← Main chat UI (all frontend lives here)
│   │   └── api/
│   │       └── chat/
│   │           └── +server.ts        ← Agent brain (Groq + tool loop)
│   │
│   └── lib/
│       ├── monday.ts                 ← All Monday.com GraphQL calls
│       ├── tools.ts                  ← Tool definitions (schema for Groq)
│       └── prompts.ts                ← System prompt
│
├── .env                              ← Secrets (never committed)
├── svelte.config.js
├── vite.config.ts
└── package.json
```

---

## 3. Environment Variables

```bash
# .env (server-side only, never exposed to browser)
GROQ_API_KEY=gsk_...
MONDAY_API_KEY=eyJhbGci...
DEALS_BOARD_ID=123456789
WORKORDERS_BOARD_ID=987654321
```

In SvelteKit, variables without the `PUBLIC_` prefix are **server-only** by default.
The frontend never sees any of these.

---

## 4. The Three Tools

These are the functions Groq (Llama 4 Scout) can choose to call. They are defined
as JSON schemas passed to the Groq API's `tools` parameter.

---

### Tool 1: `get_board_schema`

**Purpose:** Discover what columns exist on a board before querying data.  
**When called:** Always called first for any new query, so the agent knows
what column IDs to reference.

**Definition:**
```typescript
{
  type: "function",
  function: {
    name: "get_board_schema",
    description: `Get the list of columns (their IDs and human-readable names)
                  for a Monday.com board. Always call this before get_board_items
                  so you know which column IDs to request.`,
    parameters: {
      type: "object",
      properties: {
        board_id: {
          type: "string",
          description: "The Monday.com board ID. Use DEALS for sales pipeline data, WORKORDERS for project execution data."
        }
      },
      required: ["board_id"]
    }
  }
}
```

**Monday.com GraphQL query it executes:**
```graphql
query {
  boards(ids: [BOARD_ID]) {
    name
    columns {
      id
      title
      type
    }
  }
}
```

**Example response back to Groq:**
```json
{
  "board_name": "Deals",
  "columns": [
    { "id": "name",       "title": "Deal Name",    "type": "name" },
    { "id": "text_abc1",  "title": "Company",      "type": "text" },
    { "id": "status_xyz", "title": "Stage",        "type": "status" },
    { "id": "numbers_1",  "title": "Value ($)",    "type": "numeric" },
    { "id": "date_2",     "title": "Close Date",   "type": "date" },
    { "id": "text_def2",  "title": "Sector",       "type": "text" }
  ]
}
```

---

### Tool 2: `get_board_items`

**Purpose:** Fetch actual data rows from a board.  
**When called:** After schema is known. Fetches all items (up to 500) with
only the columns the agent decides it needs.

**Definition:**
```typescript
{
  type: "function",
  function: {
    name: "get_board_items",
    description: `Fetch items (rows) from a Monday.com board.
                  Pass only the column IDs you need for the analysis.
                  Use the column IDs from get_board_schema, not the titles.`,
    parameters: {
      type: "object",
      properties: {
        board_id: {
          type: "string",
          description: "The Monday.com board ID."
        },
        column_ids: {
          type: "array",
          items: { type: "string" },
          description: "List of column IDs to fetch. Only request what you need."
        }
      },
      required: ["board_id", "column_ids"]
    }
  }
}
```

**Monday.com GraphQL query it executes:**
```graphql
query {
  boards(ids: [BOARD_ID]) {
    items_page(limit: 500) {
      items {
        id
        name
        column_values(ids: ["col_id_1", "col_id_2", "col_id_3"]) {
          id
          text
        }
      }
    }
  }
}
```

**Why `text` and not `value`:**  
`value` returns raw JSON (e.g. `{"index":1,"post_id":null}`).  
`text` returns the human-readable string (e.g. `"In Progress"`).  
Always use `text` — it's what the LLM can reason about directly.

---

### Tool 3: `search_board`

**Purpose:** Filtered fetch — get only rows matching a specific column value.  
**When called:** When the user asks about a specific sector, status, company,
or date range. More efficient than fetching everything and filtering in-context.

**Definition:**
```typescript
{
  type: "function",
  function: {
    name: "search_board",
    description: `Search for items on a Monday.com board filtered by a column value.
                  Use this when the query is about a specific sector, status, company,
                  or other categorical filter. More efficient than fetching all items.`,
    parameters: {
      type: "object",
      properties: {
        board_id: {
          type: "string",
          description: "The Monday.com board ID."
        },
        column_id: {
          type: "string",
          description: "The column ID to filter by."
        },
        value: {
          type: "string",
          description: "The value to filter for. Must be exact match."
        }
      },
      required: ["board_id", "column_id", "value"]
    }
  }
}
```

**Monday.com GraphQL query it executes:**
```graphql
query {
  items_page_by_column_values(
    board_id: BOARD_ID,
    limit: 500,
    columns: [{ column_id: "COLUMN_ID", column_values: ["VALUE"] }]
  ) {
    items {
      id
      name
      column_values {
        id
        text
      }
    }
  }
}
```

---

## 5. The Agent Loop (server.ts)

This is the core logic. It's a multi-turn tool-calling loop.

```
User message arrives at /api/chat
         │
         ▼
Build messages array:
  [system_prompt, ...conversation_history, new_user_message]
         │
         ▼
Call Groq API with messages + tools defined
         │
         ▼
┌────────────────────────────────┐
│   Did Groq return tool_calls?  │
└────────┬───────────────────────┘
         │
    YES  │                          NO
         ▼                          ▼
For each tool_call:          Stream final text
  - Extract function name     response to browser
  - Extract arguments         (done)
  - Execute the Monday.com
    GraphQL query
  - Get result back
  - Emit tool event to
    browser (for action log)
  - Append tool result to
    messages array
         │
         ▼
Call Groq again with updated
messages (now includes tool results)
         │
         └──────────────► Back to top of loop
```

**In code (simplified):**
```typescript
// src/routes/api/chat/+server.ts

export async function POST({ request }) {
  const { messages } = await request.json();
  const stream = new ReadableStream({
    async start(controller) {
      let currentMessages = [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages
      ];

      // Tool loop — runs until Groq stops calling tools
      while (true) {
        const response = await groq.chat.completions.create({
          model: "meta-llama/llama-4-scout-17b-16e-instruct",
          messages: currentMessages,
          tools: TOOL_DEFINITIONS,
          tool_choice: "auto"
        });

        const choice = response.choices[0];

        // No more tool calls — send final answer
        if (choice.finish_reason === "stop") {
          controller.enqueue(encode({
            type: "answer",
            content: choice.message.content
          }));
          break;
        }

        // Execute each tool call
        if (choice.finish_reason === "tool_calls") {
          const toolCalls = choice.message.tool_calls;
          currentMessages.push(choice.message); // add assistant turn

          for (const toolCall of toolCalls) {
            const { name, arguments: argsStr } = toolCall.function;
            const args = JSON.parse(argsStr);

            // Tell the browser what we're doing (action log)
            controller.enqueue(encode({
              type: "tool_start",
              tool: name,
              args: args
            }));

            // Actually call Monday.com
            const result = await executeTool(name, args);

            // Tell the browser the result came back
            controller.enqueue(encode({
              type: "tool_done",
              tool: name,
              result_summary: summarize(result)
            }));

            // Feed result back to Groq
            currentMessages.push({
              role: "tool",
              tool_call_id: toolCall.id,
              content: JSON.stringify(result)
            });
          }
          // Loop continues — Groq will now process tool results
        }
      }
      controller.close();
    }
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" }
  });
}
```

---

## 6. The System Prompt

This is the most important tuning lever. It tells Llama 4 Scout how to behave.

```
You are a business intelligence agent for a founder/executive. You have access
to two Monday.com boards:

- DEALS board (ID: ${DEALS_BOARD_ID}): Sales pipeline data — deals, companies,
  values, stages, sectors, close dates.
- WORKORDERS board (ID: ${WORKORDERS_BOARD_ID}): Project execution data — 
  work orders, statuses, assignees, timelines.

WORKFLOW — follow this every time:
1. Call get_board_schema first for any board you plan to query.
   This tells you the column IDs you need.
2. Call get_board_items or search_board to fetch the actual data.
3. Reason over the data and provide a clear, insight-driven answer.

DATA HANDLING — the data is real-world messy. When processing:
- Treat empty strings, "N/A", "none", "-" as null/missing.
- Normalize dates: parse any format to YYYY-MM-DD. If unparseable, treat as null.
- Strip currency symbols and commas from numbers before calculations.
- Column names may be inconsistently capitalized — match case-insensitively.
- For sector/status fields, group by trimmed, lowercased value.

DATA QUALITY REPORTING — always tell the user:
- How many records were in the dataset.
- How many had missing values in fields relevant to their question.
- Example: "Note: 8 of 47 deals had no close date and were excluded from
  the timeline analysis."

CROSS-BOARD QUERIES — when a question spans both boards:
- Fetch both boards' data.
- The likely join key is company name — match case-insensitively, trimmed.
- Be explicit about how you joined them and how many records matched.

CONVERSATION — remember the full conversation. When the user says "filter those"
or "now show me only..." they are referring to the previous result. Re-query
with the new filter rather than relying on memory of old results.

RESPONSE STYLE — you are talking to a founder. Be concise. Lead with the
insight, follow with the supporting numbers. Do not return raw tables unless
asked. Flag anomalies or things that look off in the data.
```

---

## 7. Frontend: Chat UI + Action Log

The UI has two panels rendered in a single `+page.svelte` file.

### Data flow on the frontend:

```
User types message → hits Send
        │
        ▼
Append user message to local messages array
Start streaming fetch to /api/chat
        │
        ▼
As stream chunks arrive:
  type === "tool_start"  → push to actionLog array (show in right panel)
  type === "tool_done"   → update that action log entry with ✅
  type === "answer"      → append assistant message to chat
        │
        ▼
Re-render (Svelte reactivity handles this automatically)
```

### Action Log entries look like:

```
🔍 get_board_schema      board: Deals               ✅ 6 columns
📋 get_board_items       board: Deals, 4 cols        ✅ 47 items
🔎 search_board          board: Deals, sector=Energy ✅ 12 items
```

### Key Svelte state:

```typescript
let messages: {role: string, content: string}[] = [];
let actionLog: {tool: string, args: any, status: 'pending'|'done', summary?: string}[] = [];
let isLoading = false;
let input = "";
```

---

## 8. Monday.com API Module (monday.ts)

All three GraphQL calls live here. Clean separation from the agent logic.

```typescript
// src/lib/monday.ts

const MONDAY_API = "https://api.monday.com/v2";
const headers = {
  "Content-Type": "application/json",
  "Authorization": import.meta.env.MONDAY_API_KEY,  // server-side only
  "API-Version": "2025-04"
};

async function gql(query: string) {
  const res = await fetch(MONDAY_API, {
    method: "POST",
    headers,
    body: JSON.stringify({ query })
  });
  const json = await res.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
}

export async function getBoardSchema(boardId: string) {
  const data = await gql(`
    query {
      boards(ids: [${boardId}]) {
        name
        columns { id title type }
      }
    }
  `);
  return data.boards[0];
}

export async function getBoardItems(boardId: string, columnIds: string[]) {
  const ids = columnIds.map(id => `"${id}"`).join(", ");
  const data = await gql(`
    query {
      boards(ids: [${boardId}]) {
        items_page(limit: 500) {
          items {
            id
            name
            column_values(ids: [${ids}]) { id text }
          }
        }
      }
    }
  `);
  return data.boards[0].items_page.items;
}

export async function searchBoard(boardId: string, columnId: string, value: string) {
  const data = await gql(`
    query {
      items_page_by_column_values(
        board_id: ${boardId},
        limit: 500,
        columns: [{ column_id: "${columnId}", column_values: ["${value}"] }]
      ) {
        items {
          id
          name
          column_values { id text }
        }
      }
    }
  `);
  return data.items_page_by_column_values.items;
}
```

---

## 9. Complete Request Lifecycle (Example)

**User asks:** *"How's our pipeline looking for the energy sector this quarter?"*

```
Step 1 — Frontend sends:
  POST /api/chat
  { messages: [{ role: "user", content: "How's our pipeline..." }] }

Step 2 — Server builds Groq request:
  messages: [system_prompt, user_message]
  tools: [get_board_schema, get_board_items, search_board]

Step 3 — Groq responds:
  finish_reason: "tool_calls"
  tool_calls: [{ name: "get_board_schema", args: { board_id: "DEALS_ID" } }]

Step 4 — Server executes get_board_schema("DEALS_ID")
  → Calls Monday.com GraphQL → Gets 8 columns back
  → Emits { type: "tool_start", tool: "get_board_schema" } to stream
  → Emits { type: "tool_done", summary: "8 columns found" } to stream
  → Appends tool result to messages

Step 5 — Groq responds again:
  tool_calls: [{ name: "search_board", args: {
    board_id: "DEALS_ID",
    column_id: "text_def2",   ← knows this from schema result
    value: "Energy"
  }}]

Step 6 — Server executes search_board(...)
  → Calls Monday.com → Gets 12 matching deals
  → Emits tool events to stream
  → Appends tool result to messages

Step 7 — Groq responds:
  finish_reason: "stop"
  content: "Your energy sector pipeline looks healthy this quarter.
            You have 12 active deals totalling $2.4M. 4 are in final
            negotiation stage. Note: 2 deals had no close date and
            couldn't be confirmed as Q2. Top deal is Apex Energy at
            $480K, currently in proposal stage."

Step 8 — Server streams final answer to browser.
  Frontend renders it in chat panel.

Total Monday.com API calls: 2
Total Groq calls: 3 (schema → search → final answer)
```

---

## 10. Error Handling Strategy

| Error | How to Handle |
|---|---|
| Monday.com API key invalid | Catch in `monday.ts`, return `{ error: "Monday API auth failed" }` to Groq, which tells the user |
| Board ID not found | Return empty data with a message, Groq reports it |
| Groq rate limit (30 RPM) | Catch 429, return friendly message: "Rate limit hit, try again in a moment" |
| GraphQL errors in response | Check `json.errors` in `gql()`, throw with error message |
| Tool args malformed | Wrap each `executeTool()` call in try/catch, feed error back to Groq |
| Empty board / no results | Return `{ items: [], note: "No items found" }`, Groq handles gracefully |

---

## 11. Deployment

```bash
# Local dev
npm run dev

# Deploy to Vercel (one command)
vercel --prod

# Required env vars to set in Vercel dashboard:
GROQ_API_KEY
MONDAY_API_KEY
DEALS_BOARD_ID
WORKORDERS_BOARD_ID
```

Vercel auto-detects SvelteKit and configures the build. API routes
(`+server.ts`) become serverless functions. No separate backend needed.

The evaluator opens the Vercel URL — zero configuration required.

---

## 12. What the Evaluator Sees

1. Opens the hosted URL
2. Sees a chat interface with a visible "Action Log" panel on the right
3. Asks a question (e.g. "Show me top deals by value")
4. Watches the action log populate in real time:
   ```
   🔍 Fetching schema for Deals board...     ✅
   📋 Fetching items (5 columns)...          ✅ 47 rows
   ```
5. Reads a clear, insight-driven answer in the chat panel
6. Asks a follow-up ("Now filter by energy sector") — agent re-queries live
7. Clicks the "View Monday Board →" link in the header to verify source data

Every requirement in the assignment spec is visibly satisfied.

---

## 13. Decision Log Summary

| Decision | Choice | Reason |
|---|---|---|
| LLM | Groq Llama 4 Scout | Free tier, 1K RPD, 30K TPM, native tool-calling |
| Frontend | SvelteKit | One framework for UI + API routes, Vercel-native |
| Backend | SvelteKit `+server.ts` | No separate Express server needed |
| Hosting | Vercel | Free, zero-config SvelteKit deploy |
| Tools | 3 focused tools | Covers all query types without over-engineering |
| No caching | Enforced | Assignment requirement; live per query |
| MCP | Not used | REST API achieves same result; MCP is bonus |
| Conversation | In-memory state | Sufficient for evaluation session |
