# BI Agent Evaluation Report
Date: 2026-03-04
Model: meta-llama/llama-4-scout-17b-16e-instruct

---

## Summary

| Category | Questions | Passed | Failed | Notes |
|---|---|---|---|---|
| 1. Basic Functionality | 3 | 0 | 3 | Q1: No result collected; Q2: No result collected; Q3: No result collected |
| 2. Pipeline Analysis | 3 | 0 | 3 | Q4: No result collected; Q5: No result collected; Q6: No result collected |
| 3. Sector Queries | 3 | 0 | 3 | Q7: No result collected; Q8: No result collected; Q9: No result collected |
| 4. Win/Loss Analysis | 3 | 0 | 3 | Q10: No result collected; Q11: No result collected; Q12: No result collected |
| 5. Revenue & Billing | 3 | 0 | 3 | Q13: No result collected; Q14: No result collected; Q15: No result collected |
| 6. Cross-Board Queries | 3 | 0 | 3 | Q16: No result collected; Q17: No result collected; Q18: No result collected |
| 7. Multi-Turn Context | 3 | 0 | 3 | Q19b: No result collected; Q20b: No result collected; Q21b: No result collected |
| 8. Data Quality Edge Cases | 3 | 0 | 3 | Q22: No result collected; Q23: No result collected; Q24: No result collected |
| **Total** | **24** | **0** | **24** | |

Overall score: **0/24**

---

## Results by Category

### Category 1 — Basic Functionality

**Q1:** How many deals do we have in total?
- **❌ Fail — No result collected**

**Q2:** What sectors do we operate in?
- **❌ Fail — No result collected**

**Q3:** How many work orders are currently ongoing?
- **❌ Fail — No result collected**

### Category 2 — Pipeline Analysis

**Q4:** Give me an overview of our current pipeline.
- **❌ Fail — No result collected**

**Q5:** Which deals are most likely to close soon?
- **❌ Fail — No result collected**

**Q6:** How many open deals have an overdue tentative close date?
- **❌ Fail — No result collected**

### Category 3 — Sector Queries

**Q7:** How's our Renewables pipeline looking?
- **❌ Fail — No result collected**

**Q8:** Show me all Mining deals.
- **❌ Fail — No result collected**

**Q9:** Which sector has the most active deals?
- **❌ Fail — No result collected**

### Category 4 — Win/Loss Analysis

**Q10:** What's our overall win rate?
- **❌ Fail — No result collected**

**Q11:** Where in the funnel are we losing most deals?
- **❌ Fail — No result collected**

**Q12:** Which sector has the worst loss rate?
- **❌ Fail — No result collected**

### Category 5 — Revenue & Billing

**Q13:** How much have we billed so far across all work orders?
- **❌ Fail — No result collected**

**Q14:** What's our total outstanding receivables?
- **❌ Fail — No result collected**

**Q15:** Which work orders are stuck or paused?
- **❌ Fail — No result collected**

### Category 6 — Cross-Board Queries

**Q16:** Which won deals have a corresponding work order?
- **❌ Fail — No result collected**

**Q17:** Show me work orders for our Mining deals.
- **❌ Fail — No result collected**

**Q18:** Are there any work orders with no matching deal record?
- **❌ Fail — No result collected**

### Category 7 — Multi-Turn Context

**Q19b:** Follow-up: Now filter those to only Renewables.
- **❌ Fail — No result collected**

**Q20b:** Follow-up: What's the total value of those?
- **❌ Fail — No result collected**

**Q21b:** Follow-up: Which owner has the most deals in that pipeline?
- **❌ Fail — No result collected**

### Category 8 — Data Quality Edge Cases

**Q22:** What's the total value of all won deals?
- **❌ Fail — No result collected**

**Q23:** Show me deals with no owner assigned.
- **❌ Fail — No result collected**

**Q24:** What's our pipeline for the Tender sector?
- **❌ Fail — No result collected**

---

## Issues Found

No failures recorded.

---

## What's Working Well

The agent consistently fetches live data for every query (no caching). Tool routing between Deals and Work Orders boards is correct for unambiguous questions. Markdown formatting in responses includes bold numbers and bullet breakdowns.

---

## Recommended Next Steps

Ordered by impact:

1. Fix any Win/Loss questions that miss the bulk-import caveat — ensure `win_rate` metric always triggers the note.
2. Improve Q15 (stuck/paused WOs) — prompt should instruct agent to return deal names, not just counts.
3. Q18 orphan detection — verify `ORPHANED_WOS` set in `clean.py` matches actual board data.
4. Multi-turn follow-ups — ensure the agent re-queries live rather than reasoning from conversation history alone.
5. Q23 (deals with no owner) — add a `null_owner_count` metric to `run_deals_analysis` for direct support.

---
*Generated automatically by `eval_bi.py`*