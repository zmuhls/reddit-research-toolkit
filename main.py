#!/usr/bin/env python3
"""
Reddit Research Toolkit - command line

    python main.py                 guided menu
    python main.py check           test your setup
    python main.py sample          make a practice dataset (no credentials)
    python main.py scrape CUNY     collect posts and comments from r/CUNY
    python main.py list            see your datasets

Run 'python main.py --help' for every command.
"""

import sys

if sys.version_info < (3, 10):
    print(
        "The Reddit Research Toolkit needs Python 3.10 or newer.\n"
        f"This terminal is running Python {sys.version_info.major}.{sys.version_info.minor}.\n\n"
        "Install a current Python from https://www.python.org/downloads/ and try again.\n"
        "On macOS and Linux the command may be 'python3' in place of 'python'."
    )
    sys.exit(1)

try:
    import rich  # noqa: F401
except ModuleNotFoundError:
    print(
        "The toolkit's packages are not installed in this Python environment.\n\n"
        "From the toolkit folder, run these once:\n\n"
        "  macOS / Linux                      Windows\n"
        "  python3 -m venv .venv              py -m venv .venv\n"
        "  source .venv/bin/activate          .venv\\Scripts\\activate\n"
        "  python -m pip install -r requirements.txt\n\n"
        "If you already did, the virtual environment is not active in this window.\n"
        "Run the 'activate' line again, then retry."
    )
    sys.exit(1)

import argparse
import os
import shutil
import traceback
import webbrowser
from pathlib import Path
from typing import List, Optional

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, IntPrompt, Prompt

from rrt import __version__, credentials, datasets, doctor
from rrt import console as ui
from rrt.console import console, e
from rrt.errors import ACCESS_DOC, explain
from rrt.util import BadSubredditName, clean_subreddit_name, describe_estimate, estimate_seconds

DASHBOARD_URL = "https://huggingface.co/spaces/milwright/reddit-dashboard"
RESEARCHERS_URL = "https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program"

COMMANDS = ("scrape", "info", "sample", "list", "show", "export", "import", "analyze", "setup", "check", "access", "help")

EXIT_OK, EXIT_ERROR, EXIT_SETUP, EXIT_INTERRUPTED = 0, 1, 2, 130


# ==========================================================================
# Shared pieces
# ==========================================================================

