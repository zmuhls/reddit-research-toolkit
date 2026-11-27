"""Small shared helpers: subreddit names and time estimates."""

from __future__ import annotations

import re
from typing import Tuple


class BadSubredditName(ValueError):
    """What the user typed cannot be a subreddit name. The message is user-facing."""


def clean_subreddit_name(text: str) -> str:
    """Accept what people paste and return the bare name.

    'r/CUNY', '/r/CUNY/', 'https://www.reddit.com/r/CUNY/hot' and ' CUNY '
    all become 'CUNY'. Combined names such as 'CUNY+Baruch' are allowed.
    """
    name = (text or "").strip()
    match = re.search(r"reddit\.com/r/([^/?#\s]+)", name, flags=re.IGNORECASE)
    if match:
        name = match.group(1)
    name = re.sub(r"^/?r/", "", name, flags=re.IGNORECASE).strip("/ ")
    if not name:
        raise BadSubredditName("No subreddit name was entered. Example: CUNY")
    if " " in name:
        raise BadSubredditName(
            f"'{name}' has a space in it. Subreddit names are one word, for example AskHistorians."
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*", name):
        raise BadSubredditName(
            f"'{name}' has characters a subreddit name cannot contain. Use letters, numbers, and underscores only."
        )
    return name


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} sec"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min" if secs < 10 or minutes >= 10 else f"{minutes} min {secs} sec"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr {minutes} min"


def estimate_seconds(limit: int, comments: str) -> Tuple[int, int]:
    """Rough (low, high) run time for a scrape.

    Reddit serves about one request per second to a script. Listing posts costs
    one request per 100 posts. Reading a thread costs one request, and each
    'load more comments' stub on a long thread costs another.
    """
    listing = max(1, limit // 100) * 2
    if comments == "none":
        return listing, listing * 3 + 5
    if comments == "quick":
        return listing + int(limit * 0.7), listing + int(limit * 1.6)
    return listing + int(limit * 1.0), listing + int(limit * 6)


def describe_estimate(limit: int, comments: str) -> str:
    low, high = estimate_seconds(limit, comments)
    if high < 60:
        return "under a minute"
    if low == high or format_duration(low) == format_duration(high):
        return f"about {format_duration(high)}"
    return f"{format_duration(low)} to {format_duration(high)}"
