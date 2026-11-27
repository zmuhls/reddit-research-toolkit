# Reddit Research Toolkit

Collect posts and comments from Reddit communities into tidy dataset folders, then explore them in the terminal, in pandas or R, or in the [companion dashboard](https://huggingface.co/spaces/milwright/reddit-dashboard).

The toolkit serves students who are new to the terminal. Every command explains its results, names the next step, and reports problems in plain language.

> **Reddit API access changed in 2026.** Reddit accepts no new API requests as of October 31, 2026 and ends public API access in March 2027. Existing approved credentials still work until then. You can do all the analysis in this toolkit without credentials, using the built-in sample or a dataset someone shares with you. [docs/REDDIT_API_ACCESS.md](docs/REDDIT_API_ACCESS.md) explains each route.

## Contents

- [Install](#install)
- [First run, no credentials needed](#first-run-no-credentials-needed)
- [Collect from Reddit](#collect-from-reddit)
- [Your datasets](#your-datasets)
- [Commands](#commands)
- [Troubleshooting](#troubleshooting)
- [Advanced collection](#advanced-collection)
- [Responsible use](#responsible-use)

## Install

You need Python 3.10 or newer. Check your version first.

| macOS or Linux | Windows |
|---|---|
| `python3 --version` | `py --version` |

If the command fails or shows an older version, install Python from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** in the installer.

**1. Download the toolkit.** With Git, run `git clone https://github.com/zmuhls/reddit-research-toolkit.git`. Without Git, click **Code > Download ZIP** on the GitHub page and unzip the file.

**2. Open a terminal in the toolkit folder.**

```bash
cd reddit-research-toolkit
```

**3. Create a private Python environment and install the packages.** Run these lines one at a time.

macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows (PowerShell or Command Prompt)

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Your prompt now begins with `(.venv)`. Each time you open a new terminal window, return to the toolkit folder and run the `activate` line again.

**4. Check the setup.**

```bash
python main.py check
```

```
 ✓ Python version  3.13.1
 ✓ Virtual environment  active (/Users/you/reddit-research-toolkit/.venv)
 ✓ Core packages  praw 8.0.3, pandas 3.1.1, rich 15.0.0, PyYAML 6.0.4, python-dotenv 1.2.4
 ! Analysis packages (optional)  missing: plotly, numpy, networkx
     → python -m pip install -r requirements-analysis.txt
 ✓ Data folder  /Users/you/reddit-research-toolkit/data (0 datasets)
 - Reddit credentials  not set up (only needed to collect new data)
 - Connection to Reddit  skipped, no usable credentials

✓ The toolkit is installed correctly. You can analyze sample and shared data now:
    python main.py sample
```

A line marked ✗ prints its fix directly beneath it.

## First run, no credentials needed

The toolkit ships a generator for a synthetic practice dataset. A program invents every post, comment, and username, and the data has the shape of a real community, with an evening peak, a weekly rhythm, and nested comment threads.

```bash
python main.py sample            # create the practice dataset
python main.py show              # summary, top posts, most used flairs
python main.py analyze --open    # charts and reports, opened in your browser
```

The `analyze` command needs the optional charting packages. Install them once with `python -m pip install -r requirements-analysis.txt`.

To work with the data in Python, start a notebook or script in the toolkit folder.

```python
import pandas as pd

posts = pd.read_csv("data/sample_20261127-141502/posts.csv", parse_dates=["created_utc"])
comments = pd.read_csv("data/sample_20261127-141502/comments.csv", parse_dates=["created_utc"])

posts["flair"].value_counts().plot(kind="bar")
```

Replace the folder name with yours. `python main.py list` prints it.

Prefer menus? Run `python main.py` with nothing after it. The guided menu asks questions, runs the matching command, and shows the one-line command so you can skip the menu next time.

## Collect from Reddit

Collection requires a Reddit client ID and secret that Reddit has approved. Read [docs/REDDIT_API_ACCESS.md](docs/REDDIT_API_ACCESS.md) to see whether you qualify. Students in a course usually work from a dataset their instructor shares (see [Your datasets](#your-datasets)).

**1. Save and test your credentials.**

```bash
python main.py setup
```

Setup shows where to find the two values, hides the secret as you paste it, writes a private `.env` file, and tests the connection with a real request.

**2. Collect.**

```bash
python main.py scrape CUNY
```

The output has this shape. Your numbers will differ.

```
✓ Found r/CUNY

Plan
Posts           up to 100 (hot)
Comments        every comment
Estimated time  1 min 42 sec to 10 min

⠹ Collecting ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  100/100 posts  1,208 comments 0:02:51

✓ Done. Saved to data/cuny_20261127-141502
```

You can paste a name in any form, such as `CUNY`, `r/CUNY`, or the community's web address.

**Options**

| Option | Meaning | Default |
|---|---|---|
| `-l`, `--limit N` | Maximum number of posts. Reddit serves about 1,000 per sort order. | 100 |
| `--sort hot\|new\|top\|rising` | Which posts to take | hot |
| `-t`, `--time-filter hour\|day\|week\|month\|year\|all` | Period for `--sort top` | all |
| `--comments all\|quick\|none` | `all` follows every "load more comments" link. `quick` takes the comments Reddit sends with each thread, at one request per post. `none` collects posts only. | all |
| `-f`, `--format csv\|json\|both` | CSV files are always written. `json` or `both` adds `data.json`. | csv |
| `-y`, `--yes` | Start long runs without a confirmation prompt | |

```bash
python main.py scrape CUNY --limit 500 --sort top -t year --comments quick
python main.py scrape AskHistorians --sort new --comments none
python main.py info CUNY                     # facts about a community, nothing collected
```

**Run time.** Reddit serves roughly one request per second. Posts alone take seconds. Comments add at least one request per post, and long threads add more. The plan printed before each run shows an estimate.

**Stop any time.** Press Ctrl+C. The toolkit saves the rows collected so far and marks the dataset as partial. A rate limit or a dropped connection in mid-run has the same result.

## Your datasets

Each scrape produces one self-contained folder.

```
data/
└── cuny_20261127-141502/
    ├── posts.csv        one row per post
    ├── comments.csv     one row per comment
    ├── manifest.json    the collection record (community, options, counts, dates, checksums)
    └── README.md        a codebook that explains every column and shows how to load the files
```

All timestamps are UTC. [docs/DATASET_FORMAT.md](docs/DATASET_FORMAT.md) lists every column.

```bash
python main.py list                 # every dataset, newest first
python main.py show cuny            # the newest CUNY dataset
python main.py export cuny          # one .zip for a classmate or the dashboard
python main.py import shared.zip    # open a dataset someone sent you
```

**The dashboard.** Open <https://huggingface.co/spaces/milwright/reddit-dashboard>, choose **Open a dataset**, and upload an exported `.zip`. The dashboard charts activity over time, engagement, and comment threads in the browser, with nothing to install.

**Files from older versions.** Earlier releases wrote loose files such as `output/CUNY_posts_20250101_120000.csv`. Wrap them as a dataset folder with `python main.py import output/CUNY_posts_….csv output/CUNY_comments_….csv`.

## Commands

| Command | Purpose | Credentials |
|---|---|---|
| `python main.py` | Guided menu | |
| `python main.py check` | Test the setup and print fixes | |
| `python main.py sample` | Create the synthetic practice dataset | |
| `python main.py list` | List datasets | |
| `python main.py show [name]` | Summarize a dataset | |
| `python main.py analyze [name]` | Charts and reports on activity, text, and interaction networks | |
| `python main.py export [name]` | Zip a dataset | |
| `python main.py import <file>` | Open a shared zip, or wrap CSV files | |
| `python main.py access` | Current rules for Reddit API access | |
| `python main.py setup` | Save and test credentials | needed |
| `python main.py scrape <subreddit>` | Collect posts and comments | needed |
| `python main.py info <subreddit>` | Facts about a community | needed |

Add `--help` to any command for its options, `--debug` for full technical errors, and `--data-dir FOLDER` to store datasets elsewhere.

The older form `python main.py CUNY -l 500` still works. To scrape a community whose name matches a command, such as r/help, write `python main.py scrape help`.

## Troubleshooting

**`python: command not found`, or Windows opens the Microsoft Store.** Use `python3` on macOS and Linux, and `py` on Windows, until the environment is active. Inside an active environment, `python` always works.

**"The toolkit's packages are not installed in this Python environment."** The environment is not active in this window. Run `source .venv/bin/activate` (macOS, Linux) or `.venv\Scripts\activate` (Windows) from the toolkit folder, then retry.

**PowerShell reports "running scripts is disabled on this system."** Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then run the `activate` line again. The change lasts for that window only.

**`pip install` prints pages of compiler errors.** An old requirements file pinned package versions that have no ready-made build for current Python. Update the toolkit, then run `python -m pip install --upgrade pip` and `python -m pip install -r requirements.txt` again.

**"Reddit credentials are not set up."** Run `python main.py setup`. If you edited `.env` by hand, confirm the file is named exactly `.env` and not `.env.txt`.

**"Reddit did not accept these credentials," or Reddit "refused to serve data."** [docs/REDDIT_API_ACCESS.md](docs/REDDIT_API_ACCESS.md#error-messages-and-their-meaning) lists each message with its cause.

**A scrape runs for a very long time.** Press Ctrl+C. Your rows are saved. Run again with a smaller `--limit` or with `--comments quick`.

**A spreadsheet app shows garbled characters.** Import the CSV as UTF-8. In Excel, use **Data > From Text/CSV** and choose **65001: Unicode (UTF-8)**.

**Anything else.** Add `--debug` to the command and include the output in a [GitHub issue](https://github.com/zmuhls/reddit-research-toolkit/issues).

## Advanced collection

`tools/cli.py` builds a deeper archive of a community by following its participants. It discovers the accounts active in a subreddit, then gathers each account's posts and comments there. It runs for hours on a large community, resumes after interruption, and stores everything in one folder, `data/<name>_archive/`.

```bash
python -m pip install -r requirements-analysis.txt
python tools/cli.py scrape  --subreddit CUNY --max-users 200
python tools/cli.py status  --subreddit CUNY
python tools/cli.py analyze --subreddit CUNY --all
python tools/cli.py export  --subreddit CUNY        # a dataset folder for pandas or the dashboard
```

[docs/ADVANCED.md](docs/ADVANCED.md) covers the method, run times, and config files.

## Responsible use

- The rows are public posts by real people. Report patterns, quote sparingly, and leave usernames out of papers, slides, and screenshots.
- Reddit's terms restrict redistribution of its data. Share datasets inside your course or research team, and never post them publicly.
- When someone deletes a post or comment on Reddit, delete it from your copy.
- Treat your client secret as a password. Share datasets, never credentials.
- Research with human subjects data may require review by your institution's IRB. Ask before you collect.

## Project layout

```
reddit-research-toolkit/
├── main.py                  the command line described above
├── simple_scraper.py        listing-based collection (used by main.py, importable in notebooks)
├── rrt/                     terminal output, credentials, dataset folders, sample data, plain-language errors
├── tools/cli.py             advanced CLI for user-centric archives
├── core/                    user-centric scraper (SQLite, checkpoints)
├── analyzers/               temporal, text, and network analysis
├── config/                  config loading, validation, and YAML templates
├── scripts/                 shell wrappers for the advanced CLI
├── examples/                full pipelines that run on synthetic data
├── docs/                    API access, dataset format, advanced collection
├── tests/                   test suite with a stand-in for Reddit (no network, no credentials)
├── requirements.txt         core packages
└── requirements-analysis.txt   optional packages for charts and text analysis
```

Run the tests with `python -m pip install -r requirements-dev.txt` followed by `python -m pytest`.

## Upgrading from an earlier version

- Scrapes now land in `data/<community>_<date>-<time>/` in place of loose files in `output/`.
- `created_utc` now holds true UTC. Earlier versions stored the collecting computer's local time under that name.
- The default `--limit` is 100, down from 1,000, so a first run finishes in minutes. Pass `--limit 1000` for the previous behavior.
- `pip install -r requirements.txt` works on current Python releases again. `config/requirements.txt` moved to `requirements-analysis.txt`.
- `OPTIMIZATION_GUIDE.md` became [docs/ADVANCED.md](docs/ADVANCED.md).

## Citation

```bibtex
@software{reddit_research_toolkit,
  title={Reddit Research Toolkit: Comprehensive Social Media Data Collection and Analysis},
  author={zmuhls},
  year={2024},
  url={https://github.com/zmuhls/reddit-research-toolkit}
}
```

## License and acknowledgments

MIT License. See [LICENSE](LICENSE).

Built on [PRAW](https://praw.readthedocs.io/), [pandas](https://pandas.pydata.org/), [Rich](https://rich.readthedocs.io/), [NetworkX](https://networkx.org/), [NLTK](https://www.nltk.org/), [scikit-learn](https://scikit-learn.org/), and [Plotly](https://plotly.com/python/).
