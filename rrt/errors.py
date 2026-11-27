"""Turn exceptions into explanations a first-time user can act on.

explain() never raises. Anything it does not recognize comes back as a
generic message that points at --debug for the full traceback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

ACCESS_DOC = "docs/REDDIT_API_ACCESS.md"


@dataclass
class Friendly:
    """A failure described in plain language."""

    code: str
    title: str
    why: str
    fixes: List[str] = field(default_factory=list)
    detail: Optional[str] = None


def _status(exc: BaseException) -> Optional[int]:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def explain(exc: BaseException, subreddit: Optional[str] = None) -> Friendly:
    """Map an exception to a Friendly description."""
    try:
        return _explain(exc, subreddit)
    except Exception:  # explaining an error must never raise a second one
        return _generic(exc)


def _generic(exc: BaseException) -> Friendly:
    return Friendly(
        code="unexpected",
        title="Something unexpected went wrong",
        why="The toolkit hit an error it does not have a plain-language explanation for.",
        fixes=[
            "Run the same command again with [cmd]--debug[/cmd] at the end to see the full error.",
            "Run [cmd]python main.py check[/cmd] to rule out a setup problem.",
            "If it persists, open an issue and paste the --debug output: "
            "https://github.com/zmuhls/reddit-research-toolkit/issues",
        ],
        detail=f"{type(exc).__name__}: {exc}",
    )


def _explain(exc: BaseException, subreddit: Optional[str]) -> Friendly:
    name = type(exc).__name__
    detail = f"{name}: {exc}"
    # The name is echoed inside rich markup below, so strip anything that is not
    # a legal subreddit character before it gets there.
    subreddit = re.sub(r"[^A-Za-z0-9_]", "", subreddit or "") or None
    sub = f"r/{subreddit}" if subreddit else "that subreddit"
    status = _status(exc)

    try:
        import prawcore.exceptions as pc
    except ImportError:  # praw missing entirely is handled by the import check
        pc = None

    if isinstance(exc, ModuleNotFoundError):
        missing = getattr(exc, "name", None) or "a required package"
        return Friendly(
            code="missing-package",
            title=f"The Python package '{missing}' is not installed",
            why="The toolkit's packages are installed per environment. This terminal is using an "
                "environment that does not have them, which usually means the virtual environment "
                "is not active or the install step was skipped.",
            fixes=[
                "Activate the environment. macOS or Linux: [cmd]source .venv/bin/activate[/cmd]   "
                "Windows: [cmd].venv\\Scripts\\activate[/cmd]",
                "Install the packages: [cmd]python -m pip install -r requirements.txt[/cmd]",
                "For the analyze command also run: [cmd]python -m pip install -r requirements-analysis.txt[/cmd]",
            ],
            detail=detail,
        )

    if isinstance(exc, PermissionError):
        return Friendly(
            code="permission",
            title="The toolkit could not write to a file or folder",
            why=f"The operating system refused access to {getattr(exc, 'filename', None) or 'a path'}. "
                "A spreadsheet app holding the file open is the usual cause on Windows.",
            fixes=[
                "Close any app that has the file open, then run the command again.",
                "Or write somewhere else with [cmd]--data-dir <folder>[/cmd].",
            ],
            detail=detail,
        )

    if pc is not None:
        if isinstance(exc, pc.OAuthException) or status == 401:
            return Friendly(
                code="bad-credentials",
                title="Reddit did not accept these credentials",
                why="Reddit turned down the client ID and secret (HTTP 401). The two values do not "
                    "match an app Reddit currently allows.",
                fixes=[
                    "Re-enter them with [cmd]python main.py setup[/cmd]. A missing character or a "
                    "swapped ID and secret is the most common cause.",
                    "Check the app at https://www.reddit.com/prefs/apps is type 'script' and still listed.",
                    "If these credentials worked before, Reddit may have closed the app's access. "
                    f"Read [path]{ACCESS_DOC}[/path] for the current rules and deadlines.",
                    "No credentials? You can still work with shared or sample data: "
                    "[cmd]python main.py sample[/cmd]",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.TooManyRequests) or status == 429:
            wait = getattr(exc, "retry_after", None)
            wait_text = f" Reddit asked for a pause of about {float(wait):.0f} seconds." if wait else ""
            return Friendly(
                code="rate-limited",
                title="Reddit asked the toolkit to slow down",
                why="Too many requests reached Reddit in a short time (HTTP 429)." + wait_text,
                fixes=[
                    "Wait a few minutes, then run the command again.",
                    "Make sure no second copy of the toolkit is running with the same credentials.",
                    "Ask for less at once: a smaller [cmd]--limit[/cmd], or [cmd]--comments quick[/cmd].",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.Redirect):
            return Friendly(
                code="no-such-subreddit",
                title=f"Reddit has no community called {sub}",
                why="Reddit redirected the request to its search page, which is what it does when "
                    "a subreddit name does not exist.",
                fixes=[
                    "Check the spelling. Type the name as it appears after r/ in the address bar.",
                    "Leave out the r/ prefix and any spaces, for example [cmd]python main.py scrape CUNY[/cmd].",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.NotFound) or status == 404:
            return Friendly(
                code="not-found",
                title=f"Reddit could not find {sub}",
                why="Reddit responded with 'not found' (HTTP 404). The community may be banned, "
                    "deleted, or misspelled.",
                fixes=[
                    f"Open https://www.reddit.com/r/{subreddit or '<name>'} in a browser to see its status.",
                    "Check the spelling and try again.",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.Forbidden) or status == 403:
            return Friendly(
                code="forbidden",
                title=f"Reddit refused access to {sub}",
                why="Reddit responded with 'forbidden' (HTTP 403). Either the community is private "
                    "or quarantined, or Reddit no longer allows this app to read data.",
                fixes=[
                    f"Open https://www.reddit.com/r/{subreddit or '<name>'} in a browser. A private or "
                    "quarantined notice there explains the refusal.",
                    "Test the credentials against a public community: [cmd]python main.py check[/cmd]",
                    f"If every community is refused, the app has lost API access. See [path]{ACCESS_DOC}[/path].",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.UnavailableForLegalReasons) or status == 451:
            return Friendly(
                code="legal-block",
                title=f"{sub} is unavailable in your region",
                why="Reddit blocks this community where you are for legal reasons (HTTP 451).",
                fixes=["Choose a different community."],
                detail=detail,
            )

        if isinstance(exc, pc.ServerError) or (status is not None and status >= 500):
            return Friendly(
                code="reddit-down",
                title="Reddit is having trouble right now",
                why=f"Reddit's servers returned an error (HTTP {status or '5xx'}). Nothing is wrong on your side.",
                fixes=[
                    "Wait a few minutes and run the command again.",
                    "Check https://www.redditstatus.com for an outage notice.",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.RequestException):
            return Friendly(
                code="network",
                title="The toolkit could not reach Reddit",
                why="The request never got to Reddit. The connection dropped, timed out, or was "
                    "blocked on the way.",
                fixes=[
                    "Check that this computer is online by opening https://www.reddit.com in a browser.",
                    "Campus and office networks sometimes block Reddit. Try another network or a hotspot.",
                    "Turn off any VPN or proxy and try again.",
                ],
                detail=detail,
            )

        if isinstance(exc, pc.PrawcoreException):
            return Friendly(
                code="reddit-api",
                title="Reddit returned an unexpected response",
                why=f"The request reached Reddit but came back in a form the toolkit could not use"
                    f"{f' (HTTP {status})' if status else ''}.",
                fixes=[
                    "Run the command again. Occasional hiccups clear on their own.",
                    "Run [cmd]python main.py check[/cmd] to test the credentials.",
                    "Add [cmd]--debug[/cmd] to see the full error.",
                ],
                detail=detail,
            )

    if isinstance(exc, (ConnectionError, TimeoutError)):
        return Friendly(
            code="network",
            title="The toolkit could not reach Reddit",
            why="The network connection failed or timed out.",
            fixes=[
                "Check that this computer is online.",
                "Try another network if this one blocks Reddit.",
            ],
            detail=detail,
        )

    return _generic(exc)
