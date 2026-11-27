"""Analysis bridge, analyzers, and the user-centric advanced CLI."""

import signal
import sqlite3
import sys

import pytest

import fake_reddit
import main
from rrt import bridge, datasets, sample

plotly = pytest.importorskip("plotly", reason="analysis packages are optional")


@pytest.fixture
def sample_dataset(workspace):
    return sample.write_sample(workspace / "data", n_posts=80)


def test_bridge_builds_the_schema_the_analyzers_read(sample_dataset):
    posts, comments, _ = datasets.read_dataset(sample_dataset)
    db_path = bridge.build_database(sample_dataset)
    assert db_path.parent == sample_dataset / "reports"
    assert db_path.stem == "SampleCampus"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == len(posts)
        assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == len(comments)
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert users == len(set(posts["author"]) | set(comments["author"]))
        epoch, = conn.execute("SELECT created_utc FROM submissions ORDER BY created_utc LIMIT 1").fetchone()
        assert epoch == int(posts["created_utc"].min().timestamp())
        linked = conn.execute(
            "SELECT COUNT(*) FROM comments c JOIN submissions s ON c.submission_id = 't3_' || s.id").fetchone()[0]
        assert linked == len(comments)


def test_archive_database_exports_back_to_an_equal_dataset(sample_dataset, workspace):
    db_path = bridge.build_database(sample_dataset)
    exported = bridge.database_to_dataset(db_path, "SampleCampus", workspace / "data")
    original_posts, original_comments, _ = datasets.read_dataset(sample_dataset)
    posts, comments, manifest = datasets.read_dataset(exported)
    assert sorted(posts["post_id"]) == sorted(original_posts["post_id"])
    assert dict(zip(comments["comment_id"], comments["depth"])) == dict(
        zip(original_comments["comment_id"], original_comments["depth"]))
    assert manifest["query"]["method"] == "user-centric"
    assert set(posts["created_utc"]) == set(original_posts["created_utc"])


def test_analyze_command_produces_three_reports(sample_dataset, workspace, capsys):
    code = main.main(["analyze", "sample"])
    out = capsys.readouterr().out
    assert code == 0, out
    reports = sample_dataset / "reports"
    assert (reports / "temporal" / "SampleCampus_temporal_report.html").exists()
    assert (reports / "text" / "SampleCampus_text_analysis_report.html").exists()
    assert (reports / "network" / "SampleCampus_network_analysis_report.html").exists()
    assert list((reports / "network").glob("*.graphml")) and list((reports / "network").glob("*.gexf"))
    assert not list(reports.glob("*.db")), "the working database is removed afterwards"
    # one shared copy of the chart library, not one inside every chart
    assert sum(item.stat().st_size for item in (reports / "temporal").glob("*.html")) < 1_000_000


