"""The terminal experience, end to end, against the fake Reddit."""

import json

import pytest

import fake_reddit
import main
from rrt import credentials, datasets, doctor
from rrt.errors import explain


def run(capsys, *argv):
    code = main.main(list(argv))
    output = capsys.readouterr()
    return code, output.out + output.err


def only_dataset(workspace):
    found = datasets.list_datasets(workspace / "data")
    assert len(found) == 1, [path.name for path, _ in found]
    return found[0]


# ---------------------------------------------------------------- collecting

def test_scrape_writes_a_complete_dataset(fake, workspace, capsys):
    reddit = fake(n_posts=40)
    code, out = run(capsys, "scrape", "r/samplecampus", "--limit", "25")
    assert code == 0
    assert "Done." in out and "Next steps" in out

    path, manifest = only_dataset(workspace)
    assert manifest["status"] == "complete"
    assert manifest["subreddits"] == ["SampleCampus"]  # Reddit's own capitalization
    assert manifest["query"] == {"sort": "hot", "time_filter": None, "limit": 25, "comments": "all"}

    posts, comments, _ = datasets.read_dataset(path)
    expected_ids = [post["post_id"] for post in reddit.expected_posts[:25]]
    assert list(posts["post_id"]) == expected_ids
    expected_comments = [c for c in reddit.expected_comments if c["post_id"] in set(expected_ids)]
    assert len(comments) == len(expected_comments)
    assert dict(zip(comments["comment_id"], comments["depth"])) == {c["comment_id"]: c["depth"] for c in expected_comments}
    assert str(posts["created_utc"].dt.tz) == "UTC"
    assert posts["created_utc"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ") == reddit.expected_posts[0]["created_utc"]


def test_older_command_form_still_works(fake, workspace, capsys):
    fake(n_posts=10)
    code, _ = run(capsys, "SampleCampus", "-l", "5", "--sort", "top", "-t", "year", "--no-comments", "-f", "both")
    assert code == 0
    path, manifest = only_dataset(workspace)
    assert manifest["counts"] == {"posts": 5, "comments": 0, "authors": manifest["counts"]["authors"]}
    assert manifest["query"]["sort"] == "top" and manifest["query"]["time_filter"] == "year"
    assert not (path / "comments.csv").exists()
    data = json.loads((path / "data.json").read_text())
    assert len(data["posts"]) == 5


def test_sort_and_comment_mode_reach_reddit(fake, workspace, capsys):
    reddit = fake(n_posts=8)
    run(capsys, "scrape", "SampleCampus", "-l", "8", "--sort", "top", "-t", "month", "--comments", "quick")
    assert ("top", {"time_filter": "month", "limit": 8}) in reddit.calls
    limits = {limit for submission in reddit.submissions for limit in submission.comments.replace_more_limits}
    assert limits == {0}

    reddit = fake(n_posts=8)
    run(capsys, "scrape", "SampleCampus", "-l", "8")
    limits = {limit for submission in reddit.submissions for limit in submission.comments.replace_more_limits}
    assert limits == {None}


def test_fewer_posts_than_asked_is_explained(fake, workspace, capsys):
    fake(n_posts=7)
    code, out = run(capsys, "scrape", "SampleCampus", "-l", "50", "--no-comments")
    assert code == 0
    assert "fewer than the limit" in out
    assert only_dataset(workspace)[1]["counts"]["posts"] == 7


def test_removed_threads_are_skipped_not_fatal(fake, workspace, capsys):
    fake(n_posts=10, comment_failures={0: fake_reddit.not_found(), 3: fake_reddit.server_error()})
    code, out = run(capsys, "scrape", "SampleCampus", "-l", "10")
    assert code == 0
    assert "thread(s) had comments Reddit would not return" in out
    assert only_dataset(workspace)[1]["counts"]["posts"] == 10


# ------------------------------------------------------------------ failures

def test_no_credentials_points_to_setup_and_to_keyless_paths(workspace, capsys):
    code, out = run(capsys, "scrape", "CUNY")
    assert code == 2
    assert "python main.py setup" in out and "python main.py sample" in out and "python main.py access" in out
    assert "Traceback" not in out
    assert datasets.list_datasets(workspace / "data") == []


def test_placeholder_credentials_are_caught_before_any_request(workspace, capsys):
    (workspace / ".env").write_text("REDDIT_CLIENT_ID=your_client_id_here\nREDDIT_CLIENT_SECRET=your_client_secret_here\n")
    code, out = run(capsys, "scrape", "CUNY")
    assert code == 2
    assert "placeholder" in out


@pytest.mark.parametrize(
    "options, subreddit, phrase",
    [
        (dict(missing=["nosuchsub"]), "nosuchsub", "no community called r/nosuchsub"),
        (dict(banned=["gonesub"]), "gonesub", "could not find r/gonesub"),
        (dict(private=["secretclub"]), "secretclub", "refused access to r/secretclub"),
        (dict(read_error=fake_reddit.unauthorized()), "CUNY", "did not accept these credentials"),
        (dict(read_error=fake_reddit.offline()), "CUNY", "could not reach Reddit"),
        (dict(read_error=fake_reddit.server_error()), "CUNY", "having trouble"),
    ],
)
def test_failures_are_explained_without_tracebacks(fake, workspace, capsys, options, subreddit, phrase):
    fake(**options)
    code, out = run(capsys, "scrape", subreddit)
    assert code == 1
    assert phrase in out
    assert "Try this" in out
    assert "Traceback" not in out
    assert datasets.list_datasets(workspace / "data") == [], "a failed lookup must not leave an empty dataset behind"


def test_debug_flag_adds_the_traceback(fake, workspace, capsys):
    fake(missing=["nosuchsub"])
    _, out = run(capsys, "scrape", "nosuchsub", "--debug")
    assert "Traceback" in out


def test_rate_limit_mid_run_saves_what_was_collected(fake, workspace, capsys):
    fake(n_posts=60, fail_after=25, fail_with=fake_reddit.rate_limited())
    code, out = run(capsys, "scrape", "SampleCampus", "-l", "60", "--no-comments")
    assert code == 1
    assert "Ended early" in out and "slow down" in out and "42 seconds" in out
    path, manifest = only_dataset(workspace)
    assert manifest["status"] == "failed"
    assert manifest["counts"]["posts"] == 25
    assert "Partial dataset" in (path / "README.md").read_text()
    assert len(datasets.read_dataset(path)[0]) == 25


def test_ctrl_c_saves_what_was_collected(fake, workspace, capsys):
    fake(n_posts=60, interrupt_after=12)
    code, out = run(capsys, "scrape", "SampleCampus", "-l", "60")
    assert code == 130
    assert "Stopped early" in out
    _, manifest = only_dataset(workspace)
    assert manifest["status"] == "interrupted"
    assert manifest["counts"]["posts"] == 12


def test_empty_listing_leaves_nothing_behind(fake, workspace, capsys):
    fake(empty=["quietplace"])
    code, out = run(capsys, "scrape", "quietplace")
    assert code == 0
    assert "returned no posts" in out
    assert datasets.list_datasets(workspace / "data") == []


def test_bad_names_never_reach_reddit(fake, workspace, capsys):
    reddit = fake()
    code, out = run(capsys, "scrape", "ask historians")
    assert code == 2 and "one word" in out
    assert reddit.requests == 0


@pytest.mark.parametrize(
    "error, code",
    [
        (fake_reddit.unauthorized(), "bad-credentials"),
        (fake_reddit.forbidden(), "forbidden"),
        (fake_reddit.not_found(), "not-found"),
        (fake_reddit.redirect(), "no-such-subreddit"),
        (fake_reddit.rate_limited(), "rate-limited"),
        (fake_reddit.server_error(), "reddit-down"),
        (fake_reddit.offline(), "network"),
        (ModuleNotFoundError("No module named 'plotly'", name="plotly"), "missing-package"),
        (PermissionError(13, "Permission denied", "posts.csv"), "permission"),
        (RuntimeError("boom"), "unexpected"),
    ],
)
def test_every_known_failure_has_an_explanation(error, code):
    friendly = explain(error, "CUNY")
    assert friendly.code == code
    assert friendly.title and friendly.why and friendly.fixes


def test_explanations_survive_hostile_subreddit_text():
    friendly = explain(fake_reddit.not_found(), "[bold]x[/bold]/../")
    assert "[bold]" not in " ".join(friendly.fixes) + friendly.title


# ------------------------------------------------------- working without keys

def test_sample_list_show_export_import_need_no_credentials(workspace, capsys):
    code, out = run(capsys, "sample", "--posts", "40")
    assert code == 0 and "Made a practice dataset" in out

    code, out = run(capsys, "sample", "--posts", "40")
    assert code == 0 and "already here" in out
    path, manifest = only_dataset(workspace)
    assert manifest["source"] == "synthetic"

    code, out = run(capsys, "list")
    assert code == 0 and path.name in out and "sample" in out

    code, out = run(capsys, "show")
    assert code == 0 and "posts by score" in out and "Synthetic practice data" in out

    code, out = run(capsys, "export", "sample", "-o", str(workspace))
    assert code == 0
    archive = workspace / f"{path.name}.zip"
    assert archive.exists()

    code, out = run(capsys, "import", str(archive))
    assert code == 0 and "Imported as" in out
    assert len(datasets.list_datasets(workspace / "data")) == 2


def test_list_on_an_empty_folder_says_how_to_begin(workspace, capsys):
    code, out = run(capsys, "list")
    assert code == 0
    assert "python main.py sample" in out


def test_import_explains_wrong_inputs(workspace, capsys):
    code, out = run(capsys, "import", "notes.txt")
    assert code == 2 and "one .zip bundle" in out
    code, out = run(capsys, "import", "missing.zip")
    assert code == 1 and "No file at" in out


def test_show_explains_unknown_dataset(workspace, capsys):
    run(capsys, "sample", "--posts", "20")
    code, out = run(capsys, "show", "nothing-like-this")
    assert code == 2 and "python main.py list" in out


def test_access_command_states_the_dates(workspace, capsys):
    code, out = run(capsys, "access")
    assert code == 0
    for fact in ("October 31, 2026", "January 12, 2027", "March 2027", "Reddit for Researchers"):
        assert fact in out


def test_help_without_a_terminal_lists_first_steps(workspace, capsys):
    code, out = run(capsys)
    assert code == 0
    assert "first steps" in out and "python main.py sample" in out


# -------------------------------------------------------------------- setup

def test_check_passes_without_credentials_and_says_what_is_possible(workspace, capsys):
    code, out = run(capsys, "check", "--offline")
    assert code == 0
    assert "Core packages" in out and "not set up" in out and "python main.py sample" in out


def test_check_reports_a_working_connection(fake, workspace, capsys):
    fake()
    code, out = run(capsys, "check")
    assert code == 0
    assert "signed in and read a public post" in out and "Everything works" in out


def test_check_distinguishes_bad_login_from_refused_data(fake, workspace, capsys):
    fake(login_error=fake_reddit.unauthorized())
    code, out = run(capsys, "check")
    assert code == 1 and "rejected the sign-in" in out

    fake(read_error=fake_reddit.forbidden())
    code, out = run(capsys, "check")
    assert code == 1 and "refused to serve data" in out and "REDDIT_API_ACCESS.md" in out


def test_env_file_quirks(workspace):
    (workspace / ".env").write_text(
        '﻿# comment\nexport REDDIT_CLIENT_ID = "abc123"\nREDDIT_CLIENT_SECRET=\'s3cret-value-long\'\nOTHER=keep me\n',
        encoding="utf-8",
    )
    creds = credentials.load()
    assert (creds.client_id, creds.client_secret, creds.source) == ("abc123", "s3cret-value-long", ".env")
    assert credentials.problems(creds) == []

    credentials.save("newid", "newsecret-longer", credentials.default_user_agent("/u/zach"))
    text = (workspace / ".env").read_text()
    assert "OTHER=keep me" in text and "REDDIT_CLIENT_ID=newid" in text and text.count("REDDIT_CLIENT_ID") == 1
    assert "(by /u/zach)" in text
    assert credentials.default_user_agent("ursula").endswith("(by /u/ursula)")


def test_common_env_mistakes_are_named(workspace):
    assert "no .env file" in credentials.problems()[0]

    (workspace / ".env.txt").write_text("REDDIT_CLIENT_ID=abc\n")
    assert ".env.txt" in credentials.problems()[0]
    (workspace / ".env.txt").unlink()

    (workspace / ".env").write_text("REDDIT_CLIENT_ID=a-much-longer-value-than-the-secret\nREDDIT_CLIENT_SECRET=short\n")
    assert any("swapped" in problem for problem in credentials.problems())

    (workspace / ".env").write_text("REDDIT_CLIENT_ID=abc def\nREDDIT_CLIENT_SECRET=\n")
    found = " ".join(credentials.problems())
    assert "space" in found and "REDDIT_CLIENT_SECRET is empty" in found


def test_doctor_flags_missing_packages(monkeypatch):
    check = doctor.check_packages([("definitely_not_installed_pkg", "nope")], "Core packages", "requirements.txt", required=True)
    assert check.status == doctor.FAIL and "pip install -r requirements.txt" in check.fix


def test_setup_test_names_the_unapproved_app_case(fake, workspace, capsys, monkeypatch):
    fake(read_error=fake_reddit.forbidden())
    code = main._test_and_report(main._ns(type("Args", (), {"debug": False, "data_dir": None})()))
    out = capsys.readouterr().out
    assert code == 1
    assert "then refused to serve data" in out and "approved apps only" in out and "REDDIT_API_ACCESS.md" in out
