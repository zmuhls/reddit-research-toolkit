"""Shared fixtures. Every test runs against temporary folders and a fake Reddit."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """An isolated data folder and .env location, with no credentials set."""
    from rrt import credentials

    data = tmp_path / "data"
    monkeypatch.setenv("RRT_DATA_DIR", str(data))
    monkeypatch.setenv("COLUMNS", "200")
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(credentials, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(credentials, "REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def with_credentials(workspace, monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "fake-client-secret-longer")
    return workspace


@pytest.fixture
def fake(with_credentials, monkeypatch):
    """Install a FakeReddit behind the toolkit and return a factory to configure it."""
    import fake_reddit
    from rrt import credentials

    holder = {}

    def install(**options):
        reddit = fake_reddit.FakeReddit(**options)
        holder["reddit"] = reddit
        monkeypatch.setattr(credentials, "make_reddit", lambda creds=None: reddit)
        return reddit

    install()
    return install
