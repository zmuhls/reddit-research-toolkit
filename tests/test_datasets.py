"""Dataset folders: writing, reading, sharing, importing."""

import csv
import json
import zipfile

import pytest

from rrt import datasets, sample
from rrt.util import BadSubredditName, clean_subreddit_name, describe_estimate


def _write(root, n_posts=30, **kwargs):
    posts, comments = sample.generate(n_posts=n_posts)
    writer = datasets.DatasetWriter(["SampleCampus"], {"sort": "hot", "limit": n_posts}, root=root, **kwargs)
    for post in posts:
        writer.add_post(post)
    for comment in comments:
        writer.add_comment(comment)
    return writer, posts, comments


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("CUNY", "CUNY"),
        ("r/CUNY", "CUNY"),
        ("/r/CUNY/", "CUNY"),
        ("  cuny ", "cuny"),
        ("https://www.reddit.com/r/AskHistorians/top/?t=year", "AskHistorians"),
        ("old.reddit.com/r/data_viz", "data_viz"),
        ("CUNY+Baruch", "CUNY+Baruch"),
    ],
)
def test_subreddit_names_people_paste(typed, expected):
    assert clean_subreddit_name(typed) == expected


@pytest.mark.parametrize("typed", ["", "   ", "ask historians", "r/", "cuny!", "../etc"])
def test_bad_subreddit_names_are_rejected_with_a_message(typed):
    with pytest.raises(BadSubredditName) as error:
        clean_subreddit_name(typed)
    assert str(error.value)


def test_estimates_read_as_plain_language():
    assert describe_estimate(100, "none") == "under a minute"
    assert "min" in describe_estimate(500, "all")


def test_sample_is_deterministic_and_internally_consistent():
    first = sample.generate(n_posts=50)
    assert first == sample.generate(n_posts=50)
    posts, comments = first
    post_ids = {post["post_id"] for post in posts}
    comment_ids = {comment["comment_id"] for comment in comments}
    assert len(post_ids) == 50
    for comment in comments:
        assert comment["post_id"] in post_ids
        parent = comment["parent_id"]
        assert parent[3:] in (post_ids if parent.startswith("t3_") else comment_ids)
    for post in posts:
        assert post["num_comments"] == sum(1 for c in comments if c["post_id"] == post["post_id"])


