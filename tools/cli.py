#!/usr/bin/env python3
"""
Advanced command line for the Reddit Research Toolkit

User-centric collection: discover the people active in a subreddit, then
gather each person's posts and comments in that subreddit. It reaches further
back than a listing does, runs for hours on a large community, and resumes
where it stopped.

New to the toolkit? Start with 'python main.py' instead.

    python tools/cli.py scrape  --subreddit CUNY --max-users 200
    python tools/cli.py status  --subreddit CUNY
    python tools/cli.py analyze --subreddit CUNY --all
    python tools/cli.py export  --subreddit CUNY
"""

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

# Make the repository root importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import rich  # noqa: F401
    import yaml  # noqa: F401
except ModuleNotFoundError as missing:
    print(
        f"The Python package '{missing.name}' is not installed in this environment.\n\n"
        "Activate the toolkit's virtual environment, then install its packages:\n\n"
        "  macOS / Linux: source .venv/bin/activate\n"
        "  Windows:       .venv\\Scripts\\activate\n"
        "  python -m pip install -r requirements-analysis.txt\n"
    )
    sys.exit(1)

from rrt import REPO_ROOT, credentials, datasets
from rrt import console as ui
from rrt.console import console, e
from rrt.errors import explain
from rrt.util import BadSubredditName, clean_subreddit_name

EXIT_OK, EXIT_ERROR, EXIT_SETUP, EXIT_INTERRUPTED = 0, 1, 2, 130


