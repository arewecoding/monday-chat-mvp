# Technical Assignment: Monday.com Business Intelligence Agent

## Problem Statement

Founders and executives need quick, accurate answers to business questions across multiple data sources. Currently, this requires:

- Manually pulling data from monday.com boards
- Cleaning inconsistent data formats
- Querying information across multiple boards (work orders, deals, pipeline)
- Creating ad-hoc analysis for each query
- Dealing with missing data and incomplete records

**The Challenge:** Business data is messy. A founder asks "How's our pipeline looking for energy sector this quarter?" and someone needs to interpret that query, find relevant data across multiple boards, clean it, and provide meaningful insights.

**Your Task:** Build an AI agent that can answer founder-level business intelligence queries by integrating with monday.com boards containing work orders and deals data.

## Sample Data

You will receive two CSV files to import into monday.com:

1. **Work Orders** — [Project execution data](https://docs.google.com/spreadsheets/d/1mL0GsxyhIYrUSHfkhbQ--SFfxrG1AE2j/edit?usp=sharing&ouid=109330654811604508216&rtpof=true&sd=true)
2. **Deals** — [Sales pipeline data](https://docs.google.com/spreadsheets/d/1jghv-FiZ_bmWtEtB7IyaKYlwT5omEwSl/edit?usp=sharing&ouid=109330654811604508216&rtpof=true&sd=true)

Import these into monday.com as separate boards. Set up appropriate column types and structure as you see fit.

**Note:** The data is real-world messy —  Your agent must handle this gracefully.

## Core Features

Your agent must handle these areas:

### 1. Monday.com Integration (Live)
- Connect to monday.com via API or MCP (MCP / tool-calling is a bonus)
- Handle authentication and connection management
- Every user query must result in live API/MCP calls to monday.com at query time. The agent must fetch current board data for each question — not rely on data loaded at startup or stored in memory

### 2. Data Resilience
- Handle missing/null values gracefully
- Normalize inconsistent date formats, naming conventions, text fields
- Provide meaningful results even with incomplete data
- Communicate data quality issues or caveats to the user

### 3. Query Understanding
- Interpret founder-level business questions
- Ask clarifying questions when needed
- Handle follow-up queries that build on prior context (e.g., "Show me top deals" → "Now filter those by energy sector")

### 4. Business Intelligence
- Answer queries about revenue, pipeline health, sectoral performance, operational metrics
- Query across both boards when needed
- Provide context and insights, not just raw numbers

### 5. Agent Action Visibility
- The agent must visibly show what it is doing when processing a query — which API calls it's making, which boards it's querying, what data it's retrieving
- This can be a tool-call trace, action log, debug panel, or similar UI element
- The evaluator must be able to see that the agent is actively querying monday.com for each query

## Bonus: Leadership Updates

> "The agent should help prepare data for leadership updates"

This is optional bonus credit. How you interpret and implement this is up to you. If you attempt it, document your interpretation in your Decision Log.

## Integration Requirements

**What you provide:**
- Your own monday.com workspace with both boards (Work Orders and Deals) imported and configured
- A shareable link to your monday.com board so evaluators can see the data your agent is querying
- A hosted chat application that is live-connected to your monday.com board

**Monday.com — Read only**
- **Read:** All data from both boards at query time via API or MCP
- The agent must query monday.com live for each user question. Do not pre-load, cache, or store board data in a local dataframe, context window, or summary. The agent's data source is monday.com, not a local copy of it.

## Deliverables

### 1. Hosted Prototype (Required)
- Working agent accessible via link
- Platform of your choice
- Must be testable without local setup
- The prototype must work immediately when opened — no API keys, board IDs, or configuration required from the evaluator
- Must include a link to your monday.com board (so evaluators can see the source data)
- Agent must show a visible action/tool-call trace when processing queries (see Core Feature §5)

### 2. Decision Log (Required, 2 page max)
- Key assumptions you made
- Trade-offs chosen and why
- What you'd do differently with more time
- If you attempted the bonus: how you interpreted "leadership updates"

### 3. Source Code
- ZIP file
- README with architecture overview and setup instructions for monday.com configuration

## Technical Expectations

- **Conversational Interface**: The user will interact with your agent conversationally, handle that to the best of your (agents') ability
- **Monday.com Integration**: Via MCP or API as specified above
- **Error Handling**: Graceful handling of data quality issues and API failures
- **Tech Stack**: Your choice — justify your decisions in the Decision Log

## Timeline

**6 hours**

## Questions?

If you have clarifying questions, document your assumptions and proceed. Part of the evaluation is seeing how you handle ambiguity and make decisions with incomplete information.

---

**Good luck!**
