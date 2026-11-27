# Advanced collection: user-centric archives

`python main.py scrape` reads a subreddit's listings, and Reddit caps each listing at roughly 1,000 posts. The advanced CLI in `tools/cli.py` reaches further back with a different method.

1. **Discover.** It scans the hot, new, top, and rising listings and records the accounts that wrote those posts and the top-level comments beneath them.
2. **Process.** For each account it reads that person's recent history and stores the posts and comments made in the target community.

The result is an archive of a community as seen through its participants. Coverage follows the users, so the archive includes older threads that no listing still shows, and it omits threads whose participants were never discovered. State that sampling method wherever you report results.

You need working Reddit credentials (see [REDDIT_API_ACCESS.md](REDDIT_API_ACCESS.md)) and the analysis packages.

```bash
python -m pip install -r requirements-analysis.txt
python main.py setup
```

## Commands

```bash
# Start an archive. Begin small to see how long one user takes.
python tools/cli.py scrape --subreddit CUNY --max-users 200

# Check progress at any time, from a second terminal if you like
python tools/cli.py status --subreddit CUNY

# Continue after stopping
python tools/cli.py scrape --subreddit CUNY --process-only

# Charts and reports
python tools/cli.py analyze --subreddit CUNY --all

# A dataset folder for pandas, R, or the dashboard
python tools/cli.py export --subreddit CUNY
```

The shell wrappers in `scripts/` run the same commands from any folder and use the toolkit's virtual environment without activation.

```bash
./scripts/scrape.sh CUNY
./scripts/resume.sh CUNY --max-users 500
./scripts/analyze.sh --all data/cuny_archive/cuny.db
```

## Files

Everything for one community sits in `data/<name>_archive/`. [DATASET_FORMAT.md](DATASET_FORMAT.md#archives-from-the-advanced-cli) describes the folder. An archive that an earlier toolkit version created under `databases/` continues to work in place, and the CLI says so when it resumes one.

## Stopping and resuming

Press Ctrl+C once. The scraper finishes the current user, saves a checkpoint, and exits. Run the same command again, or add `--process-only` to skip discovery, and it continues with the users still pending.

The archive's `scrape.log` records every user processed. Watch it with `tail -f data/cuny_archive/scrape.log`.

## Run time

Reddit serves about 100 requests a minute to one set of credentials. Each user costs a handful of requests, since the scraper reads up to 200 of their recent posts and up to 1,000 of their recent comments. Plan on a few seconds per user and several hours for a community with thousands of participants.

| Approach | Effect |
|---|---|
| `--max-users 1000` | Processes a sample of the discovered users. The fastest route to a usable archive. |
| `--discover-only` first | Shows how many users a community has before you commit to processing them. |
| `--time-filter year` | Narrows the top listing during discovery to recent activity. |
| One process per set of credentials | Two scrapers sharing credentials split the same rate limit and both slow down. |

The per-user caps of 200 posts and 1,000 comments hold run time down, at the cost of older activity from the most prolific accounts. To change them, edit `_process_single_user` in `core/reddit_scraper.py` and note the change in your methods.

## Config files

Flags cover most uses. For a study with fixed settings, write them to a file.

```bash
python tools/cli.py config --template academic --subreddit CUNY --output cuny.yaml
python tools/cli.py config --validate --config-file cuny.yaml
python tools/cli.py scrape --config cuny.yaml
```

Leave the credential lines in the file as placeholders. The CLI reads your client ID and secret from `.env`, so the config file stays safe to share and commit.

## From Python

```python
from config.config_manager import ConfigManager
from core.reddit_scraper import UniversalRedditScraper

config = ConfigManager().load_config("cuny.yaml")
scraper = UniversalRedditScraper(config)
scraper.discover_users_from_subreddit(limit=500)
scraper.process_users(batch_size=10, max_users=200)
print(scraper.get_stats())
```

`examples/academic_research_example.py` and `examples/comparative_study_example.py` run the full pipeline on synthetic data, with no credentials.
