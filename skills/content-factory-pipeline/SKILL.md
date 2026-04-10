---
name: content-factory-pipeline
description: |
  Autonomous 24/7 Content Factory Pipeline for AI Agencies.
  Includes: 4 Data Scouts (Morning) → Central Aggregator/DB → Analyst → Writer → Editor.
  Uses SQLite for deduplication and state management.
category: content-factory-pipeline
version: 2.0
---

# Content Factory Pipeline

## Architecture

The pipeline runs autonomously every morning to generate high-quality, verified blog posts for AIMediaFlow.

### 📅 Schedule (Daily)

| Time | Agent | Function | Input | Output |
|------|-------|----------|-------|--------|
| 05:00 | 🔢 Fact-Checker | Search Gov/SME data (CSO, Ibec, etc.) | Web | `verified-sme-facts.md` |
| 05:15 | 💬 Reddit Scout | Search forum pain points | Web | `forum-pain-points.md` |
| 05:30 | 🏆 Case Hunter | Search success stories (TechCrunch, etc.) | Web | `competitor-case-studies.md` |
| 05:45 | 📧 Mail Monitor | Parse AgentMail newsletters (`theneuron@agentmail.to`) | Email API | `email-sourced-topics.md` |
| **06:00** | **🧠 Aggregator** | **Filter noise, deduplicate vs DB, save new topics** | 4 MD files | `topics-db.sqlite` (INSERT) |
| **06:15** | **📋 Analyst** | **Build post outline + find 3-5 sources** | DB (1 new topic) | `blog-outlines/outline-YYYY-MM-DD.json` |
| **06:30** | **✍️ Writer** | **Write 800-1200 word draft** | JSON Outline | `blog-drafts/YYYY-MM-DD-slug.md` |
| **06:45** | **👁 Editor** | **Polish, SEO, CTA, change status to 'ready'** | Draft MD | Telegram Notification |

## Database (`topics-db.sqlite`)

Path: `/home/hermes_user/.hermes/topics-db.sqlite`

### Schema
```sql
CREATE TABLE topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,          -- hospitality, legal, dental, sme
    source_type TEXT,       -- fact, forum, case_study, email, manual
    source_url TEXT,
    source_quote TEXT,
    similarity_hash TEXT,   -- MD5 for deduplication
    status TEXT DEFAULT 'new', -- new, new/verified, analyzed, draft, ready, archived
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    checked_at TEXT
);
```

## File Structure
```
~/.hermes/
├── topics-db.sqlite
├── verified-sme-facts.md
├── forum-pain-points.md
├── competitor-case-studies.md
├── email-sourced-topics.md
├── blog-outlines/          # .json files from Analyst
└── blog-drafts/            # .md files from Writer/Editor
```

## Key Prompts Summary

### Aggregator (06:00)
- Reads the 4 morning files.
- Checks `topics-db` for similarity.
- If new & high-value (B2B pain point), INSERTs into DB.
- **Rule:** Ignore general tech news (Apple bans apps). Only keep "AI automation for SMEs" ideas.

### Analyst (06:15)
- Query: `SELECT * FROM topics WHERE status IN ('new', 'new/seed', 'new/verified') LIMIT 1`.
- Uses `web_search` (Tavily + SearXNG) to find 3-5 verified sources.
- Saves JSON outline with `topic_id`, `hook`, `sections`, `sources`, `cta`.
- Updates DB: `status='analyzed'`.

### Writer (06:30)
- Reads the latest JSON outline.
- Writes **1,500-2,000 words** in Markdown (SEO-optimized length; never under 1,500).
- **MANDATORY SECTIONS in every draft:**
  1. Hook/Intro with hard data + source link
  2. The Problem — deep dive with real stats + inline sources
  3. **How It Works (Step by Step)** — text-based diagram showing user journey
  4. **Real-World Scenario** — concrete calculation with numbers (ADR, occupancy, savings, payback)
  5. **Comparison Tables** — Old approach vs AI approach, Human cost vs AI cost
  6. **Handling Objections** — address 2-3 common fears
  7. **FAQ Section** — 5-7 questions with schema.org `<div itemscope itemtype="https://schema.org/FAQPage">` markup
  8. **Deployment Timeline** — concrete Day 1/Day 2/Day 3 steps
  9. CTA with link
- Tone: Expert practitioner, no fluff.
- 🔥 **CRITICAL — Inline Source Links:** EVERY factual claim, statistic, or number MUST have an `[inline source link](URL)` immediately after it. NO unverified stats.
- Use Irish/British English (analyse, optimise, programme).
- Saves to `blog-drafts/` with frontmatter (status: draft, includes `sources: []` array and `meta_description`).
- Updates DB: `status='draft'`.