def _rel(path: Path) -> str:
    """Show a path relative to the current folder when that is shorter."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # different drive on Windows
        return str(path)
    return str(path) if relative.startswith("..") else relative


def _report(exc: BaseException, args, subreddit: Optional[str] = None) -> int:
    """Print a failure in plain language. With --debug, print the traceback too."""
    friendly = explain(exc, subreddit)
    ui.error_panel(friendly.title, friendly.why, friendly.fixes, friendly.detail)
    if getattr(args, "debug", False):
        console.print()
        console.print("[hint]Full error (--debug):[/hint]")
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    return EXIT_ERROR


def _access_summary() -> str:
    return (
        "Reddit is closing its public API. As of November 2026:\n\n"
        f"  {ui.BULLET} [head]Have a working client ID and secret?[/head] They still work. Reddit begins\n"
        "    removing unregistered apps on January 12, 2027 and ends public API\n"
        "    access for everyone in March 2027.\n"
        f"  {ui.BULLET} [head]Need new credentials?[/head] Reddit stopped accepting API access requests\n"
        "    on October 31, 2026. Creating an app at reddit.com/prefs/apps no longer\n"
        "    grants access.\n"
        f"  {ui.BULLET} [head]Doing academic research?[/head] Reddit for Researchers is the one route Reddit\n"
        "    names for research access. It needs a university affiliation and a sponsor.\n"
        f"  {ui.BULLET} [head]None of the above?[/head] You can do all the analysis work with the sample\n"
        "    dataset or a dataset someone shares with you.\n\n"
        f"Details, links, and sources: [path]{ACCESS_DOC}[/path]"
    )


def _no_credentials(found_problems: List[str]) -> int:
    lines = []
    if found_problems:
        lines.append("[head]The toolkit found[/head]")
        lines += [f"  {ui.BULLET} {e(problem)}" for problem in found_problems]
        lines.append("")
    lines += [
        "Collecting new data from Reddit needs a client ID and secret.",
        "",
        "[head]If you have them[/head]",
        "    [cmd]python main.py setup[/cmd]      saves them and tests the connection",
        "",
        "[head]If you do not[/head]",
        "    [cmd]python main.py sample[/cmd]     makes a practice dataset (no credentials)",
        "    [cmd]python main.py import[/cmd]     opens a dataset someone shared with you",
        "    [cmd]python main.py access[/cmd]     explains who can still get credentials",
    ]
    ui.note_panel("Reddit credentials are not set up", "\n".join(lines))
    return EXIT_SETUP


def _make_scraper(args):
    """Return (scraper, exit_code). exit_code is None when the scraper is ready."""
    creds = credentials.load()
    found = credentials.problems(creds)
    blocking = [problem for problem in found if "may be swapped" not in problem]
    if not creds.present or blocking:
        return None, _no_credentials(found)
    from simple_scraper import SimpleRedditScraper

    reddit = credentials.make_reddit(creds)
    return SimpleRedditScraper(reddit=reddit, data_dir=datasets.data_root(args.data_dir)), None


def _clean_or_explain(raw: str) -> Optional[str]:
    try:
        return clean_subreddit_name(raw)
    except BadSubredditName as exc:
        ui.fail(e(exc))
        return None


def _dataset_or_explain(name: Optional[str], args) -> Optional[Path]:
    try:
        return datasets.resolve_dataset(name, datasets.data_root(args.data_dir))
    except datasets.DatasetError as exc:
        ui.fail(e(exc))
        return None


def _summary_rows(manifest: dict) -> List[tuple]:
    counts = manifest.get("counts", {})
    span = manifest.get("date_range", {})
    first, last = span.get("first_post_utc"), span.get("last_post_utc")
    rows = [
        ("Community", ", ".join(f"r/{name}" for name in manifest.get("subreddits", [])) or "unknown"),
        ("Posts", f"{counts.get('posts', 0):,}"),
        ("Comments", f"{counts.get('comments', 0):,}"),
        ("Distinct authors", f"{counts.get('authors', 0):,}"),
    ]
    if first and last:
        rows.append(("Posts dated", f"{first[:10]} to {last[:10]} (UTC)"))
    return rows


def _print_dataset_next_steps(path: Path, include_show: bool = True) -> None:
    posts_csv = _rel(path / datasets.POSTS_FILE).replace("\\", "/")
    steps = [
        ("Look at a summary and the top posts", f"python main.py show {path.name}"),
        ("Chart it (activity over time, common words, who talks to whom)", f"python main.py analyze {path.name} --open"),
        ("Explore it in the browser dashboard: export a zip, then upload it there", f"python main.py export {path.name}"),
    ]
    ui.next_steps("Next steps", steps if include_show else steps[1:])
    console.print(f"  {ui.BULLET} Load it in Python")
    ui.command("import pandas as pd")
    ui.command(f'posts = pd.read_csv("{posts_csv}", parse_dates=["created_utc"])')
    console.print()
    ui.hint(f"Every column is explained in {e(_rel(path / datasets.README_FILE))}")


# ==========================================================================
# Commands
# ==========================================================================

def cmd_scrape(args) -> int:
    if getattr(args, "info", False):
        return cmd_info(args)

    subreddit = _clean_or_explain(args.subreddit)
    if subreddit is None:
        return EXIT_SETUP
    if args.limit < 1:
        ui.fail("--limit must be 1 or more.")
        return EXIT_SETUP

    comments_mode = "none" if args.no_comments else args.comments
    scraper, code = _make_scraper(args)
    if scraper is None:
        return code

    # Look the community up first, so a typo fails here and not mid-run.
    special = "+" in subreddit or subreddit.lower() in ("all", "popular")
    if not special:
        try:
            with console.status(f"Looking up r/{subreddit} ..."):
                about = scraper.get_subreddit_info(subreddit, raise_errors=True)
        except KeyboardInterrupt:
            ui.info("\nStopped. Nothing was collected.")
            return EXIT_INTERRUPTED
        except Exception as exc:
            return _report(exc, args, subreddit)
        subreddit = about.get("name") or subreddit
        members = about.get("subscribers")
        members_text = f", {members:,} members" if isinstance(members, int) else ""
        ui.ok(f"Found [head]r/{e(subreddit)}[/head]: {e(about.get('title') or '')}{members_text}")

    if args.limit > 1000:
        ui.warn("Reddit serves about 1,000 posts per sort order, so the run may end before reaching the limit.")

    sort_text = args.sort + (f" of the past {args.time_filter}" if args.sort == "top" and args.time_filter != "all"
                             else " of all time" if args.sort == "top" else "")
    comments_text = {"all": "every comment", "quick": "comments Reddit sends with each thread", "none": "no comments"}[comments_mode]
    ui.heading("Plan")
    ui.table(None, ["", ""], [
        ("Posts", f"up to {args.limit:,} ({sort_text})"),
        ("Comments", comments_text),
        ("Estimated time", describe_estimate(args.limit, comments_mode)),
    ])
    _, high = estimate_seconds(args.limit, comments_mode)
    if high > 15 * 60 and ui.interactive() and not args.yes:
        ui.hint("Long runs are safe to stop with Ctrl+C. The rows collected so far are saved.")
        ui.hint("Faster options: a smaller --limit, --comments quick, or --comments none.")
        if not Confirm.ask("Start?", default=True):
            ui.info("Nothing was collected.")
            return EXIT_OK
    console.print()

    query = {
        "sort": args.sort,
        "time_filter": args.time_filter if args.sort == "top" else None,
        "limit": args.limit,
        "comments": comments_mode,
    }
    writer = datasets.DatasetWriter([subreddit], query, root=datasets.data_root(args.data_dir))
    status, failure = datasets.STATUS_COMPLETE, None

    try:
        if console.is_terminal:
            progress = Progress(
                SpinnerColumn(), TextColumn("[head]Collecting[/head]"), BarColumn(), MofNCompleteColumn(),
                TextColumn("posts  {task.fields[comments]} comments"), TimeElapsedColumn(),
                console=console, transient=False,
            )
            with progress:
                task = progress.add_task("collect", total=args.limit, comments="0")

                def on_progress(done: int, comment_count: int, _title: str) -> None:
                    progress.update(task, completed=done, comments=f"{comment_count:,}")

                scraper.scrape_subreddit(subreddit, args.limit, args.sort, args.time_filter,
                                         comments=comments_mode, writer=writer, on_progress=on_progress)
                progress.update(task, total=max(writer.post_count, 1), completed=writer.post_count)
        else:
            def on_progress(done: int, comment_count: int, _title: str) -> None:
                if done % 25 == 0:
                    print(f"  {done} posts, {comment_count} comments so far", flush=True)

            scraper.scrape_subreddit(subreddit, args.limit, args.sort, args.time_filter,
                                     comments=comments_mode, writer=writer, on_progress=on_progress)
    except KeyboardInterrupt:
        status = datasets.STATUS_INTERRUPTED
    except Exception as exc:
        status, failure = datasets.STATUS_FAILED, exc

    if writer.post_count == 0:
        writer.close(status)
        shutil.rmtree(writer.path, ignore_errors=True)
        if failure is not None:
            return _report(failure, args, subreddit)
        if status == datasets.STATUS_INTERRUPTED:
            ui.info("\nStopped before any posts arrived. Nothing was saved.")
            return EXIT_INTERRUPTED
        ui.warn(f"Reddit returned no posts for r/{e(subreddit)} with these settings.")
        ui.hint("A narrow time window is the usual reason. Try --sort new, or --sort top -t all.")
        return EXIT_OK

    friendly = explain(failure, subreddit) if failure is not None else None
    path = writer.close(status, write_json=args.format in ("json", "both"), error=friendly.title if friendly else "")
    manifest = datasets.load_manifest(path)

    console.print()
    if status == datasets.STATUS_COMPLETE:
        ui.ok(f"[head]Done.[/head] Saved to [path]{e(_rel(path))}[/path]")
    elif status == datasets.STATUS_INTERRUPTED:
        ui.warn(f"[head]Stopped early.[/head] The rows collected so far are saved in [path]{e(_rel(path))}[/path]")
    else:
        ui.warn(f"[head]Ended early with an error.[/head] The rows collected before it are saved in [path]{e(_rel(path))}[/path]")

    console.print()
    ui.table(None, ["", ""], _summary_rows(manifest))
    console.print()
    files = [(name, datasets.human_size(entry.get("bytes", 0))) for name, entry in manifest.get("files", {}).items()]
    files += [(datasets.MANIFEST_FILE, "the collection record"), (datasets.README_FILE, "every column explained")]
    ui.table("Files", ["", ""], files)
    if scraper.skipped_threads:
        console.print()
        ui.hint(f"{scraper.skipped_threads} thread(s) had comments Reddit would not return (removed or restricted). Their posts are included.")
    if writer.post_count < args.limit and status == datasets.STATUS_COMPLETE:
        ui.hint(f"Reddit had {writer.post_count:,} posts to offer for this query, fewer than the limit of {args.limit:,}.")

    if failure is not None:
        _report(failure, args, subreddit)
        return EXIT_ERROR
    _print_dataset_next_steps(path)
    return EXIT_INTERRUPTED if status == datasets.STATUS_INTERRUPTED else EXIT_OK


def cmd_info(args) -> int:
    subreddit = _clean_or_explain(args.subreddit)
    if subreddit is None:
        return EXIT_SETUP
    scraper, code = _make_scraper(args)
    if scraper is None:
        return code
    try:
        with console.status(f"Looking up r/{subreddit} ..."):
            about = scraper.get_subreddit_info(subreddit, raise_errors=True)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as exc:
        return _report(exc, args, subreddit)
    description = (about.get("description") or "").strip()
    ui.heading(f"r/{about.get('name', subreddit)}")
    ui.table(None, ["", ""], [
        ("Title", about.get("title") or ""),
        ("Members", f"{about['subscribers']:,}" if isinstance(about.get("subscribers"), int) else "unknown"),
        ("Created (UTC)", (about.get("created_utc") or "")[:10]),
        ("Type", about.get("subreddit_type") or ""),
        ("NSFW", "yes" if about.get("over18") else "no"),
        ("About", description[:300] + ("..." if len(description) > 300 else "")),
    ])
    return EXIT_OK


def cmd_sample(args) -> int:
    from rrt import sample

    root = datasets.data_root(args.data_dir)
    for path, manifest in datasets.list_datasets(root):
        query = manifest.get("query", {})
        if manifest.get("source") == "synthetic" and query.get("seed") == args.seed and query.get("posts") == args.posts:
            ui.ok(f"The sample dataset is already here: [path]{e(_rel(path))}[/path]")
            _print_dataset_next_steps(path)
            return EXIT_OK
    path = sample.write_sample(root, n_posts=args.posts, seed=args.seed)
    manifest = datasets.load_manifest(path)
    ui.ok(f"Made a practice dataset in [path]{e(_rel(path))}[/path]")
    console.print()
    ui.table(None, ["", ""], _summary_rows(manifest))
    console.print()
    ui.hint("Every row is invented. It behaves like real Reddit data for practice, and it is not evidence of anything.")
    _print_dataset_next_steps(path)
    return EXIT_OK


def cmd_list(args) -> int:
    root = datasets.data_root(args.data_dir)
    found = datasets.list_datasets(root)
    if not found:
        ui.info(f"No datasets in [path]{e(_rel(root))}[/path] yet.")
        ui.next_steps("Make your first one", [
            ("Practice data, no credentials needed", "python main.py sample"),
            ("Collect from Reddit", "python main.py scrape <subreddit>"),
            ("Open a dataset someone shared", "python main.py import <file.zip>"),
        ])
        return EXIT_OK
    rows = []
    for path, manifest in found:
        counts = manifest.get("counts", {})
        status = manifest.get("status", "complete")
        kind = {"synthetic": "sample", "import": "imported"}.get(manifest.get("source"), "")
        note = ", ".join(part for part in (kind, "" if status == "complete" else status.replace("_", " ")) if part)
        rows.append((
            path.name,
            ", ".join(f"r/{name}" for name in manifest.get("subreddits", [])),
            f"{counts.get('posts', 0):,}",
            f"{counts.get('comments', 0):,}",
            (manifest.get("created_utc") or "")[:10],
            note,
        ))
    ui.table(f"Datasets in {_rel(root)}", ["Name", "Community", "Posts", "Comments", "Collected", "Note"], rows,
             right=("Posts", "Comments"))
    console.print()
    ui.hint("show, analyze, and export take a name or the part before the date (the newest match wins).")
    ui.hint("With no name they use the newest dataset.")
    return EXIT_OK


def cmd_show(args) -> int:
    path = _dataset_or_explain(args.dataset, args)
    if path is None:
        return EXIT_SETUP
    try:
        posts, comments, manifest = datasets.read_dataset(path)
    except ModuleNotFoundError as exc:
        return _report(exc, args)
    except datasets.DatasetError as exc:
        ui.fail(e(exc))
        return EXIT_ERROR

    ui.heading(f"Dataset {path.name}")
    if manifest.get("source") == "synthetic":
        ui.hint("Synthetic practice data. Every row is invented.")
    status = manifest.get("status", "complete")
    if status != "complete":
        ui.warn(f"This dataset is partial (collection {status.replace('_', ' ')}).")
    for problem in datasets.verify(path):
        ui.warn(e(problem))
    console.print()
    rows = _summary_rows(manifest)
    query = {key: value for key, value in (manifest.get("query") or {}).items() if value is not None}
    if query:
        rows.append(("Query", ", ".join(f"{key}={value}" for key, value in query.items())))
    rows.append(("Folder", _rel(path)))
    ui.table(None, ["", ""], rows)

    if len(posts):
        console.print()
        top = posts.sort_values("score", ascending=False).head(args.rows)
        preview = [
            (
                (str(row.title)[:58] + "...") if len(str(row.title)) > 61 else str(row.title),
                str(row.author),
                f"{int(row.score):,}",
                f"{int(row.num_comments):,}",
                row.created_utc.strftime("%Y-%m-%d") if hasattr(row.created_utc, "strftime") and str(row.created_utc) != "NaT" else "",
            )
            for row in top.itertuples()
        ]
        ui.table(f"Top {len(preview)} posts by score", ["Title", "Author", "Score", "Comments", "Date"], preview,
                 right=("Score", "Comments"))
        if "flair" in posts.columns and posts["flair"].notna().any():
            console.print()
            flair = posts["flair"].fillna("(none)").value_counts().head(6)
            ui.table("Most used flairs", ["Flair", "Posts"], [(name, f"{count:,}") for name, count in flair.items()], right=("Posts",))
    _print_dataset_next_steps(path, include_show=False)
    return EXIT_OK


def cmd_export(args) -> int:
    path = _dataset_or_explain(args.dataset, args)
    if path is None:
        return EXIT_SETUP
    try:
        target = datasets.export_zip(path, Path(args.output).expanduser() if args.output else None)
    except (datasets.DatasetError, OSError) as exc:
        ui.fail(e(exc))
        return EXIT_ERROR
    ui.ok(f"Wrote [path]{e(_rel(target))}[/path] ({datasets.human_size(target.stat().st_size)})")
    ui.next_steps("Use the zip", [
        (f"Explore it in the dashboard: open {DASHBOARD_URL}, choose 'Open a dataset', and upload the zip", None),
        ("A classmate can open it in their copy of the toolkit", f"python main.py import {target.name}"),
    ])
    if datasets.load_manifest(path).get("source") != "synthetic":
        console.print()
        ui.hint("This is real people's writing, and Reddit's terms restrict passing it on. Share it inside your "
                "course or research team only, and never post it publicly.")
    return EXIT_OK


def cmd_import(args) -> int:
    root = datasets.data_root(args.data_dir)
    sources = [Path(item).expanduser() for item in args.files]
    try:
        if len(sources) == 1 and sources[0].suffix.lower() == ".zip":
            path = datasets.import_zip(sources[0], root)
        elif all(source.suffix.lower() == ".csv" for source in sources) and len(sources) <= 2:
            posts_csv = sources[0]
            comments_csv = sources[1] if len(sources) == 2 else None
            if comments_csv and "comment" in posts_csv.name.lower() and "comment" not in comments_csv.name.lower():
                posts_csv, comments_csv = comments_csv, posts_csv
            path = datasets.import_csvs(posts_csv, comments_csv, root, label=args.name)
        else:
            ui.fail("Import takes one .zip bundle, or a posts .csv optionally followed by a comments .csv.")
            ui.command("python main.py import shared-dataset.zip")
            ui.command("python main.py import output/CUNY_posts_20250101_120000.csv output/CUNY_comments_20250101_120000.csv")
            return EXIT_SETUP
    except datasets.DatasetError as exc:
        ui.fail(e(exc))
        return EXIT_ERROR
    manifest = datasets.load_manifest(path)
    ui.ok(f"Imported as [path]{e(_rel(path))}[/path]")
    console.print()
    ui.table(None, ["", ""], _summary_rows(manifest))
    _print_dataset_next_steps(path)
    return EXIT_OK


def cmd_analyze(args) -> int:
    path = _dataset_or_explain(args.dataset, args)
    if path is None:
        return EXIT_SETUP

    import importlib.util
    missing = [name for name in ("plotly", "numpy", "pandas") if importlib.util.find_spec(name) is None]
    if missing:
        ui.error_panel(
            "The analysis packages are not installed",
            f"The analyze command draws charts with packages that are an optional install. Missing: {', '.join(missing)}.",
            ["Install them once: [cmd]python -m pip install -r requirements-analysis.txt[/cmd]",
             "Then run the same command again."],
        )
        return EXIT_SETUP

    import logging
    import warnings
    logging.getLogger().setLevel(logging.ERROR)  # the analyzers announce optional packages with warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # numeric edge cases in small networks

    from rrt.bridge import build_database

    wanted = [name for name in ("temporal", "text", "network") if getattr(args, name)] or ["temporal", "text", "network"]
    manifest = datasets.load_manifest(path)
    counts = manifest.get("counts", {})
    reports = path / "reports"

    ui.heading(f"Analyzing {path.name}")
    with console.status("Preparing the data ..."):
        db_path = build_database(path)

    produced: List[tuple] = []
    failures = 0
    for name in wanted:
        if name == "network" and not counts.get("comments"):
            ui.warn("Network analysis skipped: this dataset has no comments, so there are no interactions to map.")
            continue
        try:
            with console.status(f"Running {name} analysis ..."):
                report = _run_analyzer(name, db_path, reports / name)
            ui.ok(f"{name.capitalize()} analysis")
            produced.append((name, report))
        except ModuleNotFoundError as exc:
            ui.warn(f"{name.capitalize()} analysis skipped: the package '{e(getattr(exc, 'name', '?'))}' is not installed. "
                    "Run [cmd]python -m pip install -r requirements-analysis.txt[/cmd]")
        except Exception as exc:
            failures += 1
            ui.fail(f"{name.capitalize()} analysis failed: {e(type(exc).__name__)}: {e(exc)}")
            if args.debug:
                traceback.print_exception(type(exc), exc, exc.__traceback__)
    try:
        db_path.unlink()
    except OSError:
        pass

    if not produced:
        ui.info("\nNo reports were produced." + ("" if args.debug else " Add --debug for the full errors."))
        return EXIT_ERROR

    console.print()
    ui.table("Reports (open these in a browser)", ["", ""], [(name, _rel(Path(report))) for name, report in produced if report])
    console.print()
    ui.hint(f"Charts and data files for each analysis are in {e(_rel(reports))}")
    if "text" in wanted:
        import importlib.util as _spec
        if _spec.find_spec("nltk") is None or _spec.find_spec("sklearn") is None:
            ui.hint("Text analysis ran in basic mode. For sentiment and topic modeling: python -m pip install nltk scikit-learn textblob")
    if args.open and produced:
        webbrowser.open(Path(produced[0][1]).resolve().as_uri())
    else:
        ui.hint("Add --open to open the first report in your browser.")
    return EXIT_ERROR if failures else EXIT_OK


def _run_analyzer(name: str, db_path: Path, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    if name == "temporal":
        from analyzers.temporal_analyzer import TemporalAnalyzer
        return TemporalAnalyzer(str(db_path), str(output_dir)).generate_comprehensive_report()["files"]["html_report"]
    if name == "text":
        from analyzers.text_analyzer import TextAnalyzer
        return TextAnalyzer(str(db_path), str(output_dir)).analyze_text_comprehensively()["files"]["html_report"]
    from analyzers.network_analyzer import NetworkAnalyzer
    return NetworkAnalyzer(str(db_path), str(output_dir)).generate_comprehensive_analysis()["files"]["html_report"]


def cmd_access(args) -> int:
    ui.note_panel("Reddit API access", _access_summary())
    console.print()
    console.print(f"Reddit for Researchers: {RESEARCHERS_URL}")
    return EXIT_OK


def cmd_setup(args) -> int:
    ui.note_panel("Reddit API access", _access_summary())
    if not ui.interactive():
        console.print()
        ui.info("Setup asks questions, so it needs an interactive terminal. To set credentials without it, copy "
                ".env.example to .env and fill in the three values.")
        return EXIT_SETUP

    current = credentials.load()
    console.print()
    if current.present:
        ui.info(f"Credentials are already saved ({current.source}).")
        choice = Prompt.ask("Test them, replace them, or quit?", choices=["test", "replace", "quit"], default="test")
        if choice == "quit":
            return EXIT_OK
        if choice == "test":
            return _test_and_report(args)
    else:
        has = Confirm.ask("Do you have a Reddit client ID and secret?", default=False)
        if not has:
            ui.next_steps("You can still do the coursework", [
                ("Make a practice dataset and start analyzing", "python main.py sample"),
                ("Open a dataset someone shared with you", "python main.py import <file.zip>"),
                (f"Researchers at a university can apply to Reddit for Researchers: {RESEARCHERS_URL}", None),
            ])
            return EXIT_OK

    ui.heading("Where the two values are")
    console.print("  1. Sign in to Reddit and open https://www.reddit.com/prefs/apps")
    console.print("  2. Find your app in the list. The [head]client ID[/head] is the short string under its name.")
    console.print("  3. Click [head]edit[/head]. The [head]secret[/head] is the longer string labelled 'secret'.")
    console.print()
    try:
        client_id = Prompt.ask("Client ID").strip()
        client_secret = Prompt.ask("Client secret (hidden as you type or paste)", password=True).strip()
        username = Prompt.ask("Your Reddit username (Reddit asks every app to name its owner)", default="", show_default=False).strip()
    except (KeyboardInterrupt, EOFError):
        ui.info("\nSetup cancelled. Nothing was saved.")
        return EXIT_INTERRUPTED
    if not client_id or not client_secret:
        ui.fail("Both the client ID and the secret are required. Nothing was saved.")
        return EXIT_SETUP

    env_path = credentials.save(client_id, client_secret, credentials.default_user_agent(username))
    ui.ok(f"Saved to [path]{e(_rel(env_path))}[/path]. Git ignores this file. Treat the secret like a password.")
    return _test_and_report(args)


def _test_and_report(args) -> int:
    creds = credentials.load()
    for problem in credentials.problems(creds):
        ui.warn(e(problem))
    try:
        with console.status("Testing the connection to Reddit ..."):
            result = credentials.check_connection(creds)
    except ModuleNotFoundError as exc:
        return _report(exc, args)
    if result.ok:
        ui.ok("Reddit accepted the credentials and served a public post. You are ready to collect.")
        ui.next_steps("Try it", [("Collect 25 posts with their comments", "python main.py scrape AskHistorians --limit 25")])
        return EXIT_OK
    if result.stage == "config":
        return _no_credentials(credentials.problems(creds))
    if result.stage == "read" and explain(result.error).code == "forbidden":
        ui.error_panel(
            "Reddit accepted the client ID and secret, then refused to serve data",
            "The sign-in worked, and a request for one public post came back 'forbidden' (HTTP 403). "
            "Reddit serves data to approved apps only, and this is the response an app receives when "
            "Reddit has not approved it or has withdrawn its access.",
            [
                f"Read [path]{ACCESS_DOC}[/path] for who can still collect and the registration deadline.",
                "If Reddit approved this app, confirm you copied the ID and secret of that app and not another one.",
                "You can still do the analysis work with sample or shared data: [cmd]python main.py sample[/cmd]",
            ],
            f"{type(result.error).__name__}: {result.error}",
        )
        return EXIT_ERROR
    return _report(result.error, args)


def cmd_check(args) -> int:
    ui.heading(f"Reddit Research Toolkit {__version__} setup check")
    console.print()
    with console.status("Checking ..."):
        checks = doctor.run_all(args.data_dir, online=not args.offline)
    marks = {
        doctor.PASS: f"[ok]{ui.MARK_OK}[/ok]",
        doctor.WARN: f"[warn]{ui.MARK_WARN}[/warn]",
        doctor.FAIL: f"[fail]{ui.MARK_FAIL}[/fail]",
        doctor.SKIP: "[hint]-[/hint]",
    }
    for check in checks:
        console.print(f" {marks[check.status]} [head]{e(check.name)}[/head]  {e(check.detail)}")
        if check.fix and check.status != doctor.PASS:
            console.print(f"     [hint]{ui.ARROW}[/hint] [cmd]{e(check.fix)}[/cmd]")
    failed = [check for check in checks if check.status == doctor.FAIL]
    credentials_ready = any(check.name == "Connection to Reddit" and check.status == doctor.PASS for check in checks)
    console.print()
    if failed:
        ui.fail(f"{len(failed)} thing(s) to fix. Each has its fix on the line beneath it.")
        return EXIT_ERROR
    if credentials_ready:
        ui.ok("Everything works. Collect with: [cmd]python main.py scrape <subreddit>[/cmd]")
    else:
        ui.ok("The toolkit is installed correctly. You can analyze sample and shared data now:")
        ui.command("python main.py sample")
        if args.offline:
            ui.hint("The live connection test was skipped (--offline).")
    return EXIT_OK


# ==========================================================================
# Guided menu
# ==========================================================================

def guided(args) -> int:
    console.print()
    console.print(f"[head]Reddit Research Toolkit[/head] [hint]{__version__}[/hint]")
    creds = credentials.load()
    has_credentials = creds.present and not [p for p in credentials.problems(creds) if "may be swapped" not in p]
    count = len(datasets.list_datasets(datasets.data_root(args.data_dir)))
    ui.hint(f"Credentials: {'saved' if has_credentials else 'not set up'}    Datasets: {count}")

    options = [
        ("1", "Collect posts from a subreddit" + ("" if has_credentials else "  [hint](needs Reddit credentials)[/hint]")),
        ("2", "Make a practice dataset  [hint](no credentials needed)[/hint]"),
        ("3", "Open a dataset someone shared with me"),
        ("4", "See my datasets"),
        ("5", "Analyze a dataset"),
        ("6", "Set up or test Reddit credentials"),
        ("7", "Check my setup"),
        ("q", "Quit"),
    ]
    console.print()
    for key, label in options:
        console.print(f"  [cmd]{key}[/cmd]  {label}")
    console.print()
    try:
        choice = Prompt.ask("Choose", choices=[key for key, _ in options], default="2" if not has_credentials and count == 0 else "4" if not has_credentials else "1")
        if choice == "q":
            return EXIT_OK
        if choice == "1":
            return _guided_scrape(args)
        if choice == "2":
            return _echo_and_run("python main.py sample", cmd_sample, _ns(args, posts=300, seed=42))
        if choice == "3":
            location = Prompt.ask("Path to the .zip file (drag the file into this window to paste its path)").strip().strip("'\"")
            return _echo_and_run(f"python main.py import {location}", cmd_import, _ns(args, files=[location], name=None))
        if choice == "4":
            return _echo_and_run("python main.py list", cmd_list, args)
        if choice == "5":
            return _echo_and_run("python main.py analyze", cmd_analyze,
                                 _ns(args, dataset=None, temporal=False, text=False, network=False, open=True))
        if choice == "6":
            return cmd_setup(args)
        return _echo_and_run("python main.py check", cmd_check, _ns(args, offline=False))
    except (KeyboardInterrupt, EOFError):
        console.print()
        return EXIT_INTERRUPTED


def _ns(args, **extra) -> argparse.Namespace:
    values = {"debug": args.debug, "data_dir": args.data_dir}
    values.update(extra)
    return argparse.Namespace(**values)


def _echo_and_run(command_line: str, func, namespace) -> int:
    """Show the one-line command behind a menu choice, then run it."""
    console.print()
    ui.hint("The same thing without the menu:")
    ui.command(command_line)
    console.print()
    return func(namespace)


def _guided_scrape(args) -> int:
    creds = credentials.load()
    if not creds.present:
        return _no_credentials(credentials.problems(creds))
    console.print()
    subreddit = None
    while subreddit is None:
        subreddit = _clean_or_explain(Prompt.ask("Which subreddit? (name, r/name, or its web address)"))
    limit = IntPrompt.ask("How many posts?", default=100)
    sort = Prompt.ask("In what order?", choices=["hot", "new", "top", "rising"], default="hot")
    time_filter = "all"
    if sort == "top":
        time_filter = Prompt.ask("Top of which period?", choices=["hour", "day", "week", "month", "year", "all"], default="month")
    console.print("  [cmd]all[/cmd]    every comment in every thread (complete, slowest)")
    console.print("  [cmd]quick[/cmd]  the comments Reddit sends with each thread (faster, may miss deep replies)")
    console.print("  [cmd]none[/cmd]   posts only (fastest)")
    comments_mode = Prompt.ask("Comments?", choices=["all", "quick", "none"], default="quick")

    command_line = f"python main.py scrape {subreddit} --limit {limit} --sort {sort}"
    if sort == "top":
        command_line += f" -t {time_filter}"
    command_line += f" --comments {comments_mode}"
    namespace = _ns(args, subreddit=subreddit, limit=max(1, limit), sort=sort, time_filter=time_filter,
                    comments=comments_mode, no_comments=False, format="csv", info=False, yes=False)
    return _echo_and_run(command_line, cmd_scrape, namespace)


# ==========================================================================
# Argument parsing
# ==========================================================================

EPILOG = """\
first steps:
  python main.py check              is everything installed?
  python main.py sample             make a practice dataset, no credentials needed
  python main.py show               look at the newest dataset
  python main.py analyze --open     chart it and open the report

