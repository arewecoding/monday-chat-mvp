# Decision Log — Monday.com BI Agent

## Core Assumptions

The first thing I had to figure out was the scope of the problem. The assignment says "business data is messy" and asks the agent to answer founder-level queries — but it doesn't define how messy, or what kinds of questions a founder actually asks. So I made some calls early on.

**I assumed the two CSVs are the complete and stable schema.** The boards won't suddenly have new columns or entirely new structures. This let me write targeted cleaning logic instead of a generic schema-discovery system. If the data format changes, the cleaning layer breaks — but that's a trade-off I was willing to accept for an MVP under time pressure.

**I treated "no caching" as a hard constraint, not a soft one.** The assignment was explicit about this — live API calls per query. I didn't pre-load the board data into a dataframe at startup. Every query hits Monday.com fresh. The downside is latency, but the upside is the evaluator can actually see the agent doing real work.

**I assumed the agent doesn't need to understand who the user is.** The "leadership updates" bonus made me think about personalising responses based on role, but I decided against building that in the core flow. There wasn't enough signal in a single chat session to infer the user's role reliably, and adding a persona layer would complicate the prompt without a clear payoff in 6 hours.

---

## Key Trade-offs

### LLM: Groq (Llama 4 Scout) over Gemini

I initially looked at Gemini because of the context window, but Gemini's free tier is 20 requests per day. That's a demo-breaking limitation — an evaluator spending 20 minutes with the app could hit the ceiling. Groq gives 1000 RPD and 30K TPM on the free tier, which is enough to run a real demo. The trade-off is that Llama 4 Scout is a preview model with a non-trivial failure rate, but I'd rather have the app survive the demo than have a marginally better model that rate-limits.

### No LangGraph — Raw Tool Loop Instead

My first instinct was to use LangGraph because it handles the agentic loop, state management, and tool calling cleanly. But setting it up properly, debugging the graph definition, and integrating it with Groq's API would have eaten 2-3 hours of a 6-hour window. The core tool-calling loop is actually ~80 lines of Python — a `while True` that checks `finish_reason` and routes tool calls. I built that directly in `main.py`. The risk is there's no turn limit, which is a potential infinite loop issue, but for a controlled demo that's acceptable.

### Svelte over React/Streamlit

I considered Streamlit for the frontend since it's fast to build. But Streamlit has real limitations around layout customisation — the two-panel layout (chat + action log side by side) is hard to do cleanly in Streamlit, and the action log visibility was a core requirement. Svelte gave me full control over the layout with minimal overhead. No framework bloat, straightforward reactive state, and deploys to Vercel as a static site without any config.

### Cleaning Logic in `clean.py`, Not Just in the Prompt

This was the decision I thought about most. The temptation is to just tell the LLM in the system prompt: "there are duplicate header rows, ignore them." And to some extent I did that — the prompt has cleaning rules. But relying only on the LLM to clean means every query re-discovers the same issues, and there's no guarantee it handles them consistently. So I built `clean.py` as a proper Python layer that runs before the LLM ever sees the data. The downside is there's now duplication — rules live in both the prompt and the code, which can drift. But consistency of output was more important than DRY code for this.

### The Join Key Decision

The two boards don't share a customer code format — `WOCOMPANY_XXX` in Work Orders vs `COMPANY_XXX` in Deals. I spent time investigating whether there was a way to join on client code and there isn't — the masking scheme is different. The only reliable join is on Deal Name (masked). This join is imperfect because some aliases like `Alias_160` map to multiple WO records, which means some cross-board queries produce many-to-many matches. I handled this by making the agent report when that happens rather than silently summing incorrect numbers.

---

## What I'd Do Differently With More Time

**Pagination first.** Right now `items_page(limit: 500)` means results silently truncate if either board grows beyond 500 rows. For the current dataset this doesn't matter, but it's the kind of bug that surfaces in production when it's too late. Cursor-based pagination is straightforward to add but I ran out of time.

**Fix the tool schema bug.** The `run_deals_analysis` tool has `group_by`, `sort_by`, and `date_range` as required fields in the JSON schema, but the LLM sometimes passes `null` for them when they're genuinely not needed for a query. This causes validation errors. The fix is simple — mark those fields as optional with sensible defaults — but I only caught this late and didn't get to it.

**Better error messaging to the user.** Right now when a tool call fails, the error dumps the raw schema validation message into the chat. That's not what a founder wants to see. I'd add a proper error formatting layer that translates API/validation errors into plain language.

**Work order status parsing.** The agent currently reports zero ongoing work orders because the first row of that CSV is completely blank (a CSV export artifact), which breaks the default CSV parser. The correct answer is 25 ongoing. I knew the blank row existed and handled it in `clean.py`, but there's clearly a gap between what the cleaning layer does and what the LLM actually receives in some code paths.

---

## Bonus: Leadership Updates

I interpreted this as "the agent should know what matters to someone preparing for a board meeting or investor update." A founder preparing for that doesn't want raw deal counts — they want: pipeline value by sector, win rate trends, overdue deals that need follow-up, and which work orders are stuck or not billed.

I addressed this by making the system prompt aware of these BI concepts and having the agent proactively surface flags (overdue tentative close dates, orphaned work orders, deals with missing values). It's not a separate "leadership mode" — it's baked into how the agent responds to any pipeline query.

With more time I'd add a dedicated `/leadership-summary` command that generates a structured one-page update across both boards without needing the user to ask multiple questions.