def test_analyze_skips_the_network_when_there_are_no_comments(workspace, capsys):
    writer = datasets.DatasetWriter(["PostsOnly"], root=workspace / "data")
    for post in sample.generate(n_posts=30)[0]:
        writer.add_post(post)
    writer.close()
    code = main.main(["analyze", "postsonly", "--network", "--temporal"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Network analysis skipped" in out


def test_text_analysis_keeps_words_apart(sample_dataset):
    """Guards the regular expression that once deleted every space."""
    from analyzers.text_analyzer import TextAnalyzer

    analyzer = TextAnalyzer(str(bridge.build_database(sample_dataset)), str(sample_dataset / "reports" / "text"))
    words = analyzer._preprocess_text("The **registrar** replied > quoted\n about transfer credits, finally!")
    assert "registrar" in words and "transfer" in words and "credits" in words
    assert all(len(word) < 15 for word in words)


# ------------------------------------------------------------ advanced CLI

@pytest.fixture
def advanced(with_credentials, monkeypatch):
    """tools/cli.py wired to a FakeReddit, with sleeps and signal handlers disabled."""
    import praw

    import core.reddit_scraper as core
    import tools.cli as cli
    from rrt import credentials

    reddit = fake_reddit.FakeReddit(n_posts=40, broken_users=["sample_user_002"])
    monkeypatch.setattr(praw, "Reddit", lambda **_kwargs: reddit)
    monkeypatch.setattr(credentials, "make_reddit", lambda creds=None: reddit)
    monkeypatch.setattr(core.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(signal, "signal", lambda *_args: None)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
        return cli.main()

    run.reddit = reddit
    return run


def test_archive_lives_in_one_folder_and_resumes(advanced, workspace, capsys):
    code = advanced("scrape", "--subreddit", "SampleCampus", "--max-users", "15")
    out = capsys.readouterr().out
    assert code == 0, out
    archive = workspace / "data" / "samplecampus_archive"
    assert {item.name for item in archive.iterdir()} >= {"samplecampus.db", "checkpoint.pkl", "scrape.log"}
    assert (archive / "scrape.log").stat().st_size > 0
    assert not (workspace / "databases").exists() and not (workspace / "logs").exists()

    with sqlite3.connect(archive / "samplecampus.db") as conn:
        done_first = conn.execute("SELECT COUNT(*) FROM users WHERE status != 'pending'").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] > 0
    assert done_first == 15

    code = advanced("scrape", "--subreddit", "SampleCampus", "--process-only", "--max-users", "10")
    assert code == 0
    with sqlite3.connect(archive / "samplecampus.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE status != 'pending'").fetchone()[0] == 25

    code = advanced("status", "--subreddit", "SampleCampus")
    out = capsys.readouterr().out
    assert code == 0 and "Users processed" in out and "--process-only" in out


def test_archive_exports_to_a_dataset_folder(advanced, workspace, capsys):
    advanced("scrape", "--subreddit", "SampleCampus", "--max-users", "20")
    capsys.readouterr()
    code = advanced("export", "--subreddit", "SampleCampus")
    out = capsys.readouterr().out
    assert code == 0, out
    found = datasets.list_datasets(workspace / "data")
    assert len(found) == 1
    posts, comments, manifest = datasets.read_dataset(found[0][0])
    assert len(posts) > 0 and len(comments) > 0
    assert manifest["subreddits"] == ["SampleCampus"]
    assert posts["permalink"].str.startswith("https://www.reddit.com/r/").all()


def test_existing_legacy_database_is_resumed_in_place(advanced, workspace, capsys):
    (workspace / "databases").mkdir()
    sqlite3.connect(workspace / "databases" / "samplecampus_data.db").close()
    code = advanced("scrape", "--subreddit", "SampleCampus", "--max-users", "5")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Resuming the existing archive" in out
    assert not (workspace / "data" / "samplecampus_archive").exists()
    with sqlite3.connect(workspace / "databases" / "samplecampus_data.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def test_advanced_scrape_explains_bad_credentials(advanced, workspace, capsys):
    advanced.reddit.login_error = fake_reddit.unauthorized()
    code = advanced("scrape", "--subreddit", "SampleCampus")
    out = capsys.readouterr().out
    assert code == 1
    assert "did not accept these credentials" in out and "Traceback" not in out
    assert not (workspace / "data" / "samplecampus_archive").exists()


def test_advanced_scrape_explains_missing_subreddit(advanced, workspace, capsys):
    advanced.reddit.missing = {"nosuchsub"}
    code = advanced("scrape", "--subreddit", "nosuchsub")
    out = capsys.readouterr().out
    assert code == 1
    assert "no community called r/nosuchsub" in out
    assert not (workspace / "data").exists() or not list((workspace / "data").iterdir())


def test_advanced_cli_needs_a_target(advanced, capsys):
    assert advanced("scrape") == 2
    assert "--subreddit NAME" in capsys.readouterr().out
    assert advanced("status") == 2
    assert advanced("analyze", "--subreddit", "neverscraped") == 2
    assert "No archive for r/neverscraped" in capsys.readouterr().out
