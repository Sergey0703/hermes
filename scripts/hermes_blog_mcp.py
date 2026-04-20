#!/usr/bin/env python3
"""
Hermes Blog Pipeline MCP Server
Provides tools for: get_next_topic, save_outline, update_topic_status,
get_latest_outline, save_draft, get_latest_draft, list_topics
"""

import json
import re
import sqlite3
import os
import glob
import requests
from datetime import datetime
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

DB_PATH = "/home/hermes_user/.hermes/topics-db.sqlite"
OUTLINES_DIR = "/home/hermes_user/.hermes/blog-outlines"
PAPERCLIP_API_URL = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
PAPERCLIP_API_KEY = os.environ.get("PAPERCLIP_API_KEY", "")
COMPANY_ID = "b984404a-8587-41d0-9354-a6251bd0fd94"
AGENT_IDS = {
    "editorial_manager": "46ad48c3-e8b0-4c5e-b369-6da7fbfa6251",
    "researcher": "ccc8c5e8-cc55-4432-aa16-0bc73391049e",
    "sme_facts": "acf7ffec-4aef-43be-b83b-828170c15b17",
    "case_studies": "527db020-5bf8-41e0-bf8d-20e007e7056e",
    "mail_monitor": "d52c394d-a175-4b7c-af6c-cf3882c9dc14",
    "chief_editor": "f18ff445-0515-4397-b814-2a754bd245b1",
    "production_manager": "bb643d5b-92d6-4c44-8605-0929ca43b3d9",
    "writer": "b4bcf2d0-0a5f-45c5-891d-f883c16cd5c4",
    "art_director": "eb8aaa79-f772-4ae8-95d7-5b3d6916c3ef",
}

DRAFTS_DIR = "/home/hermes_user/.hermes/blog-drafts"

