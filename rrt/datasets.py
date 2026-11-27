"""Dataset folders: one self-contained folder per scrape.

A dataset folder holds everything a reader needs to use the data without the
terminal session that produced it:

    data/cuny_20261127-141502/
        posts.csv        one row per post
        comments.csv     one row per comment (absent for posts-only scrapes)
        manifest.json    what was collected, when, how, and how much
        README.md        codebook: every column explained, loading snippets

The same layout, zipped, is what the companion dashboard reads and writes, so
a folder made here opens there and the reverse.

This module uses only the standard library. pandas is imported inside
read_dataset() so that listing and writing datasets works without it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import REPO_ROOT, __version__

FORMAT_NAME = "reddit-research-dataset"
FORMAT_VERSION = 1

POSTS_FILE = "posts.csv"
COMMENTS_FILE = "comments.csv"
MANIFEST_FILE = "manifest.json"
README_FILE = "README.md"
JSON_FILE = "data.json"

# Column order is the order written to disk. The descriptions feed the codebook.
POST_COLUMNS: Dict[str, str] = {
    "post_id": "Reddit's ID for the post. Joins to comments.post_id.",
    "subreddit": "Community the post was collected from, without the r/ prefix.",
    "title": "Post title.",
    "author": "Username of the poster, or [deleted] when the account or post was removed.",
    "created_utc": "When the post was made, in UTC (ISO 8601, for example 2026-11-27T14:15:02Z).",
    "score": "Upvotes minus downvotes at collection time. Reddit fuzzes this number slightly.",
    "upvote_ratio": "Share of votes that were upvotes, from 0 to 1.",
    "num_comments": "Comment count Reddit reported for the post. Can exceed the rows in comments.csv.",
    "flair": "Flair label the community attached to the post, if any.",
    "is_self": "True for text posts, False for link, image, or video posts.",
    "is_video": "True when Reddit hosts a video for the post.",
    "over_18": "True when the post is marked NSFW.",
    "spoiler": "True when the post is marked as a spoiler.",
    "stickied": "True when moderators pinned the post.",
    "domain": "Site the post links to (self.<subreddit> for text posts).",
    "url": "Link target of the post.",
    "permalink": "Address of the discussion thread on Reddit.",
    "selftext": "Body text of a text post. Empty for link posts.",
}

COMMENT_COLUMNS: Dict[str, str] = {
    "comment_id": "Reddit's ID for the comment.",
    "post_id": "ID of the post the comment belongs to. Joins to posts.post_id.",
    "parent_id": "The item this comment replies to. t3_<post_id> marks a top-level comment, and t1_<comment_id> marks a reply to another comment.",
    "subreddit": "Community the comment was collected from.",
    "author": "Username of the commenter, or [deleted].",
    "created_utc": "When the comment was made, in UTC (ISO 8601).",
    "score": "Upvotes minus downvotes at collection time.",
    "depth": "Nesting level in the thread. 0 is a top-level comment.",
    "is_submitter": "True when the commenter also wrote the post.",
    "stickied": "True when moderators pinned the comment.",
    "edited": "True when the author edited the comment after posting.",
    "permalink": "Address of the comment on Reddit.",
    "body": "Comment text.",
}

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_INTERRUPTED = "interrupted"
STATUS_FAILED = "failed"


class DatasetError(Exception):
    """A dataset could not be found, read, or written. The message is user-facing."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def data_root(override: Optional[str] = None) -> Path:
    """Folder that holds all dataset folders.

    Order of precedence: an explicit --data-dir, the RRT_DATA_DIR environment
    variable, then data/ beside main.py.
    """
    chosen = override or os.environ.get("RRT_DATA_DIR")
    return Path(chosen).expanduser() if chosen else REPO_ROOT / "data"


