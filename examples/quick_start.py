#!/usr/bin/env python3
"""
Quick Start Example

Runs the toolkit's first steps from Python, with no Reddit credentials:
create the synthetic practice dataset, load it with pandas, and print a few
facts. Every row in the practice dataset is invented.

    python examples/quick_start.py
"""

import sys
from pathlib import Path

# Make the toolkit importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rrt import datasets, sample


def main():
    # 1. Reuse the practice dataset if it exists, otherwise create it.
    existing = [path for path, manifest in datasets.list_datasets() if manifest.get("source") == "synthetic"]
    folder = existing[0] if existing else sample.write_sample()
    print(f"Practice dataset: {folder}")

    # 2. Load it. Timestamps come back as UTC date-times.
    posts, comments, manifest = datasets.read_dataset(folder)
    print(f"{len(posts):,} posts and {len(comments):,} comments from r/{manifest['subreddits'][0]}")

    # 3. Ask a few questions of the data.
    local = posts["created_utc"].dt.tz_convert("America/New_York")
    print("\nPosts by flair")
    print(posts["flair"].value_counts().to_string())
    print("\nBusiest hours (US Eastern)")
    print(local.dt.hour.value_counts().head(5).sort_index().to_string())
    print("\nMost discussed posts")
    print(posts.nlargest(5, "num_comments")[["title", "num_comments", "score"]].to_string(index=False))

    # 4. Thread structure: how deep do conversations go?
    print("\nComments by depth (0 = reply to the post)")
    print(comments["depth"].value_counts().sort_index().to_string())

    print("\nNext steps")
    print("  python main.py show              summary in the terminal")
    print("  python main.py analyze --open    charts and reports in your browser")
    print("  python main.py scrape <name>     collect a real community (needs credentials)")


if __name__ == "__main__":
    main()
