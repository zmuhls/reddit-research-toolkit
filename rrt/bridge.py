"""Conversions between dataset folders and the analyzers' SQLite database.

The analyzers under analyzers/ were written against the database that
core/reddit_scraper.py builds. build_database() makes the same tables from a
dataset folder, so 'python main.py analyze' can run them on any dataset,
including the synthetic sample. database_to_dataset() goes the other way, so
an archive collected with tools/cli.py opens in the dashboard and in pandas
like any other dataset.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .datasets import COMMENTS_FILE, POSTS_FILE, STATUS_COMPLETE, DatasetWriter, load_manifest, slugify, utc_iso

_SCHEMA = """
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    status TEXT DEFAULT 'completed',
    discovered_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    discovery_source TEXT,
    post_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    total_karma INTEGER DEFAULT 0,
    account_created TEXT,
    error_message TEXT,
    last_attempt TEXT
);
CREATE TABLE submissions (
    id TEXT PRIMARY KEY,
    title TEXT,
    selftext TEXT,
    author TEXT,
    created_utc INTEGER,
    score INTEGER,
    upvote_ratio REAL,
    num_comments INTEGER,
    permalink TEXT,
    url TEXT,
    domain TEXT,
    flair_text TEXT,
    is_self BOOLEAN,
    stickied BOOLEAN,
    locked BOOLEAN,
    source_user TEXT,
    collected_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    body TEXT,
    author TEXT,
    created_utc INTEGER,
    score INTEGER,
    submission_id TEXT,
    parent_id TEXT,
    permalink TEXT,
    is_submitter BOOLEAN,
    stickied BOOLEAN,
    source_user TEXT,
    collected_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_submissions_author ON submissions(author);
CREATE INDEX idx_submissions_created ON submissions(created_utc);
CREATE INDEX idx_comments_author ON comments(author);
CREATE INDEX idx_comments_submission ON comments(submission_id);
CREATE INDEX idx_comments_created ON comments(created_utc);
"""


def _epoch(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _flag(value: Any) -> int:
    return 1 if str(value).strip().lower() in ("true", "1", "yes") else 0


def _number(value: Any, kind=int):
    try:
        return kind(float(value))
    except (TypeError, ValueError):
        return None


def build_database(dataset_path: Path, db_path: Optional[Path] = None) -> Path:
    """Write the analyzers' SQLite database for a dataset. Returns the database path."""
    dataset_path = Path(dataset_path)
    manifest = load_manifest(dataset_path)
    subreddits = manifest.get("subreddits") or []
    label = subreddits[0] if len(subreddits) == 1 else slugify("+".join(subreddits) or dataset_path.name)

    if db_path is None:
        reports = dataset_path / "reports"
        reports.mkdir(exist_ok=True)
        db_path = reports / f"{label}.db"
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()

    activity: Dict[str, Dict[str, int]] = {}
    csv.field_size_limit(min(2 ** 31 - 1, 10 ** 9))

    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)

        with open(dataset_path / POSTS_FILE, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                author = row.get("author") or "[deleted]"
                conn.execute(
                    "INSERT OR IGNORE INTO submissions (id, title, selftext, author, created_utc, score, upvote_ratio, "
                    "num_comments, permalink, url, domain, flair_text, is_self, stickied, locked, source_user) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (
                        row.get("post_id"), row.get("title"), row.get("selftext"), author, _epoch(row.get("created_utc")),
                        _number(row.get("score")), _number(row.get("upvote_ratio"), float), _number(row.get("num_comments")),
                        row.get("permalink"), row.get("url"), row.get("domain"), row.get("flair"),
                        _flag(row.get("is_self")), _flag(row.get("stickied")), author,
                    ),
                )
                activity.setdefault(author, {"posts": 0, "comments": 0})["posts"] += 1

        comments_path = dataset_path / COMMENTS_FILE
        if comments_path.exists():
            with open(comments_path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    author = row.get("author") or "[deleted]"
                    conn.execute(
                        "INSERT OR IGNORE INTO comments (id, body, author, created_utc, score, submission_id, parent_id, "
                        "permalink, is_submitter, stickied, source_user) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row.get("comment_id"), row.get("body"), author, _epoch(row.get("created_utc")),
                            _number(row.get("score")), f"t3_{row.get('post_id')}", row.get("parent_id"),
                            row.get("permalink"), _flag(row.get("is_submitter")), _flag(row.get("stickied")), author,
                        ),
                    )
                    activity.setdefault(author, {"posts": 0, "comments": 0})["comments"] += 1

        for username, counts in activity.items():
            if username == "[deleted]":
                continue
            conn.execute(
                "INSERT OR IGNORE INTO users (username, status, discovery_source, post_count, comment_count) "
                "VALUES (?, 'completed', 'dataset', ?, ?)",
                (username, counts["posts"], counts["comments"]),
            )
        conn.commit()
    return db_path


