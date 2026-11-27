#!/usr/bin/env python3
"""
Simple Reddit Scraper

Collects posts, and optionally their comments, from one subreddit.

Run it through main.py for the guided terminal experience:

    python main.py scrape CUNY

Or use the class directly from a notebook or script:

    from simple_scraper import SimpleRedditScraper

    scraper = SimpleRedditScraper(client_id, client_secret, user_agent)
    data = scraper.scrape_subreddit("CUNY", post_limit=100)
    folder = scraper.save_to_csv(data, "CUNY")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from rrt.datasets import STATUS_COMPLETE, DatasetWriter, export_json, utc_iso

logger = logging.getLogger("rrt.scraper")

COMMENT_MODES = ("all", "quick", "none")
SORTS = ("hot", "new", "top", "rising")
TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")

# Stop collecting comments after this many threads fail in a row. One failure is a
# removed thread; ten in a row is a lost connection or a revoked app.
_MAX_CONSECUTIVE_THREAD_FAILURES = 10


def post_row(post, subreddit_name: str) -> Dict[str, Any]:
    """One post as a flat dictionary in dataset column names. Times are UTC."""
    return {
        "post_id": post.id,
        "subreddit": subreddit_name,
        "title": post.title,
        "author": str(post.author) if post.author else "[deleted]",
        "created_utc": utc_iso(post.created_utc),
        "score": post.score,
        "upvote_ratio": getattr(post, "upvote_ratio", None),
        "num_comments": post.num_comments,
        "flair": getattr(post, "link_flair_text", None),
        "is_self": post.is_self,
        "is_video": getattr(post, "is_video", False),
        "over_18": getattr(post, "over_18", False),
        "spoiler": getattr(post, "spoiler", False),
        "stickied": getattr(post, "stickied", False),
        "domain": getattr(post, "domain", None),
        "url": getattr(post, "url", None),
        "permalink": f"https://www.reddit.com{post.permalink}",
        "selftext": getattr(post, "selftext", ""),
    }


def comment_row(comment, post_id: str, subreddit_name: str, depth: int) -> Dict[str, Any]:
    """One comment as a flat dictionary in dataset column names. Times are UTC."""
    return {
        "comment_id": comment.id,
        "post_id": post_id,
        "parent_id": comment.parent_id,
        "subreddit": subreddit_name,
        "author": str(comment.author) if comment.author else "[deleted]",
        "created_utc": utc_iso(comment.created_utc),
        "score": comment.score,
        "depth": depth,
        "is_submitter": getattr(comment, "is_submitter", False),
        "stickied": getattr(comment, "stickied", False),
        "edited": bool(getattr(comment, "edited", False)),
        "permalink": f"https://www.reddit.com{comment.permalink}",
        "body": comment.body,
    }


class SimpleRedditScraper:
    """Collects posts and comments from a subreddit through Reddit's API."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        *,
        reddit=None,
        data_dir: Optional[Path] = None,
    ):
        """
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string Reddit sees on every request
            reddit: An existing praw.Reddit instance to use in place of the
                three values above (handy for tests)
            data_dir: Where dataset folders are written (default: data/)
        """
        if reddit is None:
            import praw

            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent or "python:reddit-research-toolkit (simple scraper)",
                check_for_async=False,
                check_for_updates=False,
            )
        self.reddit = reddit
        self.data_dir = Path(data_dir) if data_dir else None
        self.skipped_threads = 0

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def iter_posts(self, subreddit_name: str, post_limit: Optional[int] = 1000,
                   sort_by: str = "hot", time_filter: str = "all") -> Iterator[Any]:
        """Yield PRAW submissions in the requested order."""
        subreddit = self.reddit.subreddit(subreddit_name)
        if sort_by == "new":
            return iter(subreddit.new(limit=post_limit))
        if sort_by == "top":
            return iter(subreddit.top(time_filter=time_filter, limit=post_limit))
        if sort_by == "rising":
            return iter(subreddit.rising(limit=post_limit))
        return iter(subreddit.hot(limit=post_limit))

    def scrape_subreddit(
        self,
        subreddit_name: str,
        post_limit: int = 1000,
        sort_by: str = "hot",
        time_filter: str = "all",
        include_comments: bool = True,
        *,
        comments: Optional[str] = None,
        writer: Optional[DatasetWriter] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Collect posts and, unless told otherwise, their comments.

        Args:
            subreddit_name: Name of the subreddit (without r/)
            post_limit: Maximum number of posts (Reddit serves about 1,000 per sort)
            sort_by: 'hot', 'new', 'top', or 'rising'
            time_filter: For 'top' only: 'hour', 'day', 'week', 'month', 'year', 'all'
            include_comments: False is the same as comments='none'
            comments: 'all' follows every "load more comments" link (complete, slow);
                'quick' takes the comments Reddit sends with the thread (one
                request per post); 'none' skips comments
            writer: A DatasetWriter. Rows are written to it as they arrive, so an
                interrupted run still leaves usable files
            on_progress: Called after each post as on_progress(posts_so_far,
                comments_so_far, post_title)

        Returns:
            Dictionary with 'posts' and 'comments' lists
        """
        mode = comments or ("all" if include_comments else "none")
        if mode not in COMMENT_MODES:
            raise ValueError(f"comments must be one of {COMMENT_MODES}, not {mode!r}")

        posts_data: List[Dict[str, Any]] = []
        comments_data: List[Dict[str, Any]] = []
        self.skipped_threads = 0
        consecutive_failures = 0

        for post in self.iter_posts(subreddit_name, post_limit, sort_by, time_filter):
            row = post_row(post, subreddit_name)
            posts_data.append(row)
            if writer:
                writer.add_post(row)

            if mode != "none" and post.num_comments > 0:
                try:
                    thread = self._scrape_post_comments(post, subreddit_name, expand_all=(mode == "all"))
                    consecutive_failures = 0
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    if not _thread_error_is_skippable(exc):
                        raise
                    self.skipped_threads += 1
                    consecutive_failures += 1
                    logger.debug("Skipped comments for post %s: %s", post.id, exc)
                    if consecutive_failures >= _MAX_CONSECUTIVE_THREAD_FAILURES:
                        raise
                    thread = []
                comments_data.extend(thread)
                if writer:
                    for comment in thread:
                        writer.add_comment(comment)

            if writer and len(posts_data) % 25 == 0:
                writer.flush()
            if on_progress:
                on_progress(len(posts_data), len(comments_data), row["title"])

        return {"posts": posts_data, "comments": comments_data}

    def _scrape_post_comments(self, submission, subreddit_name: Optional[str] = None,
                              expand_all: bool = True) -> List[Dict[str, Any]]:
        """All comments of one post, flattened, each with its depth in the thread."""
        subreddit_name = subreddit_name or str(getattr(submission, "subreddit", ""))
        # limit=None follows every "load more comments" stub. limit=0 drops the
        # stubs and takes what arrived with the first response.
        submission.comments.replace_more(limit=None if expand_all else 0)

        rows: List[Dict[str, Any]] = []
        stack = [(comment, 0) for comment in reversed(list(submission.comments))]
        while stack:
            comment, depth = stack.pop()
            if not hasattr(comment, "body"):
                continue
            rows.append(comment_row(comment, submission.id, subreddit_name, depth))
            replies = getattr(comment, "replies", None)
            if replies:
                stack.extend((reply, depth + 1) for reply in reversed(list(replies)))
        return rows

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save_dataset(self, data: Dict[str, List[Dict]], subreddit_name: str,
                     query: Optional[Dict[str, Any]] = None, write_json: bool = False) -> Path:
        """Write collected rows as a dataset folder and return its path."""
        writer = DatasetWriter([subreddit_name], query or {}, root=self.data_dir)
        for post in data.get("posts", []):
            writer.add_post(post)
        for comment in data.get("comments", []):
            writer.add_comment(comment)
        return writer.close(STATUS_COMPLETE, write_json=write_json)

    def save_to_csv(self, data: Dict[str, List[Dict]], subreddit_name: str) -> Path:
        """Write posts.csv and comments.csv into a new dataset folder.

        Returns the folder. Earlier versions wrote loose, timestamped files into
        output/; each scrape now gets its own folder under data/.
        """
        return self.save_dataset(data, subreddit_name)

    def save_to_json(self, data: Dict[str, List[Dict]], subreddit_name: str,
                     dataset_path: Optional[Path] = None) -> Path:
        """Write data.json. Pass dataset_path to add it to an existing dataset folder."""
        if dataset_path is not None:
            return export_json(Path(dataset_path))
        folder = self.save_dataset(data, subreddit_name, write_json=True)
        return folder / "data.json"

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_subreddit_info(self, subreddit_name: str, raise_errors: bool = False) -> Dict[str, Any]:
        """Basic facts about a subreddit. Returns {} on failure unless raise_errors is set."""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            return {
                "name": subreddit.display_name,
                "title": subreddit.title,
                "description": subreddit.public_description,
                "subscribers": subreddit.subscribers,
                "created_utc": utc_iso(subreddit.created_utc),
                "over18": subreddit.over18,
                "subreddit_type": subreddit.subreddit_type,
            }
        except Exception as exc:
            if raise_errors:
                raise
            logger.error("Error getting subreddit info: %s", exc)
            return {}


def _thread_error_is_skippable(exc: BaseException) -> bool:
    """True for failures that concern one thread, not the whole session."""
    try:
        import prawcore.exceptions as pc
    except ImportError:
        return False
    if isinstance(exc, (pc.TooManyRequests, pc.OAuthException, pc.RequestException)):
        return False
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        return False
    return isinstance(exc, (pc.NotFound, pc.Forbidden, pc.ServerError, pc.BadJSON, pc.Redirect)) or isinstance(
        exc, (AttributeError, KeyError)
    )