def test_writer_produces_a_self_describing_folder(tmp_path):
    writer, posts, comments = _write(tmp_path)
    path = writer.close()

    assert {item.name for item in path.iterdir()} == {"posts.csv", "comments.csv", "manifest.json", "README.md"}
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["format"] == datasets.FORMAT_NAME
    assert manifest["status"] == "complete"
    assert manifest["counts"]["posts"] == len(posts)
    assert manifest["counts"]["comments"] == len(comments)
    assert manifest["files"]["posts.csv"]["rows"] == len(posts)
    assert manifest["date_range"]["first_post_utc"] == min(post["created_utc"] for post in posts)
    assert datasets.verify(path) == []

    with open(path / "posts.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(datasets.POST_COLUMNS)
    assert rows[0]["created_utc"].endswith("Z")

    readme = (path / "README.md").read_text()
    for column in list(datasets.POST_COLUMNS) + list(datasets.COMMENT_COLUMNS):
        assert f"`{column}`" in readme


@pytest.mark.skipif(not hasattr(__import__("time"), "tzset"), reason="time.tzset is not available on Windows")
def test_timestamps_are_utc_regardless_of_machine_timezone(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert datasets.utc_iso(1767225600) == "2026-01-01T00:00:00Z"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_interrupted_run_leaves_usable_files_and_says_so(tmp_path):
    writer, posts, _ = _write(tmp_path, n_posts=12)
    path = writer.close(datasets.STATUS_INTERRUPTED)
    manifest = datasets.load_manifest(path)
    assert manifest["status"] == "interrupted"
    assert "Partial dataset" in (path / "README.md").read_text()
    frame, _, _ = datasets.read_dataset(path)
    assert len(frame) == len(posts)


def test_rows_reach_disk_before_close(tmp_path):
    writer, posts, _ = _write(tmp_path, n_posts=10)
    writer.flush()
    with open(writer.path / "posts.csv", newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == len(posts)
    assert datasets.load_manifest(writer.path)["status"] == "in_progress"
    writer.close()


def test_text_with_commas_quotes_newlines_and_brackets_survives(tmp_path):
    writer = datasets.DatasetWriter(["Test"], root=tmp_path)
    tricky = 'He said "no", then\nleft. [deleted] =SUM(A1) NA null'
    writer.add_post({"post_id": "a1", "subreddit": "Test", "title": tricky, "author": "[deleted]",
                     "created_utc": "2026-01-01T00:00:00Z", "score": 1, "num_comments": 0, "selftext": tricky})
    path = writer.close()
    posts, _, _ = datasets.read_dataset(path)
    assert posts.loc[0, "title"] == tricky
    assert posts.loc[0, "selftext"] == tricky
    assert posts.loc[0, "author"] == "[deleted]"


def test_zip_round_trip_and_tamper_detection(tmp_path):
    writer, posts, comments = _write(tmp_path / "a")
    original = writer.close()
    archive = datasets.export_zip(original, tmp_path)
    with zipfile.ZipFile(archive) as bundle:
        assert sorted(name.split("/")[-1] for name in bundle.namelist()) == ["README.md", "comments.csv", "manifest.json", "posts.csv"]

    imported = datasets.import_zip(archive, tmp_path / "b")
    frame, comment_frame, manifest = datasets.read_dataset(imported)
    assert (len(frame), len(comment_frame)) == (len(posts), len(comments))
    assert manifest["dataset_id"] == original.name
    assert datasets.verify(imported) == []

    with open(imported / "posts.csv", "a", encoding="utf-8") as handle:
        handle.write("extra\n")
    assert any("changed" in problem for problem in datasets.verify(imported))


def test_import_refuses_archives_that_are_not_bundles(tmp_path):
    bogus = tmp_path / "notes.zip"
    with zipfile.ZipFile(bogus, "w") as bundle:
        bundle.writestr("notes.txt", "hello")
    with pytest.raises(datasets.DatasetError, match="posts.csv"):
        datasets.import_zip(bogus, tmp_path / "data")

    not_a_zip = tmp_path / "broken.zip"
    not_a_zip.write_text("this is not a zip")
    with pytest.raises(datasets.DatasetError, match="not a zip"):
        datasets.import_zip(not_a_zip, tmp_path / "data")


def test_import_cannot_write_outside_the_data_folder(tmp_path):
    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as bundle:
        bundle.writestr("../../escaped/posts.csv", "post_id,title\nx1,hi\n")
        bundle.writestr("../../evil.sh", "rm -rf /")
        bundle.writestr("manifest.json", json.dumps({"dataset_id": "../../../outside"}))
    target = datasets.import_zip(hostile, tmp_path / "data")
    assert target.parent == tmp_path / "data"
    assert (target / "posts.csv").exists()
    assert not (tmp_path / "escaped").exists()
    assert not list(tmp_path.rglob("evil.sh"))


def test_older_loose_csv_files_import_as_a_dataset(tmp_path):
    posts_csv = tmp_path / "CUNY_posts_20250101_120000.csv"
    comments_csv = tmp_path / "CUNY_comments_20250101_120000.csv"
    posts_csv.write_text(
        "post_id,title,author,created_utc,score,num_comments,flair\n"
        "abc,Hello,alice,2025-01-01T09:30:00,5,1,Question\n"
        "def,World,bob,1735725600,2,0,\n",
        encoding="utf-8",
    )
    comments_csv.write_text(
        "comment_id,post_id,parent_id,author,body,score,created_utc,depth\n"
        "c1,abc,t3_abc,bob,Hi there,3,2025-01-01T10:00:00,0\n",
        encoding="utf-8",
    )
    path = datasets.import_csvs(posts_csv, comments_csv, tmp_path / "data")
    posts, comments, manifest = datasets.read_dataset(path)
    assert manifest["source"] == "import"
    assert manifest["subreddits"] == ["CUNY"]
    assert path.name.startswith("cuny_")
    assert list(posts["subreddit"]) == ["CUNY", "CUNY"]
    assert len(comments) == 1
    assert posts.loc[1, "created_utc"].isoformat().startswith("2025-01-01T10:00:00")


def test_dashboard_style_columns_import(tmp_path):
    exported = tmp_path / "reddit_data.csv"
    exported.write_text("id,title,author,created_utc,score,num_comments,subreddit\nt3_zz9,Hi,carol,2026-05-01 12:00:00+00:00,4,2,Baruch\n")
    path = datasets.import_csvs(exported, None, tmp_path / "data")
    posts, _, manifest = datasets.read_dataset(path)
    assert posts.loc[0, "post_id"] == "zz9"
    assert manifest["subreddits"] == ["Baruch"]


def test_csv_without_ids_is_refused_with_guidance(tmp_path):
    bad = tmp_path / "random.csv"
    bad.write_text("name,value\na,1\n")
    with pytest.raises(datasets.DatasetError, match="post_id"):
        datasets.import_csvs(bad, None, tmp_path / "data")


def test_datasets_resolve_by_name_label_or_newest(tmp_path):
    first = datasets.DatasetWriter(["CUNY"], root=tmp_path)
    first.add_post({"post_id": "1", "created_utc": "2026-01-01T00:00:00Z"})
    first_path = first.close()
    second = datasets.DatasetWriter(["Baruch"], root=tmp_path)
    second.add_post({"post_id": "2", "created_utc": "2026-01-01T00:00:00Z"})
    second_path = second.close()

    assert datasets.resolve_dataset(first_path.name, tmp_path) == first_path
    assert datasets.resolve_dataset("cuny", tmp_path) == first_path
    assert datasets.resolve_dataset("BARUCH", tmp_path) == second_path
    assert datasets.resolve_dataset(str(second_path), tmp_path) == second_path
    assert datasets.resolve_dataset(None, tmp_path) in (first_path, second_path)
    with pytest.raises(datasets.DatasetError, match="more than one"):
        datasets.resolve_dataset("2", tmp_path)
    with pytest.raises(datasets.DatasetError, match="No dataset named"):
        datasets.resolve_dataset("nothing-like-this", tmp_path)


def test_empty_data_folder_explains_how_to_start(tmp_path):
    with pytest.raises(datasets.DatasetError, match="python main.py sample"):
        datasets.resolve_dataset(None, tmp_path / "empty")
    assert datasets.list_datasets(tmp_path / "empty") == []


def test_synthetic_data_is_labelled_everywhere(tmp_path):
    path = sample.write_sample(tmp_path, n_posts=20)
    manifest = datasets.load_manifest(path)
    assert manifest["source"] == "synthetic"
    readme = (path / "README.md").read_text()
    assert "Synthetic sample" in readme
    assert "## Handling" not in readme