def _depths(conn: sqlite3.Connection) -> Dict[str, int]:
    """Thread depth of every comment, worked out from parent links.

    A comment whose parent is the post, or whose parent comment was not
    collected, counts as depth 0.
    """
    parents = {row[0]: row[1] or "" for row in conn.execute("SELECT id, parent_id FROM comments")}
    depths: Dict[str, int] = {}
    for start in parents:
        chain = []
        current = start
        while True:
            if current in depths:
                base = depths[current]
                break
            chain.append(current)
            parent = parents.get(current, "")
            if not parent.startswith("t1_") or parent[3:] not in parents or len(chain) > 1000:
                base = -1
                break
            current = parent[3:]
        for node in reversed(chain):
            base += 1
            depths[node] = base
    return depths


def database_to_dataset(db_path: Path, subreddit: str, root: Optional[Path] = None) -> Path:
    """Write a dataset folder from a database made by core/reddit_scraper.py."""
    db_path = Path(db_path)
    writer = DatasetWriter(
        [subreddit],
        {"method": "user-centric", "database": db_path.name},
        root=root,
        notes="Exported from a user-centric archive. Rows cover the activity of discovered users in this "
              "community, so coverage follows the users, not a single listing.",
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute("SELECT * FROM submissions ORDER BY created_utc"):
            row = dict(row)
            permalink = row.get("permalink") or ""
            writer.add_post({
                "post_id": row.get("id"),
                "subreddit": subreddit,
                "title": row.get("title"),
                "author": row.get("author"),
                "created_utc": utc_iso(row["created_utc"]) if row.get("created_utc") is not None else "",
                "score": row.get("score"),
                "upvote_ratio": row.get("upvote_ratio"),
                "num_comments": row.get("num_comments"),
                "flair": row.get("flair_text"),
                "is_self": bool(row.get("is_self")),
                "is_video": "",
                "over_18": "",
                "spoiler": "",
                "stickied": bool(row.get("stickied")),
                "domain": row.get("domain"),
                "url": row.get("url"),
                "permalink": f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink,
                "selftext": row.get("selftext"),
            })
        depths = _depths(conn)
        for row in conn.execute("SELECT * FROM comments ORDER BY created_utc"):
            row = dict(row)
            permalink = row.get("permalink") or ""
            writer.add_comment({
                "comment_id": row.get("id"),
                "post_id": str(row.get("submission_id") or "").replace("t3_", ""),
                "parent_id": row.get("parent_id"),
                "subreddit": subreddit,
                "author": row.get("author"),
                "created_utc": utc_iso(row["created_utc"]) if row.get("created_utc") is not None else "",
                "score": row.get("score"),
                "depth": depths.get(row.get("id"), 0),
                "is_submitter": bool(row.get("is_submitter")),
                "stickied": bool(row.get("stickied")),
                "edited": "",
                "permalink": f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink,
                "body": row.get("body"),
            })
    return writer.close(STATUS_COMPLETE)
