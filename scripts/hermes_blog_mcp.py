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
from datetime import datetime
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

DB_PATH = "/home/hermes_user/.hermes/topics-db.sqlite"
OUTLINES_DIR = "/home/hermes_user/.hermes/blog-outlines"
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
            name="finalize_draft",
            description="Finalize the latest draft: sets status to ready, adds author block, updates DB. Returns the file path for delivery.",
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
        # Find latest draft
        files = sorted(glob.glob(os.path.join(DRAFTS_DIR, "*.md")), reverse=True)
        if not files:
            return [types.TextContent(type="text", text="No draft files found.")]
        filepath = files[0]
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
        word_count = len(content.split())
        return [types.TextContent(type="text", text=f"Finalized: {filename} ({word_count} words). {db_msg}\nMEDIA:{filepath}")]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
