"""Friendly command-line layer for the Reddit Research Toolkit.

Everything a first-time user touches lives here: plain-language errors,
credential setup, the dataset folder format, and the sample data generator.
The collection engines stay where they were (simple_scraper.py and core/).
"""

from pathlib import Path

__version__ = "1.1.0"

# The folder that holds main.py. Paths such as .env and data/ hang off this so
# the toolkit behaves the same no matter which folder the terminal is in.
REPO_ROOT = Path(__file__).resolve().parent.parent