collecting from Reddit (needs credentials, see 'python main.py access'):
  python main.py setup              save and test your client ID and secret
  python main.py scrape CUNY        100 hot posts from r/CUNY with all comments
  python main.py scrape CUNY -l 500 --sort top -t year --comments quick

sharing:
  python main.py export             zip the newest dataset for a classmate or the dashboard
  python main.py import shared.zip  open a dataset someone sent you
"""


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--debug", action="store_true", help="show full technical errors")
    common.add_argument("--data-dir", metavar="FOLDER", default=None, help="where datasets live (default: data/)")

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Reddit Research Toolkit: collect Reddit posts and comments into tidy dataset folders, then analyze them.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"reddit-research-toolkit {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    scrape = sub.add_parser("scrape", parents=[common], help="collect posts and comments from a subreddit",
                            description="Collect posts, and their comments, from one subreddit into a new dataset folder.")
    scrape.add_argument("subreddit", help="subreddit name, with or without r/")
    scrape.add_argument("-l", "--limit", type=int, default=100, help="maximum number of posts (default: 100; Reddit serves about 1000 per sort)")
    scrape.add_argument("--sort", choices=["hot", "new", "top", "rising"], default="hot", help="which posts to take (default: hot)")
    scrape.add_argument("-t", "--time-filter", choices=["hour", "day", "week", "month", "year", "all"], default="all",
                        help="period for --sort top (default: all)")
    scrape.add_argument("--comments", choices=["all", "quick", "none"], default="all",
                        help="all = every comment (default, slowest); quick = comments sent with each thread; none = posts only")
    scrape.add_argument("--no-comments", action="store_true", help="same as --comments none")
    scrape.add_argument("-f", "--format", choices=["csv", "json", "both"], default="csv",
                        help="csv files are always written; json or both adds data.json")
    scrape.add_argument("-y", "--yes", action="store_true", help="do not ask before a long run")
    scrape.add_argument("--info", action="store_true", help="show facts about the subreddit and stop")
    scrape.set_defaults(func=cmd_scrape)

    info = sub.add_parser("info", parents=[common], help="show facts about a subreddit")
    info.add_argument("subreddit")
    info.set_defaults(func=cmd_info)

    sample = sub.add_parser("sample", parents=[common], help="make a synthetic practice dataset (no credentials needed)")
    sample.add_argument("--posts", type=int, default=300, help="number of posts to invent (default: 300)")
    sample.add_argument("--seed", type=int, default=42, help="same seed, same data (default: 42)")
    sample.set_defaults(func=cmd_sample)

    listing = sub.add_parser("list", parents=[common], help="list your datasets")
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", parents=[common], help="summarize a dataset and preview its rows")
    show.add_argument("dataset", nargs="?", help="dataset name or its first letters (default: newest)")
    show.add_argument("--rows", type=int, default=5, help="how many posts to preview (default: 5)")
    show.set_defaults(func=cmd_show)

    export = sub.add_parser("export", parents=[common], help="zip a dataset for sharing or for the dashboard")
    export.add_argument("dataset", nargs="?", help="dataset name (default: newest)")
    export.add_argument("-o", "--output", help="zip file or folder to write to")
    export.set_defaults(func=cmd_export)

    importer = sub.add_parser("import", parents=[common], help="open a shared dataset zip, or wrap loose CSV files",
                              description="Import one dataset .zip, or a posts .csv optionally followed by a comments .csv.")
    importer.add_argument("files", nargs="+", metavar="file")
    importer.add_argument("--name", help="label for a CSV import (default: taken from the file)")
    importer.set_defaults(func=cmd_import)

    analyze = sub.add_parser("analyze", parents=[common], help="chart a dataset: activity over time, words, interactions")
    analyze.add_argument("dataset", nargs="?", help="dataset name (default: newest)")
    analyze.add_argument("--temporal", action="store_true", help="only the activity-over-time analysis")
    analyze.add_argument("--text", action="store_true", help="only the text analysis")
    analyze.add_argument("--network", action="store_true", help="only the interaction network analysis")
    analyze.add_argument("--open", action="store_true", help="open the first report in your browser when done")
    analyze.set_defaults(func=cmd_analyze)

    setup = sub.add_parser("setup", parents=[common], help="save and test Reddit credentials")
    setup.set_defaults(func=cmd_setup)

    check = sub.add_parser("check", parents=[common], help="test your setup and say what to fix")
    check.add_argument("--offline", action="store_true", help="skip the live connection test")
    check.set_defaults(func=cmd_check)

    access = sub.add_parser("access", parents=[common], help="who can get Reddit API credentials today")
    access.set_defaults(func=cmd_access)

    helper = sub.add_parser("help", parents=[common], help="show this help")
    helper.set_defaults(func=lambda _args: (parser.print_help(), EXIT_OK)[1])
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Older form: 'python main.py CUNY -l 500'. Anything that is not a command
    # or an option is read as a subreddit to scrape.
    for index, item in enumerate(argv):
        if item.startswith("-") or (index > 0 and argv[index - 1] == "--data-dir"):
            continue
        if item not in COMMANDS:
            argv.insert(index, "scrape")
        break

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        if ui.interactive():
            return guided(args)
        parser.print_help()
        return EXIT_OK

    try:
        return args.func(args) or EXIT_OK
    except KeyboardInterrupt:
        console.print("\nStopped.")
        return EXIT_INTERRUPTED
    except Exception as exc:  # last line of defence: no raw traceback for a first-time user
        return _report(exc, args)


if __name__ == "__main__":
    sys.exit(main())