def slugify(text: str) -> str:
    """Lowercase, filesystem-safe version of a subreddit name or label."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").lower()
    return slug or "dataset"


def utc_iso(epoch_seconds: float) -> str:
    """Turn Reddit's epoch timestamp into an unambiguous UTC string."""
    return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_cell(value: Any) -> Any:
    """Strip stray NUL bytes, which break CSV readers, and turn None into an empty cell."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

class DatasetWriter:
    """Writes one dataset folder, row by row.

    Rows reach the disk as they arrive, so an interrupted scrape retains the
    rows it had collected. close() records the final status in the manifest.
    """

    def __init__(
        self,
        subreddits: Iterable[str],
        query: Optional[Dict[str, Any]] = None,
        *,
        root: Optional[Path] = None,
        source: str = "reddit-api",
        tool: str = "reddit-research-toolkit",
        tool_version: str = __version__,
        label: Optional[str] = None,
        notes: str = "",
    ) -> None:
        self.subreddits = [s for s in subreddits if s]
        self.query = dict(query or {})
        self.source = source
        self.tool = tool
        self.tool_version = tool_version
        self.notes = notes
        self.root = Path(root) if root else data_root()
        self.root.mkdir(parents=True, exist_ok=True)

        base = slugify(label or "+".join(self.subreddits) or "dataset")[:60]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = self.root / f"{base}_{stamp}"
        suffix = 2
        while candidate.exists():
            candidate = self.root / f"{base}_{stamp}-{suffix}"
            suffix += 1
        candidate.mkdir(parents=True)
        self.path = candidate
        self.dataset_id = candidate.name

        self.created_utc = now_utc_iso()
        self.post_count = 0
        self.comment_count = 0
        self._authors: set = set()
        self._first_post: Optional[str] = None
        self._last_post: Optional[str] = None
        self._handles: Dict[str, Any] = {}
        self._writers: Dict[str, csv.DictWriter] = {}
        self._closed = False

        self._write_manifest(STATUS_IN_PROGRESS)

    # -- rows ---------------------------------------------------------------

    def _writer(self, filename: str, columns: Iterable[str]) -> csv.DictWriter:
        if filename not in self._writers:
            handle = open(self.path / filename, "w", newline="", encoding="utf-8")
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            self._handles[filename] = handle
            self._writers[filename] = writer
        return self._writers[filename]

    def add_post(self, post: Dict[str, Any]) -> None:
        writer = self._writer(POSTS_FILE, POST_COLUMNS)
        writer.writerow({key: _clean_cell(post.get(key)) for key in POST_COLUMNS})
        self.post_count += 1
        author = post.get("author")
        if author and author != "[deleted]":
            self._authors.add(author)
        created = post.get("created_utc")
        if created:
            created = str(created)
            if self._first_post is None or created < self._first_post:
                self._first_post = created
            if self._last_post is None or created > self._last_post:
                self._last_post = created

    def add_comment(self, comment: Dict[str, Any]) -> None:
        writer = self._writer(COMMENTS_FILE, COMMENT_COLUMNS)
        writer.writerow({key: _clean_cell(comment.get(key)) for key in COMMENT_COLUMNS})
        self.comment_count += 1
        author = comment.get("author")
        if author and author != "[deleted]":
            self._authors.add(author)

    def flush(self) -> None:
        for handle in self._handles.values():
            handle.flush()

    # -- finishing ----------------------------------------------------------

    def close(self, status: str = STATUS_COMPLETE, *, write_json: bool = False, error: str = "") -> Path:
        """Close the files, then write the manifest and the codebook."""
        if self._closed:
            return self.path
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        self._writers.clear()
        self._closed = True

        if write_json:
            export_json(self.path, manifest_stub=self._manifest_dict(status, error))
        manifest = self._write_manifest(status, error)
        (self.path / README_FILE).write_text(render_codebook(manifest), encoding="utf-8")
        return self.path

    def _manifest_dict(self, status: str, error: str = "") -> Dict[str, Any]:
        files: Dict[str, Any] = {}
        for filename, count in ((POSTS_FILE, self.post_count), (COMMENTS_FILE, self.comment_count), (JSON_FILE, None)):
            file_path = self.path / filename
            if file_path.exists() and status != STATUS_IN_PROGRESS:
                entry: Dict[str, Any] = {"bytes": file_path.stat().st_size, "sha256": _sha256(file_path)}
                if count is not None:
                    entry["rows"] = count
                files[filename] = entry
        manifest: Dict[str, Any] = {
            "format": FORMAT_NAME,
            "format_version": FORMAT_VERSION,
            "dataset_id": self.dataset_id,
            "status": status,
            "created_utc": self.created_utc,
            "finished_utc": None if status == STATUS_IN_PROGRESS else now_utc_iso(),
            "tool": {"name": self.tool, "version": self.tool_version},
            "source": self.source,
            "subreddits": self.subreddits,
            "query": self.query,
            "counts": {
                "posts": self.post_count,
                "comments": self.comment_count,
                "authors": len(self._authors),
            },
            "date_range": {"first_post_utc": self._first_post, "last_post_utc": self._last_post},
            "timezone": "UTC",
            "files": files,
        }
        if self.notes:
            manifest["notes"] = self.notes
        if error:
            manifest["error"] = error
        return manifest

    def _write_manifest(self, status: str, error: str = "") -> Dict[str, Any]:
        manifest = self._manifest_dict(status, error)
        (self.path / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest


def export_json(dataset_path: Path, manifest_stub: Optional[Dict[str, Any]] = None) -> Path:
    """Write data.json: the posts and comments of a dataset in one JSON file."""
    dataset_path = Path(dataset_path)
    payload: Dict[str, Any] = {"manifest": manifest_stub or load_manifest(dataset_path), "posts": [], "comments": []}
    for key, filename in (("posts", POSTS_FILE), ("comments", COMMENTS_FILE)):
        file_path = dataset_path / filename
        if file_path.exists():
            with open(file_path, newline="", encoding="utf-8") as handle:
                payload[key] = list(csv.DictReader(handle))
    target = dataset_path / JSON_FILE
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# Codebook
# --------------------------------------------------------------------------

def render_codebook(manifest: Dict[str, Any]) -> str:
    """Human-readable README for a dataset folder."""
    counts = manifest.get("counts", {})
    query = manifest.get("query", {})
    date_range = manifest.get("date_range", {})
    subs = manifest.get("subreddits") or []
    sub_text = ", ".join(f"r/{s}" for s in subs) or "unknown"
    status = manifest.get("status", STATUS_COMPLETE)
    source = manifest.get("source", "reddit-api")
    dataset_id = manifest.get("dataset_id", "dataset")
    has_comments = COMMENTS_FILE in manifest.get("files", {}) or counts.get("comments", 0) > 0

    lines: List[str] = [f"# Dataset {dataset_id}", ""]

    if source == "synthetic":
        lines += [
            "> **Synthetic sample.** A program invented every row in this folder so that",
            "> you can practice loading and charting data without Reddit credentials.",
            "> No post, comment, or username here is real. Do not cite it as evidence.",
            "",
        ]
    if status == STATUS_INTERRUPTED:
        lines += [
            "> **Partial dataset.** Collection stopped early. The rows present are valid,",
            "> but the folder does not cover everything the query asked for.",
            "",
        ]
    elif status == STATUS_FAILED:
        lines += [
            "> **Partial dataset.** Collection ended with an error"
            + (f" ({manifest.get('error')})" if manifest.get("error") else "")
            + ". The rows present are valid.",
            "",
        ]

    lines += [
        "## Contents",
        "",
        "| | |",
        "|---|---|",
        f"| Community | {sub_text} |",
        f"| Posts | {counts.get('posts', 0):,} |",
        f"| Comments | {counts.get('comments', 0):,} |",
        f"| Distinct authors | {counts.get('authors', 0):,} |",
        f"| Earliest post (UTC) | {date_range.get('first_post_utc') or 'n/a'} |",
        f"| Latest post (UTC) | {date_range.get('last_post_utc') or 'n/a'} |",
        f"| Collected (UTC) | {manifest.get('created_utc', 'n/a')} |",
        f"| Collected with | {manifest.get('tool', {}).get('name', 'unknown')} {manifest.get('tool', {}).get('version', '')} |",
    ]
    if query:
        described = ", ".join(f"{key}={value}" for key, value in query.items() if value is not None)
        lines.append(f"| Query | {described} |")
    lines += [
        "",
        "`manifest.json` holds the same facts in machine-readable form, plus a SHA-256",
        "checksum for each data file.",
        "",
        "## Load it",
        "",
        "Python:",
        "",
        "```python",
        "import pandas as pd",
        "",
        'posts = pd.read_csv("posts.csv", parse_dates=["created_utc"])',
    ]
    if has_comments:
        lines.append('comments = pd.read_csv("comments.csv", parse_dates=["created_utc"])')
    lines += [
        "",
        "# Timestamps are UTC. Convert before charting by hour or weekday:",
        'posts["created_local"] = posts["created_utc"].dt.tz_convert("America/New_York")',
        "```",
        "",
        "R:",
        "",
        "```r",
        "library(readr)",
        'posts <- read_csv("posts.csv")',
    ]
    if has_comments:
        lines.append('comments <- read_csv("comments.csv")')
    lines += [
        "```",
        "",
        "Spreadsheet apps open both files directly. Choose UTF-8 if the app asks for an",
        "encoding.",
        "",
        "## posts.csv",
        "",
        "| Column | Meaning |",
        "|---|---|",
    ]
    lines += [f"| `{name}` | {meaning} |" for name, meaning in POST_COLUMNS.items()]
    if has_comments:
        lines += ["", "## comments.csv", "", "| Column | Meaning |", "|---|---|"]
        lines += [f"| `{name}` | {meaning} |" for name, meaning in COMMENT_COLUMNS.items()]
        lines += [
            "",
            "To rebuild a thread, follow `parent_id`: a value that starts with `t3_` points",
            "at the post, and a value that starts with `t1_` points at another comment.",
        ]
    lines += [
        "",
        "## Limits of this data",
        "",
        "- Reddit listings return roughly 1,000 posts at most per sort order, so a",
        "  dataset is a sample of a community, not its full history.",
        "- Scores and comment counts are snapshots from the moment of collection.",
        "- Removed and deleted content appears as `[deleted]` or `[removed]`.",
    ]
    if source != "synthetic":
        lines += [
            "",
            "## Handling",
            "",
            "- These rows are public posts by real people. Report patterns, quote sparingly,",
            "  and leave usernames out of anything you publish or present.",
            "- Reddit's terms do not allow redistributing its data. Share this folder with",
            "  your class or research team, not on the open web.",
            "- When someone deletes a post or comment on Reddit, delete it from your copy too.",
            "- The text comes from strangers. If a spreadsheet app offers to run a formula or",
            "  follow a link from one of these cells, decline.",
        ]
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def load_manifest(dataset_path: Path) -> Dict[str, Any]:
    manifest_path = Path(dataset_path) / MANIFEST_FILE
    if not manifest_path.exists():
        raise DatasetError(f"{dataset_path} has no {MANIFEST_FILE}, so it is not a dataset folder.")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Could not read {manifest_path}: {exc}") from exc


def list_datasets(root: Optional[Path] = None) -> List[Tuple[Path, Dict[str, Any]]]:
    """All dataset folders under the data root, newest first."""
    root = Path(root) if root else data_root()
    if not root.is_dir():
        return []
    found: List[Tuple[Path, Dict[str, Any]]] = []
    for child in root.iterdir():
        if child.is_dir() and (child / MANIFEST_FILE).exists():
            try:
                found.append((child, load_manifest(child)))
            except DatasetError:
                continue
    found.sort(key=lambda item: item[1].get("created_utc", ""), reverse=True)
    return found


def resolve_dataset(name: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Find a dataset from what the user typed.

    Accepts nothing or "latest" (newest dataset), a folder path, a full dataset
    name, the label before the timestamp (newest dataset with that label), or
    any part of a name that matches exactly one dataset.
    """
    root = Path(root) if root else data_root()
    if name and name != "latest":
        direct = Path(name).expanduser()
        if direct.is_dir() and (direct / MANIFEST_FILE).exists():
            return direct
        if direct.is_dir() and not (direct / MANIFEST_FILE).exists():
            raise DatasetError(
                f"{direct} is a folder, but it has no {MANIFEST_FILE}. "
                "To wrap loose CSV files as a dataset, run: python main.py import <posts.csv> [comments.csv]"
            )

    datasets = list_datasets(root)
    if not datasets:
        raise DatasetError(
            f"No datasets in {root} yet. Make one with 'python main.py sample' (no credentials needed) "
            "or 'python main.py scrape <subreddit>'."
        )
    if not name or name == "latest":
        return datasets[0][0]

    wanted = name.strip().rstrip("/\\").lower()
    exact = [path for path, _ in datasets if path.name.lower() == wanted]
    if exact:
        return exact[0]
    # 'cuny' means the newest cuny_<timestamp> folder. The list is newest first.
    same_label = [path for path, _ in datasets if path.name.lower().rsplit("_", 1)[0] == wanted]
    if same_label:
        return same_label[0]
    partial = [path for path, _ in datasets if path.name.lower().startswith(wanted) or wanted in path.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        options = ", ".join(path.name for path in partial[:6])
        raise DatasetError(f"'{name}' matches more than one dataset: {options}. Type more of the name.")
    raise DatasetError(f"No dataset named '{name}' in {root}. Run 'python main.py list' to see what is there.")


def read_dataset(dataset_path: Path):
    """Return (posts, comments, manifest) with timestamps parsed as UTC.

    comments is an empty DataFrame when the dataset has no comments file.
    """
    import pandas as pd

    dataset_path = Path(dataset_path)
    manifest = load_manifest(dataset_path)
    posts_path = dataset_path / POSTS_FILE
    if not posts_path.exists():
        raise DatasetError(f"{dataset_path} has no {POSTS_FILE}.")
    posts = pd.read_csv(posts_path, dtype={"post_id": str}, keep_default_na=False, na_values=[""])
    comments_path = dataset_path / COMMENTS_FILE
    if comments_path.exists():
        comments = pd.read_csv(
            comments_path,
            dtype={"comment_id": str, "post_id": str, "parent_id": str},
            keep_default_na=False,
            na_values=[""],
        )
    else:
        comments = pd.DataFrame(columns=list(COMMENT_COLUMNS))
    for frame in (posts, comments):
        if "created_utc" in frame.columns:
            # ISO8601 accepts every variant in one column: with or without a zone,
            # with a T or a space between date and time.
            frame["created_utc"] = pd.to_datetime(frame["created_utc"], utc=True, errors="coerce", format="ISO8601")
    return posts, comments, manifest


# --------------------------------------------------------------------------
# Sharing: zip out, zip in, wrap loose CSVs
# --------------------------------------------------------------------------

def export_zip(dataset_path: Path, destination: Optional[Path] = None) -> Path:
    """Zip a dataset folder for sharing. Returns the zip path."""
    dataset_path = Path(dataset_path)
    load_manifest(dataset_path)
    destination = Path(destination) if destination else dataset_path.parent / f"{dataset_path.name}.zip"
    if destination.is_dir():
        destination = destination / f"{dataset_path.name}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in (MANIFEST_FILE, README_FILE, POSTS_FILE, COMMENTS_FILE, JSON_FILE):
            file_path = dataset_path / filename
            if file_path.exists():
                archive.write(file_path, arcname=f"{dataset_path.name}/{filename}")
    return destination


_ALLOWED_IN_ZIP = {MANIFEST_FILE, README_FILE, POSTS_FILE, COMMENTS_FILE, JSON_FILE}
_MAX_UNZIPPED_BYTES = 2 * 1024 ** 3


def import_zip(zip_path: Path, root: Optional[Path] = None, max_bytes: int = _MAX_UNZIPPED_BYTES) -> Path:
    """Unpack a shared dataset zip into the data root. Returns the new folder.

    Only the five known file names are extracted, and only by base name, so an
    archive cannot write outside the dataset folder. max_bytes caps the
    unpacked size, which stops a small hostile archive from filling the disk.
    """
    zip_path = Path(zip_path).expanduser()
    root = Path(root) if root else data_root()
    if not zip_path.exists():
        raise DatasetError(f"No file at {zip_path}.")
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise DatasetError(f"{zip_path.name} is not a zip file.") from exc

    with archive:
        members = {}
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            base = Path(info.filename.replace("\\", "/")).name
            if base in _ALLOWED_IN_ZIP and base not in members:
                members[base] = info
                total += info.file_size
        if POSTS_FILE not in members:
            raise DatasetError(
                f"{zip_path.name} has no {POSTS_FILE} inside, so it is not a dataset bundle. "
                "For loose CSV files use: python main.py import <posts.csv> [comments.csv]"
            )
        if total > max_bytes:
            raise DatasetError(
                f"{zip_path.name} unpacks to {human_size(total)}, more than the {human_size(max_bytes)} this tool accepts."
            )

        name = slugify(zip_path.stem)
        if MANIFEST_FILE in members:
            try:
                declared = json.loads(archive.read(members[MANIFEST_FILE]).decode("utf-8")).get("dataset_id")
                if declared:
                    name = re.sub(r"[^A-Za-z0-9_+.-]", "-", str(declared))[:80] or name
            except (ValueError, UnicodeDecodeError):
                pass

        root.mkdir(parents=True, exist_ok=True)
        target = root / name
        suffix = 2
        while target.exists():
            target = root / f"{name}-{suffix}"
            suffix += 1
        target.mkdir()
        for base, info in members.items():
            with archive.open(info) as source, open(target / base, "wb") as sink:
                shutil.copyfileobj(source, sink)

    if not (target / MANIFEST_FILE).exists():
        _rebuild_manifest(target, source="import", notes=f"Imported from {zip_path.name}; the bundle carried no manifest.")
    return target


def import_csvs(posts_csv: Path, comments_csv: Optional[Path] = None, root: Optional[Path] = None,
                label: Optional[str] = None) -> Path:
    """Wrap loose CSV files (for example from an older toolkit run) as a dataset folder."""
    posts_csv = Path(posts_csv).expanduser()
    if not posts_csv.exists():
        raise DatasetError(f"No file at {posts_csv}.")
    if comments_csv is not None:
        comments_csv = Path(comments_csv).expanduser()
        if not comments_csv.exists():
            raise DatasetError(f"No file at {comments_csv}.")

    posts = _read_rows(posts_csv)
    if not posts:
        raise DatasetError(f"{posts_csv.name} has no rows.")
    zoneless = any(_is_zoneless(row.get("created_utc")) for row in posts[:200])
    posts = [_normalize_post(row) for row in posts]
    if not any(row.get("post_id") for row in posts):
        raise DatasetError(
            f"{posts_csv.name} has no post_id (or id) column, so its rows cannot be matched to comments. "
            "Expected columns are listed in docs/DATASET_FORMAT.md."
        )
    comments = [_normalize_comment(row) for row in _read_rows(comments_csv)] if comments_csv else []

    subreddits = sorted({row["subreddit"] for row in posts if row.get("subreddit")})
    guess = label or (subreddits[0] if len(subreddits) == 1 else None) or _label_from_filename(posts_csv)
    if not subreddits and guess:
        for row in posts:
            row["subreddit"] = guess
        for row in comments:
            row.setdefault("subreddit", guess)
            row["subreddit"] = row["subreddit"] or guess
        subreddits = [guess]

    writer = DatasetWriter(
        subreddits, {}, root=root, source="import", label=guess,
        notes=f"Imported from {posts_csv.name}" + (f" and {comments_csv.name}" if comments_csv else "") + "."
              + (" The timestamps carried no time zone and are read as UTC. Toolkit versions before 1.1 "
                 "recorded the collecting computer's local time, so times may be off by that offset."
                 if zoneless else ""),
    )
    for row in posts:
        writer.add_post(row)
    for row in comments:
        writer.add_comment(row)
    return writer.close(STATUS_COMPLETE)


def _read_rows(csv_path: Optional[Path]) -> List[Dict[str, Any]]:
    if csv_path is None:
        return []
    csv.field_size_limit(min(2 ** 31 - 1, 10 ** 9))
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _label_from_filename(path: Path) -> str:
    stem = re.sub(r"_(posts|comments|data)(_\d{8}_\d{6})?$", "", path.stem)
    return stem or "imported"


def _normalize_post(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    if not row.get("post_id"):
        row["post_id"] = str(row.get("id", "")).replace("t3_", "")
    row["post_id"] = str(row.get("post_id", "")).replace("t3_", "")
    if "flair" not in row and "flair_text" in row:
        row["flair"] = row["flair_text"]
    row["created_utc"] = _normalize_time(row.get("created_utc"))
    return row


def _normalize_comment(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    if not row.get("comment_id"):
        row["comment_id"] = str(row.get("id", "")).replace("t1_", "")
    row["comment_id"] = str(row.get("comment_id", "")).replace("t1_", "")
    if not row.get("post_id"):
        row["post_id"] = str(row.get("submission_id", "")).replace("t3_", "")
    row["post_id"] = str(row.get("post_id", "")).replace("t3_", "")
    row["created_utc"] = _normalize_time(row.get("created_utc"))
    return row


def _is_zoneless(value: Any) -> bool:
    """True for a date-time string that names no time zone (and is not an epoch number)."""
    text = str(value or "").strip()
    if not text:
        return False
    try:
        float(text)
        return False
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).tzinfo is None
    except ValueError:
        return False


def _normalize_time(value: Any) -> str:
    """Accept epoch seconds or an ISO-like string; return an ISO string or ''."""
    if value in (None, ""):
        return ""
    text = str(value).strip()
    try:
        return utc_iso(float(text))
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        # Older toolkit versions wrote the collector's local time without a zone.
        # The zone is unknown here, so the value is kept as written.
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rebuild_manifest(dataset_path: Path, source: str, notes: str = "") -> Dict[str, Any]:
    """Create a manifest and codebook for a folder that has data files but no manifest."""
    posts = _read_rows(dataset_path / POSTS_FILE)
    comments_path = dataset_path / COMMENTS_FILE
    comments = _read_rows(comments_path) if comments_path.exists() else []
    authors = {row.get("author") for row in posts + comments} - {None, "", "[deleted]"}
    times = sorted(str(row.get("created_utc")) for row in posts if row.get("created_utc"))
    files: Dict[str, Any] = {}
    for filename, rows in ((POSTS_FILE, posts), (COMMENTS_FILE, comments)):
        file_path = dataset_path / filename
        if file_path.exists():
            files[filename] = {"rows": len(rows), "bytes": file_path.stat().st_size, "sha256": _sha256(file_path)}
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "dataset_id": dataset_path.name,
        "status": STATUS_COMPLETE,
        "created_utc": now_utc_iso(),
        "finished_utc": now_utc_iso(),
        "tool": {"name": "reddit-research-toolkit", "version": __version__},
        "source": source,
        "subreddits": sorted({row.get("subreddit") for row in posts if row.get("subreddit")}),
        "query": {},
        "counts": {"posts": len(posts), "comments": len(comments), "authors": len(authors)},
        "date_range": {"first_post_utc": times[0] if times else None, "last_post_utc": times[-1] if times else None},
        "timezone": "UTC",
        "files": files,
    }
    if notes:
        manifest["notes"] = notes
    (dataset_path / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dataset_path / README_FILE).write_text(render_codebook(manifest), encoding="utf-8")
    return manifest


def verify(dataset_path: Path) -> List[str]:
    """Compare data files with the checksums in the manifest. Returns problems found."""
    dataset_path = Path(dataset_path)
    manifest = load_manifest(dataset_path)
    problems: List[str] = []
    for filename, entry in (manifest.get("files") or {}).items():
        file_path = dataset_path / filename
        if not file_path.exists():
            problems.append(f"{filename} is listed in the manifest but missing from the folder.")
        elif entry.get("sha256") and _sha256(file_path) != entry["sha256"]:
            problems.append(f"{filename} has changed since the dataset was written.")
    return problems