def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration."""
    level = getattr(logging, log_level.upper())
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    # Apply the level to the console handlers too. The archive's own log file
    # always records INFO, whatever the console shows.
    for handler in logging.getLogger().handlers:
        handler.setLevel(level)


# --------------------------------------------------------------------------
# Where an archive lives
# --------------------------------------------------------------------------

def archive_paths(subreddit: str) -> dict:
    """File locations for one subreddit's archive.

    Everything sits in one folder, data/<name>_archive/. A database from an
    earlier toolkit version (databases/<name>_data.db) is still honoured, so
    an interrupted scrape resumes in place.
    """
    base = subreddit.lower()
    for anchor in (Path.cwd(), REPO_ROOT):
        if (anchor / "databases" / f"{base}_data.db").exists():
            return {
                'database': str(anchor / "databases" / f"{base}_data.db"),
                'checkpoint': str(anchor / "checkpoints" / f"{base}_checkpoint.pkl"),
                'log': str(anchor / "logs" / f"{base}.log"),
                'output_dir': str(anchor / "output" / base),
                'layout': 'legacy',
            }
    root = datasets.data_root() / f"{base}_archive"
    return {
        'database': str(root / f"{base}.db"),
        'checkpoint': str(root / "checkpoint.pkl"),
        'log': str(root / "scrape.log"),
        'output_dir': str(root / "exports"),
        'layout': 'archive',
    }


def resolve_database(args):
    """Return (db_path, subreddit) from --database or --subreddit, or (None, None) after explaining."""
    if getattr(args, 'database', None):
        db_path = Path(args.database).expanduser()
        if not db_path.exists():
            ui.fail(f"No database at {e(db_path)}.")
            return None, None
        name = getattr(args, 'subreddit', None) or db_path.stem.replace('_data', '').replace('_historical', '')
        return db_path, name
    if getattr(args, 'subreddit', None):
        try:
            subreddit = clean_subreddit_name(args.subreddit)
        except BadSubredditName as exc:
            ui.fail(e(exc))
            return None, None
        db_path = Path(archive_paths(subreddit)['database'])
        if not db_path.exists():
            ui.fail(f"No archive for r/{e(subreddit)} yet (looked for {e(db_path)}).")
            ui.command(f"python tools/cli.py scrape --subreddit {subreddit}")
            return None, None
        return db_path, subreddit
    ui.fail("Name the archive with --subreddit NAME or --database PATH.")
    return None, None


def _report(exc, args, subreddit=None) -> int:
    friendly = explain(exc, subreddit)
    ui.error_panel(friendly.title, friendly.why, friendly.fixes, friendly.detail)
    if getattr(args, 'debug', False):
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    return EXIT_ERROR


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_scrape(args):
    """Execute scraping command."""
    from config.config_manager import ConfigManager

    config_manager = ConfigManager()

    if args.config:
        try:
            config = config_manager.load_config(args.config)
        except (FileNotFoundError, ValueError) as exc:
            ui.fail(e(exc))
            return EXIT_SETUP
        if args.subreddit:
            config['subreddit']['name'] = args.subreddit
    else:
        if not args.subreddit:
            ui.fail("Name a community with --subreddit NAME, or pass a config file with --config FILE.")
            return EXIT_SETUP
        try:
            subreddit = clean_subreddit_name(args.subreddit)
        except BadSubredditName as exc:
            ui.fail(e(exc))
            return EXIT_SETUP
        paths = archive_paths(subreddit)
        if paths.pop('layout') == 'legacy':
            ui.hint(f"Resuming the existing archive at {paths['database']}.")
        config = {
            'subreddit': {
                'name': subreddit,
                'display_name': f'r/{subreddit}'
            },
            'reddit': {
                'client_id': args.client_id or '',
                'client_secret': args.client_secret or '',
                'user_agent': args.user_agent or credentials.default_user_agent()
            },
            'paths': paths,
            'rate_limits': {
                'user_discovery': 0.5,
                'content_extraction': 0.05,
                'comment_expansion': 0.01,
                'batch_processing': 0.1,
                'rate_limit_backoff': 60.0
            },
            'scraping': {
                'batch_size': args.batch_size,
                'max_users': args.max_users,
                'max_posts_per_discovery': args.max_posts,
                'time_filter': args.time_filter,
                'resume_on_interrupt': True,
                'save_checkpoint_interval': 50
            },
            'analysis': {
                'temporal_analysis': True,
                'text_analysis': True,
                'network_analysis': True,
                'min_text_length': 10,
                'max_word_length': 20,
                'topic_modeling_topics': 10,
                'network_types': ['interaction', 'coparticipation']
            }
        }

    # Credentials, in order of precedence: command-line flags, then environment
    # variables and .env, then whatever the config file holds.
    saved = credentials.load()
    reddit_config = config.setdefault('reddit', {})
    flags = {'client_id': args.client_id, 'client_secret': args.client_secret, 'user_agent': args.user_agent}
    stored = {'client_id': saved.client_id, 'client_secret': saved.client_secret,
              'user_agent': saved.user_agent if saved.source != 'none' else ''}
    for key in flags:
        if flags[key]:
            reddit_config[key] = flags[key]
        elif stored[key]:
            reddit_config[key] = stored[key]

    usable = credentials.Credentials(reddit_config.get('client_id', ''), reddit_config.get('client_secret', ''),
                                     reddit_config.get('user_agent', ''), source='environment')
    if not usable.present or str(usable.client_id).upper().startswith('YOUR_'):
        ui.note_panel(
            "Reddit credentials are not set up",
            "Collecting from Reddit needs a client ID and secret.\n\n"
            "    [cmd]python main.py setup[/cmd]     saves them and tests the connection\n"
            "    [cmd]python main.py access[/cmd]    explains who can still get credentials",
        )
        return EXIT_SETUP

    subreddit_name = config['subreddit']['name']
    # One real request against the target community, before any folder is made.
    # A typo or revoked credentials stop here.
    with console.status(f"Checking r/{subreddit_name} ..."):
        test = credentials.check_connection(usable, subreddit=subreddit_name)
    if not test.ok:
        return _report(test.error, args, subreddit_name)

    created_dirs = config_manager.validate_paths(config)
    if created_dirs:
        ui.hint(f"Created: {', '.join(created_dirs)}")

    from core.reddit_scraper import UniversalRedditScraper

    scraper = UniversalRedditScraper(config)
    max_posts = args.max_posts
    batch_size = args.batch_size
    time_filter = args.time_filter

    ui.heading(f"Archiving r/{subreddit_name}")
    ui.table(None, ["", ""], [
        ("Database", config['paths']['database']),
        ("Log", config['paths'].get('log', '')),
        ("Users to process", "all discovered" if not args.max_users else f"up to {args.max_users:,}"),
    ])
    ui.hint("Press Ctrl+C once to stop cleanly. Progress is saved, and the same command resumes it.")
    console.print()

    try:
        if not args.process_only:
            discovered = scraper.discover_users_from_subreddit(limit=max_posts, time_filter=time_filter)
            ui.ok(f"Discovered {discovered:,} new users")
        if not args.discover_only:
            results = scraper.process_users(batch_size=batch_size, max_users=args.max_users)
            ui.ok(f"Processed users: {results.get('success', 0):,} done, {results.get('failed', 0):,} failed")
    except KeyboardInterrupt:
        ui.warn("Stopped. Progress is saved.")
    except Exception as exc:
        _report(exc, args, subreddit_name)
        ui.hint("Progress up to the error is saved. Run the same command to resume.")
        return EXIT_ERROR

    if args.export:
        if args.export_format == 'dataset':
            from rrt.bridge import database_to_dataset
            export_path = database_to_dataset(Path(config['paths']['database']), subreddit_name)
        else:
            export_path = scraper.export_data(format=args.export_format)
        ui.ok(f"Exported to {e(export_path)}")

    stats = scraper.get_stats()
    console.print()
    _print_status(stats.get('users', {}), stats.get('total_submissions', 0), stats.get('total_comments', 0),
                  stats.get('date_range'))
    ui.next_steps("Next", [
        ("Check progress at any time", f"python tools/cli.py status --subreddit {subreddit_name}"),
        ("Chart what you have", f"python tools/cli.py analyze --subreddit {subreddit_name} --all"),
        ("Turn it into a dataset folder for pandas or the dashboard", f"python tools/cli.py export --subreddit {subreddit_name}"),
    ])
    return EXIT_INTERRUPTED if scraper.shutdown_requested else EXIT_OK


def cmd_analyze(args):
    """Execute analysis command."""
    db_path, _name = resolve_database(args)
    if db_path is None:
        return EXIT_SETUP

    if args.output:
        output_dir = args.output
    elif db_path.parent.name.endswith('_archive'):
        output_dir = str(db_path.parent / 'reports')
    else:
        output_dir = f"output/{db_path.stem.replace('_data', '').replace('_historical_data', '')}"

    run_all = args.all or not (args.temporal or args.text or args.network)
    logging.getLogger().setLevel(logging.ERROR)
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # numeric edge cases in small networks
    results = {}
    failures = 0

    def run(label, func):
        nonlocal failures
        try:
            with console.status(f"Running {label} analysis ..."):
                outcome = func()
            results[label] = outcome
            ui.ok(f"{label.capitalize()} analysis: {e(outcome['files']['html_report'])}")
        except ModuleNotFoundError as exc:
            ui.warn(f"{label.capitalize()} analysis skipped, package '{e(exc.name)}' is missing. "
                    "Run: python -m pip install -r requirements-analysis.txt")
        except Exception as exc:
            failures += 1
            ui.fail(f"{label.capitalize()} analysis failed: {e(type(exc).__name__)}: {e(exc)}")
            if args.debug:
                traceback.print_exception(type(exc), exc, exc.__traceback__)

    if args.temporal or run_all:
        def temporal():
            from analyzers.temporal_analyzer import TemporalAnalyzer
            return TemporalAnalyzer(str(db_path), f"{output_dir}/temporal").generate_comprehensive_report(
                start_date=args.start_date, end_date=args.end_date)
        run('temporal', temporal)

    if args.text or run_all:
        def text():
            from analyzers.text_analyzer import TextAnalyzer
            return TextAnalyzer(str(db_path), f"{output_dir}/text").analyze_text_comprehensively(
                content_types=args.content_types, start_date=args.start_date, end_date=args.end_date)
        run('text', text)

    if args.network or run_all:
        def network():
            from analyzers.network_analyzer import NetworkAnalyzer
            return NetworkAnalyzer(str(db_path), f"{output_dir}/network").generate_comprehensive_analysis(
                network_types=args.network_types, start_date=args.start_date, end_date=args.end_date)
        run('network', network)

    if not results:
        ui.info("No reports were produced." + ("" if args.debug else " Add --debug for the full errors."))
        return EXIT_ERROR

    results_file = Path(output_dir) / "analysis_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    console.print()
    ui.ok(f"Open the .html reports above in a browser. Combined results: {e(results_file)}")
    return EXIT_ERROR if failures else EXIT_OK


def cmd_config(args):
    """Execute configuration command."""
    from config.config_manager import ConfigManager

    config_manager = ConfigManager()

    if args.create_templates:
        config_manager.create_default_templates()
        ui.ok("Default configuration templates created in config/templates/")
        return EXIT_OK

    if args.template and args.subreddit:
        config_path = config_manager.create_config_from_template(args.template, args.subreddit, args.output)
        ui.ok(f"Configuration created: {e(config_path)}")
        ui.hint("Leave the credential lines as they are. The toolkit reads your client ID and secret from .env.")
        return EXIT_OK

    if args.validate and args.config_file:
        try:
            config = config_manager.load_config(args.config_file)
        except Exception as exc:
            ui.fail(f"Configuration validation failed: {e(exc)}")
            return EXIT_ERROR
        ui.ok(f"Configuration is valid: {e(args.config_file)}")
        ui.table(None, ["", ""], [
            ("Subreddit", f"r/{config['subreddit']['name']}"),
            ("Research context", config.get('research_context', 'not specified')),
            ("Database", config['paths']['database']),
        ])
        return EXIT_OK

    if args.schema:
        schema_path = config_manager.export_config_schema(args.schema)
        ui.ok(f"Configuration schema exported to: {e(schema_path)}")
        return EXIT_OK

    ui.fail("Choose an action: --create-templates, --template with --subreddit, --validate with --config-file, or --schema.")
    return EXIT_SETUP


def _print_status(user_stats: dict, submissions: int, comments: int, date_range=None):
    total = sum(user_stats.values())
    done = user_stats.get('completed', 0)
    rows = [
        ("Users discovered", f"{total:,}"),
        ("Users processed", f"{done:,}" + (f" ({done / total:.0%})" if total else "")),
        ("Users pending", f"{user_stats.get('pending', 0):,}"),
        ("Users failed", f"{user_stats.get('failed', 0):,}"),
        ("Posts", f"{submissions:,}"),
        ("Comments", f"{comments:,}"),
    ]
    if date_range:
        rows.append(("Posts dated", f"{str(date_range.get('start', ''))[:10]} to {str(date_range.get('end', ''))[:10]}"))
    ui.table(None, ["", ""], rows)


def cmd_status(args):
    """Show status of scraping progress."""
    db_path, name = resolve_database(args)
    if db_path is None:
        return EXIT_SETUP

    import sqlite3
    from datetime import datetime, timezone

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM users GROUP BY status")
        user_stats = dict(cursor.fetchall())
        num_submissions = cursor.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        num_comments = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        low, high = cursor.execute(
            "SELECT MIN(created_utc), MAX(created_utc) FROM submissions WHERE created_utc IS NOT NULL").fetchone()

    date_range = None
    if low and high:
        date_range = {
            'start': datetime.fromtimestamp(low, tz=timezone.utc).strftime('%Y-%m-%d'),
            'end': datetime.fromtimestamp(high, tz=timezone.utc).strftime('%Y-%m-%d'),
        }
    ui.heading(f"Archive status: {name}")
    ui.hint(str(db_path))
    console.print()
    _print_status(user_stats, num_submissions, num_comments, date_range)
    if user_stats.get('pending'):
        console.print()
        ui.hint("To continue where it stopped, run the scrape command again with --process-only.")
    return EXIT_OK


def cmd_export(args):
    """Write a dataset folder (posts.csv, comments.csv, manifest, codebook) from an archive."""
    db_path, name = resolve_database(args)
    if db_path is None:
        return EXIT_SETUP
    from rrt.bridge import database_to_dataset

    with console.status("Exporting ..."):
        path = database_to_dataset(db_path, name)
    manifest = datasets.load_manifest(path)
    counts = manifest.get('counts', {})
    ui.ok(f"Wrote dataset {e(path)}")
    ui.table(None, ["", ""], [("Posts", f"{counts.get('posts', 0):,}"), ("Comments", f"{counts.get('comments', 0):,}")])
    ui.next_steps("Next", [
        ("Look at it", f"python main.py show {path.name}"),
        ("Zip it for the dashboard or a collaborator", f"python main.py export {path.name}"),
    ])
    return EXIT_OK


def main():
    """Main CLI entry point."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--debug', action='store_true', help='Show full technical errors')

    parser = argparse.ArgumentParser(
        description="Reddit Research Toolkit, advanced CLI: user-centric archives of a subreddit, with analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
        epilog="""
Examples:
  # Archive a subreddit (credentials come from .env; set them with: python main.py setup)
  python tools/cli.py scrape --subreddit MachineLearning --max-users 200

  # Resume after stopping
  python tools/cli.py scrape --subreddit MachineLearning --process-only

  # Check progress
  python tools/cli.py status --subreddit MachineLearning

  # Run every analysis
  python tools/cli.py analyze --subreddit MachineLearning --all

  # Export a dataset folder for pandas or the dashboard
  python tools/cli.py export --subreddit MachineLearning

New to the toolkit? Start with:  python main.py
        """
    )

    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='Set logging level')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', parents=[common], help='Archive a subreddit, user by user')
    scrape_parser.add_argument('--subreddit', help='Subreddit name (without r/)')
    scrape_parser.add_argument('--config', help='Configuration file path (optional; defaults are used without it)')
    scrape_parser.add_argument('--client-id', help='Reddit API client ID (default: from .env)')
    scrape_parser.add_argument('--client-secret', help='Reddit API client secret (default: from .env)')
    scrape_parser.add_argument('--user-agent', help='Reddit API user agent (default: from .env)')
    scrape_parser.add_argument('--max-posts', type=int, default=1000,
                               help='Posts to scan per listing when discovering users (default: 1000, the most Reddit serves)')
    scrape_parser.add_argument('--max-users', type=int, help='Maximum users to process (default: all discovered)')
    scrape_parser.add_argument('--batch-size', type=int, default=10, help='Users per checkpointed batch (default: 10)')
    scrape_parser.add_argument('--time-filter', choices=['hour', 'day', 'week', 'month', 'year', 'all'],
                               default='all', help='Time filter for post discovery (default: all)')
    scrape_parser.add_argument('--discover-only', action='store_true', help="Only discover users, don't process them")
    scrape_parser.add_argument('--process-only', action='store_true', help='Only process users already discovered (resume)')
    scrape_parser.add_argument('--export', action='store_true', help='Export data after scraping')
    scrape_parser.add_argument('--export-format', choices=['dataset', 'json', 'csv', 'jsonl'], default='dataset',
                               help='Export format (default: dataset folder)')

    def add_target(sub):
        sub.add_argument('--subreddit', help='Subreddit whose archive to use')
        sub.add_argument('--database', help='Database file path (alternative to --subreddit)')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', parents=[common], help='Analyze an archive')
    add_target(analyze_parser)
    analyze_parser.add_argument('--output', help='Output directory')
    analyze_parser.add_argument('--temporal', action='store_true', help='Run temporal analysis')
    analyze_parser.add_argument('--text', action='store_true', help='Run text analysis')
    analyze_parser.add_argument('--network', action='store_true', help='Run network analysis')
    analyze_parser.add_argument('--all', action='store_true', help='Run all analyses (the default when none is named)')
    analyze_parser.add_argument('--start-date', help='Start date for analysis (YYYY-MM-DD)')
    analyze_parser.add_argument('--end-date', help='End date for analysis (YYYY-MM-DD)')
    analyze_parser.add_argument('--content-types', nargs='+', choices=['submissions', 'comments'],
                                default=['submissions', 'comments'], help='Content types to analyze')
    analyze_parser.add_argument('--network-types', nargs='+',
                                choices=['interaction', 'coparticipation'],
                                default=['interaction', 'coparticipation'],
                                help='Network types to analyze')

    # Config command
    config_parser = subparsers.add_parser('config', parents=[common], help='Manage configurations')
    config_parser.add_argument('--create-templates', action='store_true',
                               help='Create default configuration templates')
    config_parser.add_argument('--template', choices=['academic', 'commercial', 'personal', 'comparative'],
                               help='Template to use for new configuration')
    config_parser.add_argument('--subreddit', help='Subreddit name for new configuration')
    config_parser.add_argument('--output', help='Output path for new configuration')
    config_parser.add_argument('--validate', action='store_true', help='Validate configuration file')
    config_parser.add_argument('--config-file', help='Configuration file to validate')
    config_parser.add_argument('--schema', help='Export configuration schema to file')

    # Status command
    status_parser = subparsers.add_parser('status', parents=[common], help='Check archive progress')
    add_target(status_parser)

    # Export command
    export_parser = subparsers.add_parser('export', parents=[common],
                                          help='Write a dataset folder from an archive (for pandas or the dashboard)')
    add_target(export_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return EXIT_SETUP

    setup_logging(args.log_level)
    handlers = {'scrape': cmd_scrape, 'analyze': cmd_analyze, 'config': cmd_config,
                'status': cmd_status, 'export': cmd_export}

    try:
        return handlers[args.command](args) or EXIT_OK
    except KeyboardInterrupt:
        console.print("\nStopped.")
        return EXIT_INTERRUPTED
    except Exception as exc:
        return _report(exc, args)


if __name__ == '__main__':
    sys.exit(main())
