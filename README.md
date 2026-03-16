# Reddit Research Toolkit

A straightforward tool to scrape entire subreddits, including all posts and comments, and save them to CSV or JSON files.

## Features

- Scrape posts from any subreddit
- Automatically scrape all comments from each post
- Export data to CSV or JSON format
- Simple command-line interface
- Progress bars to track scraping status
- Filter by time period and sort method

## Quick Start

### 1. Installation

```bash
# Clone or download this repository
cd reddit-scraper-toolkit

# Install dependencies
pip install -r requirements.txt
```

### 2. Get Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in the form:
   - **name**: Your app name (e.g., "My Scraper")
   - **App type**: Select "script"
   - **redirect uri**: http://localhost:8080 (required but not used)
4. Click "Create app"
5. Note your **client_id** (under the app name) and **client_secret**

### 3. Configure Credentials

Create a `.env` file in the project directory:

```bash
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=MyRedditScraper/1.0
```

### 4. Run the Scraper

```bash
# Scrape a subreddit (basic usage)
python main.py python

# Scrape with custom limit
python main.py python -l 500

# Scrape top posts from all time
python main.py python --sort top -t all

# Get subreddit info only
python main.py python --info
```

## Usage Examples

### Basic Scraping

```bash
# Scrape the first 1000 hot posts from r/python
python main.py python

# Scrape 500 posts
python main.py python -l 500

# Scrape without comments (faster)
python main.py python --no-comments
```

### Advanced Options

```bash
# Scrape top posts from the past year
python main.py MachineLearning --sort top -t year -l 1000

# Scrape new posts and save as JSON
python main.py technology --sort new -f json

# Save in both CSV and JSON formats
python main.py datascience -f both
```

### Get Subreddit Information

```bash
# Display info about a subreddit
python main.py python --info
```

## Command-Line Options

```
positional arguments:
  subreddit             Subreddit name to scrape (without r/)

optional arguments:
  -h, --help            Show help message
  -l, --limit LIMIT     Maximum number of posts to scrape (default: 1000)
  --sort {hot,new,top,rising}
                        How to sort posts (default: hot)
  -t, --time-filter {hour,day,week,month,year,all}
                        Time filter for "top" sort (default: all)
  -f, --format {csv,json,both}
                        Output format (default: csv)
  --no-comments         Skip scraping comments (posts only)
  --info                Display subreddit information and exit
```

## Output Files

The scraper creates an `output/` directory with the following files:

### CSV Format
- `{subreddit}_posts_{timestamp}.csv` - All post data
- `{subreddit}_comments_{timestamp}.csv` - All comment data

### JSON Format
- `{subreddit}_data_{timestamp}.json` - Combined posts and comments

### Data Fields

**Posts CSV/JSON includes:**
- post_id, title, author, created_utc
- score, upvote_ratio, num_comments
- permalink, url, selftext
- is_self, is_video, over_18, spoiler, stickied
- flair, domain

**Comments CSV/JSON includes:**
- comment_id, post_id, parent_id
- author, body, score
- created_utc, edited
- is_submitter, stickied, depth
- permalink

## Project Structure

```
reddit-research-toolkit/
├── main.py                    # Simple scraper entry point
├── simple_scraper.py          # Simple scraper (posts + comments → CSV/JSON)
├── requirements.txt           # Core dependencies
├── .env.example               # Example credentials (copy to .env)
├── config.yaml.example        # Example config (copy to config.yaml)
├── core/
│   └── reddit_scraper.py      # Universal scraper (user-centric, SQLite)
├── analyzers/
│   ├── temporal_analyzer.py   # Time-series analysis
│   ├── text_analyzer.py       # NLP / topic modeling
│   └── network_analyzer.py    # User interaction networks
├── tools/
│   └── cli.py                 # Full CLI for scrape/analyze/config/status
├── config/
│   ├── config_manager.py      # Config loading and validation
│   ├── requirements.txt       # Full dependency list (analysis features)
│   └── templates/             # YAML config templates
├── examples/                  # Usage examples
├── scripts/                   # Helper shell scripts
└── README.md
```

## Important Notes

- **Rate Limiting**: The scraper respects Reddit's API rate limits automatically
- **Reddit API Limits**: Reddit's API returns a maximum of ~1000 posts per request
- **Large Subreddits**: For very large subreddits, consider using filters (time period, sort method)
- **Comments**: Scraping comments can take longer; use `--no-comments` for faster posts-only scraping
- **Credentials**: Never commit your `.env` file with real credentials to version control

## Troubleshooting

### "Reddit API credentials not found"
Make sure you have a `.env` file with valid credentials. See step 3 in Quick Start.

### "403 Forbidden" or Rate Limit Errors
Reddit is rate limiting your requests. The scraper should handle this automatically, but you may need to wait a bit and try again.

### No Comments Scraped
Some posts may have deleted comments or the subreddit might not allow comments. Check the `num_comments` field in the posts data.

### Slow Scraping
Scraping comments can be time-consuming. Use `--no-comments` to only scrape posts, or reduce the `--limit` value.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built upon the excellent [PRAW (Python Reddit API Wrapper)](https://praw.readthedocs.io/)
- Network analysis powered by [NetworkX](https://networkx.org/)
- Text analysis using [NLTK](https://www.nltk.org/) and [scikit-learn](https://scikit-learn.org/)
- Visualizations created with [Plotly](https://plotly.com/python/)

## 📚 Academic Usage

### Citation

If you use this toolkit in academic research, please cite:

```bibtex
@software{reddit_research_toolkit,
  title={Reddit Research Toolkit: Comprehensive Social Media Data Collection and Analysis},
  author={zmuhls},
  year={2024},
  url={https://github.com/zmuhls/reddit-research-toolkit}
}
```

### Ethical Considerations

- **Respect Reddit's Terms of Service**: This toolkit is designed to work within Reddit's API guidelines
- **Rate Limiting**: Built-in delays prevent server overload
- **Data Privacy**: No personal information beyond usernames is collected
- **Academic Use**: Designed for research purposes with appropriate ethical oversight

### Research Applications

- **Digital Humanities**: Online community analysis, discourse studies
- **Computer Science**: Social network analysis, natural language processing
- **Psychology**: Online behavior patterns, community psychology
- **Marketing**: Consumer sentiment, brand analysis
- **Sociology**: Digital sociology, community formation studies

## 🔗 Related Projects

- [PRAW Documentation](https://praw.readthedocs.io/): Python Reddit API Wrapper
- [Reddit Research Tools](https://github.com/pushshift/api): Alternative Reddit data access
- [Social Network Analysis Papers](https://scholar.google.com/): Academic research using similar methodologies

## 📞 Support

- **Issues**: Report bugs and request features via [GitHub Issues](https://github.com/zmuhls/reddit-research-toolkit/issues)
- **Discussions**: Join conversations in [GitHub Discussions](https://github.com/zmuhls/reddit-research-toolkit/discussions)

---

**Happy scraping and analyzing! 🎉**

*Remember to always respect Reddit's terms of service and rate limits. This toolkit is designed for ethical research and analysis purposes.*