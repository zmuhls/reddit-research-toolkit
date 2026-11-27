"""A stand-in for praw.Reddit that serves the synthetic sample.

The tests cannot reach Reddit and should not need credentials, so they drive
the toolkit against this object. It mimics the parts of PRAW the toolkit uses:
subreddit lookup, the four listings, comment forests with replace_more, and
the failures Reddit produces (bad credentials, missing or private community,
rate limiting, a dropped connection).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import prawcore.exceptions as pc

from rrt import sample


class FakeResponse:
    def __init__(self, status_code: int, headers: Optional[Dict[str, str]] = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


def unauthorized() -> Exception:
    return pc.ResponseException(FakeResponse(401))


def forbidden() -> Exception:
    return pc.Forbidden(FakeResponse(403))


def not_found() -> Exception:
    return pc.NotFound(FakeResponse(404))


def redirect() -> Exception:
    return pc.Redirect(FakeResponse(302, {"location": "https://www.reddit.com/subreddits/search.json?q=nope"}))


def rate_limited() -> Exception:
    return pc.TooManyRequests(FakeResponse(429, {"retry-after": "42"}, "Too Many Requests"))


def server_error() -> Exception:
    return pc.ServerError(FakeResponse(503))


def offline() -> Exception:
    return pc.RequestException(ConnectionError("Name or service not known"), (), {})


class FakeAuthor(str):
    """A username that also works as redditor.name, the way PRAW authors do."""

    @property
    def name(self) -> str:
        return str(self)


class FakeSubredditName(str):
    """A subreddit name that also offers .display_name."""

    @property
    def display_name(self) -> str:
        return str(self)


def _epoch(iso: str) -> float:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


class FakeComment:
    def __init__(self, row: Dict[str, Any]):
        self.id = row["comment_id"]
        self.parent_id = row["parent_id"]
        self.author = FakeAuthor(row["author"])
        self.subreddit = FakeSubredditName(row["subreddit"])
        self.submission = type("FakeSubmissionRef", (), {"id": row["post_id"]})()
        self.body = row["body"]
        self.score = row["score"]
        self.created_utc = _epoch(row["created_utc"])
        self.edited = row["edited"]
        self.is_submitter = row["is_submitter"]
        self.stickied = False
        self.permalink = f"/r/{row['subreddit']}/comments/{row['post_id']}/_/{row['comment_id']}/"
        self.replies: List["FakeComment"] = []


class FakeForest(list):
    """The comments of one post. Records how replace_more was called."""

    def __init__(self, comments, fail: Optional[Exception] = None):
        super().__init__(comments)
        self.replace_more_limits: List[Any] = []
        self._fail = fail

    def replace_more(self, *, limit=32, threshold=0):
        self.replace_more_limits.append(limit)
        if self._fail is not None:
            raise self._fail
        return []


class FakeSubmission:
    def __init__(self, row: Dict[str, Any], comment_rows: List[Dict[str, Any]], comment_failure: Optional[Exception] = None):
        self.id = row["post_id"]
        self.title = row["title"]
        self.author = None if row["author"] == "[deleted]" else FakeAuthor(row["author"])
        self.locked = False
        self.created_utc = _epoch(row["created_utc"])
        self.score = row["score"]
        self.upvote_ratio = row["upvote_ratio"]
        self.num_comments = row["num_comments"]
        self.permalink = f"/r/{row['subreddit']}/comments/{row['post_id']}/"
        self.url = row["url"]
        self.selftext = row["selftext"]
        self.is_self = row["is_self"]
        self.is_video = False
        self.over_18 = False
        self.spoiler = False
        self.stickied = False
        self.link_flair_text = row["flair"]
        self.domain = row["domain"]
        self.subreddit = FakeSubredditName(row["subreddit"])

        by_id = {c["comment_id"]: FakeComment(c) for c in comment_rows}
        top: List[FakeComment] = []
        for c in comment_rows:
            node = by_id[c["comment_id"]]
            parent = c["parent_id"]
            if parent.startswith("t1_") and parent[3:] in by_id:
                by_id[parent[3:]].replies.append(node)
            else:
                top.append(node)
        self.comments = FakeForest(top, comment_failure)
        self.all_comments = list(by_id.values())


class FakeSubreddit:
    def __init__(self, reddit: "FakeReddit", name: str):
        self._reddit = reddit
        self._name = name

    def _about(self, key: str):
        self._reddit.requests += 1
        lowered = self._name.lower()
        if lowered in self._reddit.missing:
            raise redirect()
        if lowered in self._reddit.banned:
            raise not_found()
        if lowered in self._reddit.private:
            raise forbidden()
        if self._reddit.read_error is not None:
            raise self._reddit.read_error
        return {
            "display_name": sample.SUBREDDIT if lowered == sample.SUBREDDIT.lower() else self._name,
            "title": "A sample campus community",
            "public_description": "Synthetic community used by the toolkit's tests.",
            "subscribers": 12345,
            "created_utc": 1400000000.0,
            "over18": False,
            "subreddit_type": "public",
        }[key]

    display_name = property(lambda self: self._about("display_name"))
    title = property(lambda self: self._about("title"))
    public_description = property(lambda self: self._about("public_description"))
    subscribers = property(lambda self: self._about("subscribers"))
    created_utc = property(lambda self: self._about("created_utc"))
    over18 = property(lambda self: self._about("over18"))
    subreddit_type = property(lambda self: self._about("subreddit_type"))

    def _listing(self, limit=None, **_kwargs):
        reddit = self._reddit
        lowered = self._name.lower()
        if lowered in reddit.missing:
            raise redirect()
        if lowered in reddit.private:
            raise forbidden()
        if reddit.read_error is not None:
            raise reddit.read_error
        if lowered in reddit.empty:
            return
        for index, submission in enumerate(reddit.submissions[: limit if limit is not None else None]):
            if reddit.fail_after is not None and index >= reddit.fail_after:
                raise reddit.fail_with
            if reddit.interrupt_after is not None and index >= reddit.interrupt_after:
                raise KeyboardInterrupt
            reddit.requests += 1
            yield submission

    def hot(self, **kwargs):
        self._reddit.calls.append(("hot", kwargs))
        return self._listing(**kwargs)

    def new(self, **kwargs):
        self._reddit.calls.append(("new", kwargs))
        return self._listing(**kwargs)

    def rising(self, **kwargs):
        self._reddit.calls.append(("rising", kwargs))
        return self._listing(**kwargs)

    def top(self, *, time_filter="all", **kwargs):
        self._reddit.calls.append(("top", {"time_filter": time_filter, **kwargs}))
        return self._listing(**kwargs)


class _FakeUserListing:
    def __init__(self, items):
        self._items = items

    def new(self, limit=None):
        return iter(self._items[: limit if limit is not None else None])


class FakeRedditor:
    """One account: its posts and comments across the fake site."""

    def __init__(self, reddit: "FakeReddit", name: str):
        if name in reddit.broken_users:
            raise not_found()
        self.name = name
        self.created_utc = 1500000000.0
        self.total_karma = 1234
        self.submissions = _FakeUserListing([s for s in reddit.submissions if s.author == name])
        self.comments = _FakeUserListing(
            [c for s in reddit.submissions for c in s.all_comments if c.author == name]
        )


class FakeAuth:
    def __init__(self, reddit: "FakeReddit"):
        self._reddit = reddit
        self.limits = {"remaining": 99, "used": 1}

    def scopes(self):
        if self._reddit.login_error is not None:
            raise self._reddit.login_error
        return {"*"}


class FakeReddit:
    """Configure failures through the keyword arguments."""

    def __init__(
        self,
        n_posts: int = 60,
        *,
        missing=(),
        banned=(),
        private=(),
        empty=(),
        login_error: Optional[Exception] = None,
        read_error: Optional[Exception] = None,
        fail_after: Optional[int] = None,
        fail_with: Optional[Exception] = None,
        interrupt_after: Optional[int] = None,
        comment_failures: Optional[Dict[int, Exception]] = None,
        broken_users=(),
    ):
        posts, comments = sample.generate(n_posts=n_posts)
        by_post: Dict[str, List[Dict[str, Any]]] = {}
        for comment in comments:
            by_post.setdefault(comment["post_id"], []).append(comment)
        comment_failures = comment_failures or {}
        self.submissions = [
            FakeSubmission(post, by_post.get(post["post_id"], []), comment_failures.get(index))
            for index, post in enumerate(posts)
        ]
        self.expected_posts = posts
        self.expected_comments = comments
        self.missing = {name.lower() for name in missing}
        self.banned = {name.lower() for name in banned}
        self.private = {name.lower() for name in private}
        self.empty = {name.lower() for name in empty}
        self.broken_users = set(broken_users)
        self.login_error = login_error
        self.read_error = read_error
        self.fail_after = fail_after
        self.fail_with = fail_with or rate_limited()
        self.interrupt_after = interrupt_after
        self.read_only = True
        self.auth = FakeAuth(self)
        self.calls: List[Any] = []
        self.requests = 0

    def subreddit(self, name: str) -> FakeSubreddit:
        return FakeSubreddit(self, name)

    def redditor(self, name: str) -> FakeRedditor:
        return FakeRedditor(self, name)