app = Server("hermes-blog-pipeline")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_next_topic",
            description="Get the next unprocessed topic from the blog topics database. Returns topic id, title, description, category, source_url.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="list_topics",
            description="List topics from the database by status. Status can be: new, analyzed, draft, ready, archived.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (new, analyzed, draft, ready, archived). Leave empty for all."},
                    "limit": {"type": "integer", "description": "Max number of topics to return. Default 10."}
                },
                "required": []
            },
        ),
        types.Tool(
            name="update_topic_status",
            description="Update the status of a topic in the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic_id": {"type": "integer", "description": "The topic ID to update"},
                    "status": {"type": "string", "description": "New status: new, analyzed, draft, ready, archived"}
                },
                "required": ["topic_id", "status"]
            },
        ),
        types.Tool(
            name="save_outline",
            description="Save a blog post outline as a JSON file. Returns the file path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic_id": {"type": "integer", "description": "The topic ID this outline is for"},
                    "title": {"type": "string", "description": "Blog post title"},
                    "hook": {"type": "string", "description": "Opening hook sentence"},
                    "sections": {"type": "array", "items": {"type": "string"}, "description": "List of section names"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "key_fact": {"type": "string"}
                            }
                        },
                        "description": "List of sources with title, url, key_fact"
                    },
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "SEO keywords"},
                    "target_audience": {"type": "string", "description": "Target audience description"},
                    "cta": {"type": "string", "description": "Call to action text"}
                },
                "required": ["topic_id", "title", "hook", "sections", "sources"]
            },
        ),
        types.Tool(
            name="get_latest_outline",
            description="Get the most recently saved blog outline JSON file content.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="save_draft",
            description="Save a blog post draft as a markdown file. Returns the file path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic_id": {"type": "integer", "description": "The topic ID"},
                    "slug": {"type": "string", "description": "URL slug for the filename (lowercase, hyphens)"},
                    "content": {"type": "string", "description": "Full markdown content including frontmatter"}
                },
                "required": ["topic_id", "slug", "content"]
            },
        ),
        types.Tool(
            name="get_latest_draft",
            description="Get the most recently saved blog draft markdown file content and path.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="insert_topic",
            description="Insert a new topic into the database. Used by the Aggregator.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "source_type": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_quote": {"type": "string"}
                },
                "required": ["title", "description"]
            },
        ),
        types.Tool(
            name="get_all_topic_titles",
            description="Get all existing topic titles from the database for deduplication check.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="lookup_article",
            description="Look up a blog article by numeric ID or slug. Returns id, title, slug, status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "article_id": {"type": "integer", "description": "Numeric article ID (e.g. 63)"},
                    "slug": {"type": "string", "description": "Article slug (alternative to id)"}
                },
                "required": []
            },
        ),
        types.Tool(
            name="create_pipeline_issue",
            description="Create an issue in Paperclip to delegate a task to a pipeline agent. Agent names: editorial_manager, researcher, sme_facts, case_studies, mail_monitor, chief_editor, production_manager, writer, art_director.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name (e.g. art_director, production_manager)"},
                    "title": {"type": "string", "description": "Issue title"},
                    "description": {"type": "string", "description": "Full task description for the agent"}
                },
                "required": ["agent", "title", "description"]
            },
        ),
        types.Tool(
            name="get_pipeline_status",
            description="Get current blog pipeline status: topic counts by status and pending issues.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="finalize_draft",
            description="Finalize the latest draft: sets status to ready, adds author block, updates DB. Returns the file path for delivery.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="publish_to_notion",
            description="Publish the latest finalized (status: ready) blog article to Notion database. Checks for duplicates by slug. Returns Notion page URL.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "get_next_topic":
        conn = get_db()
        row = conn.execute(
            "SELECT id, title, description, category, source_type, source_url, source_quote FROM topics "
            "WHERE status IN ('new', 'new/seed', 'new/verified') ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return [types.TextContent(type="text", text="No new topics available.")]
        result = dict(row)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "list_topics":
        status = arguments.get("status", "")
        limit = arguments.get("limit", 10)
        conn = get_db()
        if status:
            rows = conn.execute(
                "SELECT id, title, status, created_at FROM topics WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, status, created_at FROM topics ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        result = [dict(r) for r in rows]
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "update_topic_status":
        topic_id = arguments["topic_id"]
        status = arguments["status"]
        conn = get_db()
        conn.execute(
            "UPDATE topics SET status=?, checked_at=datetime('now') WHERE id=?",
            (status, topic_id)
        )
        conn.commit()
        conn.close()
        return [types.TextContent(type="text", text=f"Topic {topic_id} status updated to '{status}'.")]

    elif name == "save_outline":
        os.makedirs(OUTLINES_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(OUTLINES_DIR, f"outline-{today}.json")
        outline = {
            "topic_id": arguments["topic_id"],
            "title": arguments["title"],
            "hook": arguments["hook"],
            "sections": arguments.get("sections", []),
            "sources": arguments.get("sources", []),
            "keywords": arguments.get("keywords", []),
            "target_audience": arguments.get("target_audience", "Irish SMEs"),
            "cta": arguments.get("cta", "Book a free 15-min AI audit at aimediaflow.net"),
            "created_at": datetime.now().isoformat()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(outline, f, ensure_ascii=False, indent=2)
        return [types.TextContent(type="text", text=f"Outline saved to {filepath}")]

    elif name == "get_latest_outline":
        files = sorted(glob.glob(os.path.join(OUTLINES_DIR, "outline-*.json")), reverse=True)
        if not files:
            return [types.TextContent(type="text", text="No outline files found.")]
        with open(files[0], "r", encoding="utf-8") as f:
            content = f.read()
        return [types.TextContent(type="text", text=f"File: {files[0]}\n\n{content}")]

    elif name == "save_draft":
        os.makedirs(DRAFTS_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        slug = arguments["slug"].lower().replace(" ", "-")
        filepath = os.path.join(DRAFTS_DIR, f"{today}-{slug}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(arguments["content"])
        return [types.TextContent(type="text", text=f"Draft saved to {filepath}")]

    elif name == "get_latest_draft":
        files = sorted(glob.glob(os.path.join(DRAFTS_DIR, "*.md")), reverse=True)
        if not files:
            return [types.TextContent(type="text", text="No draft files found.")]
        with open(files[0], "r", encoding="utf-8") as f:
            content = f.read()
        return [types.TextContent(type="text", text=f"File: {files[0]}\n\n{content}")]

    elif name == "insert_topic":
        title = arguments["title"]
        # Check for duplicate
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM topics WHERE title=?", (title,)
        ).fetchone()
        if existing:
            conn.close()
            return [types.TextContent(type="text", text=f"Skipped (duplicate): {title}")]
        conn.execute(
            "INSERT INTO topics (title, description, category, source_type, source_url, source_quote, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'new')",
            (
                title,
                arguments.get("description", ""),
                arguments.get("category", ""),
                arguments.get("source_type", ""),
                arguments.get("source_url", ""),
                arguments.get("source_quote", ""),
            )
        )
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return [types.TextContent(type="text", text=f"Inserted topic #{new_id}: {title}")]

    elif name == "get_all_topic_titles":
        conn = get_db()
        rows = conn.execute(
            "SELECT title FROM topics WHERE status NOT LIKE '%archived%'"
        ).fetchall()
        conn.close()
        titles = [r[0] for r in rows]
        return [types.TextContent(type="text", text=json.dumps(titles, ensure_ascii=False))]

    elif name == "finalize_draft":
        # Find latest draft by modification time, skip outline-*.md files
        all_files = glob.glob(os.path.join(DRAFTS_DIR, "*.md"))
        files = [f for f in all_files if not os.path.basename(f).startswith("outline-")]
        if not files:
            return [types.TextContent(type="text", text="No draft files found.")]
        filepath = max(files, key=os.path.getmtime)

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract topic_id from frontmatter (case-insensitive)
        topic_id = None
        for line in content.splitlines():
            if line.lower().startswith("topic_id:"):
                try:
                    topic_id = int(line.split(":", 1)[1].strip())
                except:
                    pass

        # Update status in frontmatter (handle both cases: "status: draft" or "Status: draft")
        content = re.sub(r'(?i)^status:\s*draft', 'status: ready', content, count=1, flags=re.MULTILINE)

        # Add author block if not present
        author_block = "\n---\n**Author:** Serhii Baliasnyi, Founder & CEO, AIMediaFlow"
        if "Serhii Baliasnyi" not in content:
            content = content.rstrip() + author_block + "\n"

        # Save updated file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        # Update DB if topic_id found
        if topic_id:
            conn = get_db()
            conn.execute(
                "UPDATE topics SET status='ready', checked_at=datetime('now') WHERE id=?",
                (topic_id,)
            )
            conn.commit()
            conn.close()
            db_msg = f"Topic {topic_id} status set to ready."
        else:
            db_msg = "Warning: topic_id not found in frontmatter, DB not updated."

        filename = os.path.basename(filepath)
        slug = os.path.splitext(filename)[0]
        word_count = len(content.split())

        # Generate cover image via HuggingFace FLUX.1-schnell
        cover_msg = "Cover image: skipped (no HF key)."
        hf_key = ""
        env_path = os.path.join(os.path.dirname(DB_PATH), ".env")
        try:
            with open(env_path) as ef:
                for line in ef:
                    if line.startswith("HUGGINGFACE_API_KEY="):
                        hf_key = line.split("=", 1)[1].strip()
        except Exception:
            pass

        if hf_key:
            covers_dir = os.path.join(os.path.dirname(DB_PATH), "blog-covers")
            os.makedirs(covers_dir, exist_ok=True)
            cover_path = os.path.join(covers_dir, f"{slug}.jpg")
            if not os.path.exists(cover_path):
                # Extract title for prompt
                title = slug.replace("-", " ")
                for line in content.splitlines():
                    if re.match(r'(?i)^title:', line):
                        title = line.split(":", 1)[1].strip().strip('"')
                        break
                try:
                    hf_url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
                    resp = requests.post(
                        hf_url,
                        headers={"Authorization": f"Bearer {hf_key}", "Content-Type": "application/json"},
                        json={"inputs": f"Professional editorial blog cover photo for article: {title}. Business technology, Irish SME, modern office, 16:9 format.",
                              "parameters": {"num_inference_steps": 4, "width": 1024, "height": 576}},
                        timeout=120
                    )
                    if resp.status_code == 200:
                        with open(cover_path, "wb") as cf:
                            cf.write(resp.content)
                        size_kb = len(resp.content) // 1024
                        # Update frontmatter cover_image field
                        cover_rel = f"blog-covers/{slug}.jpg"
                        if "cover_image:" in content:
                            content = re.sub(r'(?i)^cover_image:.*', f'cover_image: {cover_rel}', content, flags=re.MULTILINE)
                        else:
                            content = content.replace("status: ready", f"status: ready\ncover_image: {cover_rel}", 1)
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(content)
                        cover_msg = f"Cover image: {slug}.jpg ({size_kb}KB)."
                    else:
                        cover_msg = f"Cover image: HF API error {resp.status_code}."
                except Exception as e:
                    cover_msg = f"Cover image: failed ({e})."
            else:
                cover_msg = f"Cover image: already exists."

        return [types.TextContent(type="text", text=f"Finalized: {filename} ({word_count} words). {db_msg} {cover_msg}\nMEDIA:{filepath}")]

    elif name == "lookup_article":
        article_id = arguments.get("article_id")
        slug = arguments.get("slug")
        conn = get_db()
        if article_id:
            row = conn.execute("SELECT id, title, slug, status FROM topics WHERE id = ?", (article_id,)).fetchone()
        elif slug:
            row = conn.execute("SELECT id, title, slug, status FROM topics WHERE slug = ?", (slug,)).fetchone()
        else:
            conn.close()
            return [types.TextContent(type="text", text="Error: provide article_id or slug")]
        conn.close()
        if not row:
            return [types.TextContent(type="text", text=f"Article not found")]
        result = dict(row)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "create_pipeline_issue":
        agent = arguments.get("agent", "")
        title = arguments.get("title", "")
        description = arguments.get("description", "")
        agent_id = AGENT_IDS.get(agent)
        if not agent_id:
            return [types.TextContent(type="text", text=f"Unknown agent: {agent}. Valid: {', '.join(AGENT_IDS.keys())}")]
        payload = {
            "title": title,
            "description": description,
            "assigneeAgentId": agent_id,
            "status": "todo",
            "priority": "high"
        }
        resp = requests.post(
            f"{PAPERCLIP_API_URL}/api/companies/{COMPANY_ID}/issues",
            headers={"Authorization": f"Bearer {PAPERCLIP_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            issue_id = data.get("id", "?")
            return [types.TextContent(type="text", text=f"Issue created: #{issue_id} assigned to {agent} ({agent_id}). Title: {title}")]
        else:
            return [types.TextContent(type="text", text=f"Failed to create issue: {resp.status_code} {resp.text[:200]}")]

    elif name == "get_pipeline_status":
        conn = get_db()
        rows = conn.execute("SELECT status, COUNT(*) as cnt FROM topics GROUP BY status").fetchall()
        conn.close()
        counts = {row["status"]: row["cnt"] for row in rows}
        # Get pending issues
        issues_resp = requests.get(
            f"{PAPERCLIP_API_URL}/api/companies/{COMPANY_ID}/issues?status=todo&limit=20",
            headers={"Authorization": f"Bearer {PAPERCLIP_API_KEY}"},
            timeout=10
        )
        pending = []
        if issues_resp.status_code == 200:
            data = issues_resp.json()
            issues = data if isinstance(data, list) else data.get("issues", data.get("data", []))
            for iss in issues:
                pending.append(f"#{iss.get('issueNumber','?')} [{iss.get('status','?')}] {iss.get('title','?')}")
        result = {
            "topic_counts": counts,
            "pending_issues": pending
        }
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


    elif name == "publish_to_notion":
        import re as _re
        import time as _time
        NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
        NOTION_DB_ID = os.environ.get("NOTION_DATABASE_ID", "")
        if not NOTION_TOKEN or not NOTION_DB_ID:
            env_path = "/home/hermes_user/.hermes/.env"
            try:
                with open(env_path) as ef:
                    for line in ef:
                        if line.startswith("NOTION_TOKEN="):
                            NOTION_TOKEN = line.split("=", 1)[1].strip()
                        elif line.startswith("NOTION_DATABASE_ID="):
                            NOTION_DB_ID = line.split("=", 1)[1].strip()
            except Exception:
                pass
        if not NOTION_TOKEN or not NOTION_DB_ID:
            return [types.TextContent(type="text", text="Error: NOTION_TOKEN or NOTION_DATABASE_ID not set in env or .env file")]

        # Find latest ready draft by mtime, skip outline-*.md
        all_files = glob.glob(os.path.join(DRAFTS_DIR, "*.md"))
        files = sorted(
            [f for f in all_files if not os.path.basename(f).startswith("outline-")],
            key=os.path.getmtime, reverse=True
        )
        if not files:
            return [types.TextContent(type="text", text="No draft files found.")]

        filepath = None
        for f in files:
            with open(f) as fh:
                head = fh.read(500)
            if "status: ready" in head or "status:ready" in head:
                filepath = f
                break
        if not filepath:
            return [types.TextContent(type="text", text="No ready articles found in blog-drafts.")]

        with open(filepath) as fh:
            raw = fh.read()

        fm_match = _re.match(r"---\n(.*?)\n---", raw, _re.DOTALL)
        fm = {}
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
        body = raw[fm_match.end():].strip() if fm_match else raw

        slug = os.path.splitext(os.path.basename(filepath))[0]
        title = fm.get("title", slug)
        date = fm.get("date", slug[:10])
        meta = fm.get("meta_description", "")[:2000]
        cover_url = fm.get("cover_image", "")
        if cover_url and not cover_url.startswith("http"):
            cover_url = "https://aimediaflow.net/" + cover_url.lstrip("/")

        notion_headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        # Check duplicate by slug
        check = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
            headers=notion_headers,
            json={"filter": {"property": "Slug", "rich_text": {"equals": slug}}},
            timeout=15
        )
        if check.status_code == 200 and check.json().get("results"):
            return [types.TextContent(type="text", text=f"Already published in Notion: {slug}")]

        # Convert markdown to Notion blocks
        def md_to_blocks(md):
            blocks = []
            for line in md.splitlines():
                line = line.rstrip()
                if not line:
                    continue
                if line.startswith("### "):
                    blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:][:2000]}}]}})
                elif line.startswith("## "):
                    blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:][:2000]}}]}})
                elif line.startswith("# "):
                    blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]}})
                elif line.startswith("- ") or line.startswith("* "):
                    blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]}})
                elif line.startswith("> "):
                    blocks.append({"object": "block", "type": "quote", "quote": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]}})
                else:
                    blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]}})
            return blocks

        blocks = md_to_blocks(body)

        props = {
            "Name": {"title": [{"type": "text", "text": {"content": title[:2000]}}]},
            "Title": {"rich_text": [{"type": "text", "text": {"content": title[:2000]}}]},
            "Status": {"select": {"name": "ready"}},
            "Slug": {"rich_text": [{"type": "text", "text": {"content": slug}}]},
            "Meta Description": {"rich_text": [{"type": "text", "text": {"content": meta}}]},
        }
        if date:
            props["Date"] = {"date": {"start": date[:10]}}
        if cover_url:
            props["Cover URL"] = {"url": cover_url}

        create_resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=notion_headers,
            json={"parent": {"database_id": NOTION_DB_ID}, "properties": props, "children": blocks[:100]},
            timeout=30
        )
        if create_resp.status_code not in (200, 201):
            return [types.TextContent(type="text", text=f"Notion API error: {create_resp.status_code} {create_resp.text[:300]}")]

        page_id = create_resp.json()["id"]

        for i in range(100, len(blocks), 100):
            requests.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=notion_headers,
                json={"children": blocks[i:i + 100]},
                timeout=30
            )
            _time.sleep(0.35)

        page_url = f"https://notion.so/{page_id.replace('-', '')}"
        return [types.TextContent(type="text", text=f"Published to Notion: {title}\nSlug: {slug}\nPage: {page_url}")]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

# ===== NOTION PUBLISH PATCH =====
