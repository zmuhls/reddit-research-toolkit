# Dataset folders

Every scrape, import, and sample produces one folder under `data/`. The folder holds the data and everything a reader needs to interpret it, so it can travel as a unit to a classmate, a notebook, or the dashboard.

```
data/
└── cuny_20261127-141502/        one folder per scrape, named <community>_<date>-<time>
    ├── posts.csv                one row per post
    ├── comments.csv             one row per comment (absent for posts-only scrapes)
    ├── manifest.json            the collection record
    ├── README.md                codebook, generated for this dataset
    └── reports/                 created by `python main.py analyze`, never included in a zip
```

`python main.py export` zips the first four files into `<folder name>.zip`. The [dashboard](https://huggingface.co/spaces/milwright/reddit-dashboard) reads and writes the same zip.

## Commands

| Command | Result |
|---|---|
| `python main.py list` | Every dataset, newest first |
| `python main.py show [name]` | Summary, top posts, most used flairs |
| `python main.py analyze [name]` | Charts and reports in `reports/` |
| `python main.py export [name]` | A `.zip` for sharing |
| `python main.py import file.zip` | Unpacks a shared `.zip` into `data/` |
| `python main.py import posts.csv [comments.csv]` | Wraps loose CSV files as a dataset folder |

`name` accepts a full folder name, the part before the date (the newest match wins), or any fragment that matches one dataset. Without a name, a command uses the newest dataset.

Set another location with `--data-dir FOLDER` or the `RRT_DATA_DIR` environment variable.

## posts.csv

| Column | Type | Meaning |
|---|---|---|
| `post_id` | text | Reddit's ID for the post. Joins to `comments.post_id`. |
| `subreddit` | text | Community the post came from, without `r/`. |
| `title` | text | Post title. |
| `author` | text | Username, or `[deleted]`. |
| `created_utc` | date-time | Creation time in UTC, ISO 8601, for example `2026-11-27T14:15:02Z`. |
| `score` | integer | Upvotes minus downvotes at collection time. |
| `upvote_ratio` | number | Share of votes that were upvotes, 0 to 1. |
| `num_comments` | integer | Comment count Reddit reported. It can exceed the rows in `comments.csv`. |
| `flair` | text | Flair label, if any. |
| `is_self` | boolean | True for text posts. |
| `is_video` | boolean | True for Reddit-hosted video. |
| `over_18` | boolean | True for posts marked NSFW. |
| `spoiler` | boolean | True for posts marked as spoilers. |
| `stickied` | boolean | True for posts pinned by moderators. |
| `domain` | text | Site the post links to. |
| `url` | text | Link target. |
| `permalink` | text | Address of the thread on Reddit. |
| `selftext` | text | Body of a text post. |

## comments.csv

| Column | Type | Meaning |
|---|---|---|
| `comment_id` | text | Reddit's ID for the comment. |
| `post_id` | text | ID of the post the comment belongs to. |
| `parent_id` | text | `t3_<post_id>` for a top-level comment, `t1_<comment_id>` for a reply to a comment. |
| `subreddit` | text | Community the comment came from. |
| `author` | text | Username, or `[deleted]`. |
| `created_utc` | date-time | Creation time in UTC, ISO 8601. |
| `score` | integer | Upvotes minus downvotes at collection time. |
| `depth` | integer | Nesting level. 0 marks a top-level comment. |
| `is_submitter` | boolean | True when the commenter wrote the post. |
| `stickied` | boolean | True for comments pinned by moderators. |
| `edited` | boolean | True when the author edited the comment. |
| `permalink` | text | Address of the comment on Reddit. |
| `body` | text | Comment text. |

Both files use UTF-8, a header row, and standard CSV quoting. Text cells can contain commas, quotation marks, and line breaks.

## Time zones

All timestamps are UTC. Convert before you chart by hour or weekday, or a community on the US East Coast will appear to peak at midnight.

```python
import pandas as pd

posts = pd.read_csv("data/cuny_20261127-141502/posts.csv", parse_dates=["created_utc"])
posts["created_local"] = posts["created_utc"].dt.tz_convert("America/New_York")
posts["hour"] = posts["created_local"].dt.hour
```

Toolkit versions before 1.1 wrote the collecting computer's local time into `created_utc` with no zone marker. When you import those files, the manifest records that the times carried no zone.

## manifest.json

```json
{
  "format": "reddit-research-dataset",
  "format_version": 1,
  "dataset_id": "cuny_20261127-141502",
  "status": "complete",
  "created_utc": "2026-11-27T19:15:02Z",
  "finished_utc": "2026-11-27T19:18:40Z",
  "tool": {"name": "reddit-research-toolkit", "version": "1.1.0"},
  "source": "reddit-api",
  "subreddits": ["CUNY"],
  "query": {"sort": "top", "time_filter": "year", "limit": 100, "comments": "all"},
  "counts": {"posts": 100, "comments": 2314, "authors": 842},
  "date_range": {"first_post_utc": "2025-12-02T15:01:22Z", "last_post_utc": "2026-11-20T03:44:10Z"},
  "timezone": "UTC",
  "files": {
    "posts.csv": {"bytes": 81234, "sha256": "…", "rows": 100},
    "comments.csv": {"bytes": 602114, "sha256": "…", "rows": 2314}
  }
}
```

| Field | Values |
|---|---|
| `status` | `complete`, `interrupted` (stopped with Ctrl+C), `failed` (ended on an error), `in_progress` (still writing, or the program was killed) |
| `source` | `reddit-api`, `synthetic` (the practice sample), `import` (wrapped from other files) |
| `query` | The options the scrape ran with. Report these in your methods section. |
| `files` | Size, row count, and SHA-256 checksum for each data file. `python main.py show` warns when a file no longer matches its checksum. |

An interrupted or failed scrape still leaves valid rows. The manifest and the codebook both mark the dataset as partial.

## Archives from the advanced CLI

`tools/cli.py scrape` collects user by user into a SQLite database, and it holds everything for one community in a single folder.

```
data/
└── cuny_archive/
    ├── cuny.db            tables: users, submissions, comments
    ├── checkpoint.pkl     resume point
    ├── scrape.log         full log of the run
    ├── exports/           files from --export
    └── reports/           output of tools/cli.py analyze
```

`python tools/cli.py export --subreddit CUNY` converts an archive into a dataset folder in the format above. A database created by an earlier version under `databases/` continues to work in place.