### Editor (06:45)
- Reads the draft with `status: draft`.
- 🔥 **Cover Image:** Extracts keywords from frontmatter. Generates via Hugging Face FLUX.1-schnell API (free tier). **Immediately converts JPEG → WebP** (quality 85) using Pillow for web optimization (~30-40% smaller). **NOTE:** Pillow NOT available in execute_code sandbox. Install with `apt install python3-pil` on the server first, or use `cwebp` CLI tool as alternative. Saves to `~/.hermes/blog-covers/YYYY-MM-DD-slug.webp`. If conversion unavailable, save as `.jpg` instead. Updates frontmatter `cover_image` field. If API fails, skip image — don't block publishing.
- 🔥 **Source Link Enforcement:** Every stat/claim/number must have an inline `[link](URL)`. If missing → `web_search` for source or rewrite/remove the claim.
- **H1 Length:** Keep under 60 characters for Google SEO (trimmed to ~58 chars).
- **Author Block:** Every article must end with an author card: Serhii Baliasnyi, Founder & CEO, AIMediaFlow, LinkedIn: `https://www.linkedin.com/in/serhii-baliasnyi-290b72246/`.
- **Deployment Section:** If article mentions a service/process, include concrete step-by-step details (e.g., Day 1/Day 2/Day 3), not vague promises.
- Cuts fluff (no "game-changer", "revolutionizing", "in today's world").
- Strengthens hook (3-second grab).
- Irish/British English spelling.
- Checks CTA: "Book a free 15-min AI Infrastructure Audit at aimediaflow.net".
- Updates frontmatter: `status: ready`, `editor_notes: "..."`, `fact_check: "All claims sourced ✅"` or list unverified.
- Adds footer: `> Edited & Published by AIMediaFlow | aimediaflow.net | Date`.
- Updates DB: `status='ready'`.
- **Delivers file to Telegram:** Ends response with `MEDIA:/home/hermes_user/.hermes/blog-drafts/filename.md` so the gateway sends the .md file as a native attachment.

## AgentMail Integration
- Inbox: `theneuron@agentmail.to`
- API: `GET /inboxes/{inbox_id}/threads`
- Used to extract daily AI automation trends from paid newsletters.

## Critical Rules & Pitfalls

### 🚨 Image Generation Constraints (Cron/Sandbox)
The Editor generates cover images via Hugging Face FLUX.1-schnell API.
### 🔧 Manual Fallback: When Editor Cron Times Out
The Editor cron job has a hard 10-minute timeout. If it fails:
- Check: `cronjob action=list` to confirm status
- Common causes: HF API cold start delays, excessive iterations, empty prompt
- **Fix:** Run the Editor steps manually in the current session context:
  1. Read the draft with `status: draft`
  2. Expand to 1,500+ words if needed
  3. Generate cover via HF API (save as .jpg, no conversion)
  4. Update frontmatter: `status: ready`
- Update the cron prompt to prevent future timeouts (ensure it's concise and self-contained)

### 🚨 Cron sandbox has NO Pillow, NO cwebp, NO ImageMagick. Do NOT attempt conversion.
HF API returns JPEG directly — use it as-is, save as `.jpg` to `~/.hermes/blog-covers/`.
If WebP is absolutely requested for a specific file, it must be done on the host machine (not in cron).
If the HF API call fails or times out, **skip the image and don't block the article** — save what you have.

### 🚨 File Naming Convention
Draft filenames MUST use today's date: `YYYY-MM-DD-slug.md`.
If reprocessing an old seed file (e.g. `2024-09-16-...`), **rename it with current date** before saving.
Never save drafts with stale dates from original seed content.

### 🚨 NO Unlinked Facts
If a paragraph contains a number, statistic, or claim — it MUST be linked inline: `[Source Title](URL)`.
The Editor must verify every link. If a link is broken or missing, find a replacement via `web_search` or remove the claim entirely.
A blog post with unverified stats is worthless — it damages AIMediaFlow's credibility as a data-driven agency.

### 🚨 ALL Content in English
All article text, cron prompts, database entries, and file names must be in English. The target audience is Irish SMEs, not Russian speakers.
If you find Russian text in the DB or drafts, translate it immediately.

### 🚨 No General Tech News
Ignore headlines like "China bans Bitchat" or "Elon Musk tweets X". Only keep topics related to **AI automation for small businesses** (Hotels, Dental, Legal, SMEs).

### ✅ Deduplication is non-negotiable
The Aggregator (06:00) must compare every new topic against `topics-db.sqlite`. If a similar topic exists (by semantic similarity), it is SKIPPED.
Database `status` is the single source of truth: `new` → `analyzed` → `draft` → `ready`.

## Cron Jobs
1. `SME Facts Monitor` (05:00)
2. `Forum Pain Points Monitor` (05:15)
3. `Case Studies Monitor` (05:30)
4. `AgentMail Automation Monitor` (05:45)
5. `Morning Topics Aggregator` (06:00)
6. `Blog Analyst (Outline Builder)` (06:15)
7. `Blog Writer (First Draft)` (06:30)
8. `Blog Editor & Publisher` (06:45)