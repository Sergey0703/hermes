---
name: irish-sme-research
description: Research workflow for finding verified blog topics for AIMediaFlow based on Irish SME pain points.
---

## Goal
Find verified, logical blog topics for AIMediaFlow (AI Automation Agency) targeting Irish SMEs (Hotels, Dental, Legal). 

## Source Rules
**ALLOWED (Trusted Sources):**
- Ibec.ie, CSO.ie, RTE.ie, IrishTimes.com, IrishIndependent.ie
- FailteIreland.ie, SBCI.gov.ie (Gov/Official)
- University studies, Deloitte/PwC/McKinsey (Independent consulting)

**BLACKLIST (DO NOT USE):**
- AI vendors (VoiceFleet, BotBureau, etc.) — these are competitors/sellers, not facts.
- Generic homepages — NEVER cite "example.com". Always use direct article URLs.
- Marketing estimates — No "5 billion in losses!" unless backed by independent study.

## Workflow
1. **Search via Dual Sources**: 
   Use `web_search` (Tavily) AND `curl` (SearXNG) to ensure coverage.
   Search queries must be highly specific: `"administrative burden" site:ibec.ie OR site:rte.ie 2025`
2. **Find ONE Fact per Run**: Focus on depth, not breadth.
   Look for: "Admin burden rising", "Time spent on paperwork", "Reception workload", "Compliance costs for SMEs".
   AVOID topics like chef shortages, dentist shortages, or general hiring issues unless they directly mention admin/phone/data tasks.
3. **Verify the Link**:
   Use `web_extract` on the specific article URL found in search.
   Ensure the number/fact actually exists in the text. Copy the exact quote.
4. **Check Logic (CRITICAL — NEVER SKIP)**:
   - ❌ WRONG: "No cooks available" → "Buy AI Receptionist". (No logical link).
   - ❌ WRONG: "Children without dental screening" → "Private clinics need AI booking". (Disconnected).
   - ✅ RIGHT: "57% SMEs need help with regulatory compliance paperwork" → "AI automates form-filling and document processing".
   - ✅ RIGHT: "Receptionists spend 4 hours/day on appointment confirmations" → "AI handles confirmations automatically".
   **The pain point MUST be solvable by AI (calls, emails, scheduling, data entry, document processing).**
5. **Save Output**:
   Format:
   - **Fact:** The core issue with specific number.
   - **Source:** Organization + Article Date + Article Title.
   - **URL:** Direct link to the specific article (NOT homepage).
   - **Quote:** Exact text snippet from the page (copy-paste).
   - **AI Solution:** How AIMediaFlow solves THIS specific problem — only if logically connected.
6. **Save to**: `/home/hermes_user/.hermes/verified-sme-facts.md` (append, do not overwrite).

## Cron Automation
- `cronjob` (d18476a830ac) — "SME Facts Monitor" — runs daily at 05:00, finds ONE fact
- `cronjob` (83c3b98fb0e9) — "Forum Pain Points Monitor" — runs daily at 05:15, finds ONE complaint from Reddit/forums
- `cronjob` (5e86d7595a33) — "Case Studies Monitor" — runs daily at 05:30, finds ONE AI automation success story
Each runs independently, appends to its own file. Check existing file before writing to avoid duplicates.

## Cron Automation
Run daily at 5:00 AM using `cronjob` to build a backlog of content. Use this skill in the cron prompt to ensure consistency.
