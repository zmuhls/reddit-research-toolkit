#!/usr/bin/env python3
"""Run main.py against the fake Reddit, for trying the terminal experience offline.

    python tests/run_with_fake_reddit.py scrape SampleCampus --limit 40
    FAKE_REDDIT=missing   python tests/run_with_fake_reddit.py scrape nosuchsub
    FAKE_REDDIT=badlogin  python tests/run_with_fake_reddit.py check
    FAKE_REDDIT=ratelimit python tests/run_with_fake_reddit.py scrape SampleCampus
    FAKE_ENV_DIR=/tmp/try python tests/run_with_fake_reddit.py setup

Development aid only. Nothing here talks to Reddit, and the rows it produces
are synthetic.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_reddit  # noqa: E402
import main  # noqa: E402
from rrt import credentials  # noqa: E402

SCENARIOS = {
    "ok": dict(),
    "missing": dict(missing=["nosuchsub"]),
    "private": dict(private=["secretclub"]),
    "empty": dict(empty=["quietplace"]),
    "badlogin": dict(login_error=fake_reddit.unauthorized()),
    "noaccess": dict(read_error=fake_reddit.forbidden()),
    "offline": dict(login_error=fake_reddit.offline(), read_error=fake_reddit.offline()),
    "ratelimit": dict(fail_after=25, fail_with=fake_reddit.rate_limited()),
    "interrupt": dict(interrupt_after=25),
}

if __name__ == "__main__":
    scenario = os.environ.get("FAKE_REDDIT", "ok")
    reddit = fake_reddit.FakeReddit(n_posts=int(os.environ.get("FAKE_POSTS", "120")), **SCENARIOS[scenario])
    credentials.make_reddit = lambda creds=None: reddit
    if os.environ.get("FAKE_ENV_DIR"):
        # Try 'setup' without touching the real .env: credentials are read from
        # and written to this folder instead.
        credentials.REPO_ROOT = Path(os.environ["FAKE_ENV_DIR"])
        credentials.ENV_PATH = credentials.REPO_ROOT / ".env"
    else:
        os.environ.setdefault("REDDIT_CLIENT_ID", "fake-client-id")
        os.environ.setdefault("REDDIT_CLIENT_SECRET", "fake-client-secret-longer")
    sys.exit(main.main())
