"""Reddit credentials: find them, sanity-check them, save them, test them.

Credentials live in a .env file beside main.py. Environment variables with the
same names take precedence, which is how shared machines and CI set them.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import REPO_ROOT, __version__

ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

KEY_ID = "REDDIT_CLIENT_ID"
KEY_SECRET = "REDDIT_CLIENT_SECRET"
KEY_AGENT = "REDDIT_USER_AGENT"

# Values people leave in place after copying an example file.
_PLACEHOLDER = re.compile(r"your[_ -]?(client[_ -]?)?(id|secret)|^x+$|changeme|placeholder|<.*>", re.IGNORECASE)


@dataclass
class Credentials:
    client_id: str = ""
    client_secret: str = ""
    user_agent: str = ""
    source: str = "none"  # ".env", "environment", or "none"

    @property
    def present(self) -> bool:
        return bool(self.client_id and self.client_secret)


def default_user_agent(username: str = "") -> str:
    """Reddit asks for <platform>:<app id>:<version> (by /u/<username>)."""
    name = re.sub(r"^/?u/", "", username.strip())
    who = f" (by /u/{name})" if name else ""
    return f"python:reddit-research-toolkit:v{__version__}{who}"


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value.strip()
    return values


def load() -> Credentials:
    """Read credentials from the environment first, then from .env."""
    file_values = _parse_env_file(ENV_PATH)

    def pick(key: str) -> Tuple[str, str]:
        if os.environ.get(key, "").strip():
            return os.environ[key].strip(), "environment"
        if file_values.get(key, "").strip():
            return file_values[key].strip(), ".env"
        return "", "none"

    client_id, id_source = pick(KEY_ID)
    client_secret, _ = pick(KEY_SECRET)
    user_agent, _ = pick(KEY_AGENT)
    return Credentials(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent or default_user_agent(),
        source=id_source,
    )


def problems(creds: Optional[Credentials] = None) -> List[str]:
    """Things that are wrong before any network call. Empty list means plausible."""
    creds = creds or load()
    found: List[str] = []

    stray = [name for name in (".env.txt", "env", ".env.example.txt", "env.txt") if (REPO_ROOT / name).is_file()]
    if not ENV_PATH.is_file() and creds.source != "environment":
        if stray:
            found.append(
                f"There is no .env file, but there is a file named '{stray[0]}'. Some editors add .txt or drop "
                "the leading dot when saving. Rename it to exactly .env"
            )
        else:
            found.append("There is no .env file yet.")
        return found

    if not creds.client_id:
        found.append(f"{KEY_ID} is empty.")
    elif _PLACEHOLDER.search(creds.client_id):
        found.append(f"{KEY_ID} still holds the placeholder text from the example file.")
    elif re.search(r"\s", creds.client_id):
        found.append(f"{KEY_ID} contains a space. Copy it again without surrounding whitespace.")

    if not creds.client_secret:
        found.append(f"{KEY_SECRET} is empty.")
    elif _PLACEHOLDER.search(creds.client_secret):
        found.append(f"{KEY_SECRET} still holds the placeholder text from the example file.")
    elif re.search(r"\s", creds.client_secret):
        found.append(f"{KEY_SECRET} contains a space. Copy it again without surrounding whitespace.")

    if creds.client_id and creds.client_secret and not found:
        if len(creds.client_id) > len(creds.client_secret):
            found.append(
                "The client ID is longer than the secret. Reddit's IDs are the shorter of the two, "
                "so the values may be swapped."
            )
    return found


def save(client_id: str, client_secret: str, user_agent: str) -> Path:
    """Write the three values into .env, preserving any other lines in the file."""
    wanted = {KEY_ID: client_id.strip(), KEY_SECRET: client_secret.strip(), KEY_AGENT: user_agent.strip()}
    lines: List[str] = []
    seen = set()
    if ENV_PATH.is_file():
        for raw in ENV_PATH.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            stripped = raw.strip()
            key = stripped.split("=", 1)[0].replace("export ", "").strip() if "=" in stripped and not stripped.startswith("#") else None
            if key in wanted:
                if key not in seen:
                    lines.append(f"{key}={wanted[key]}")
                    seen.add(key)
            else:
                lines.append(raw)
    else:
        lines += [
            "# Reddit API credentials for the Reddit Research Toolkit.",
            "# This file is private. Git ignores it. Never paste its contents anywhere public.",
            "",
        ]
    for key, value in wanted.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    try:
        ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # owner read/write only; a no-op on Windows
    except OSError:
        pass
    return ENV_PATH


def make_reddit(creds: Optional[Credentials] = None):
    """Build a read-only PRAW client. Raises ModuleNotFoundError when praw is absent."""
    import praw

    creds = creds or load()
    return praw.Reddit(
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        user_agent=creds.user_agent or default_user_agent(),
        check_for_async=False,
        check_for_updates=False,
    )


@dataclass
class ConnectionCheck:
    ok: bool
    stage: str  # "config", "login", "read", or "done"
    error: Optional[BaseException] = None
    sample_title: str = ""


def check_connection(creds: Optional[Credentials] = None, subreddit: str = "announcements", reddit=None) -> ConnectionCheck:
    """Two real requests: get a token, then read one public post.

    The second step matters. Reddit can accept a client ID and secret and still
    refuse to serve data to an app it has not approved.
    """
    creds = creds or load()
    if reddit is None:
        if not creds.present:
            return ConnectionCheck(ok=False, stage="config")
        reddit = make_reddit(creds)
    try:
        reddit.auth.scopes()
    except Exception as exc:  # classified by rrt.errors.explain
        return ConnectionCheck(ok=False, stage="login", error=exc)
    try:
        post = next(iter(reddit.subreddit(subreddit).new(limit=1)), None)
        title = getattr(post, "title", "") if post is not None else ""
    except Exception as exc:
        return ConnectionCheck(ok=False, stage="read", error=exc)
    return ConnectionCheck(ok=True, stage="done", sample_title=title)


def env_is_git_ignored() -> Optional[bool]:
    """True/False when it can be determined that git ignores .env; None otherwise."""
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.is_file():
        return None
    patterns = {line.strip() for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines()}
    return ".env" in patterns or "/.env" in patterns or "*.env" in patterns
