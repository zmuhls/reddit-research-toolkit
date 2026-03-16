#!/usr/bin/env python3
"""
Simple Reddit Scraper - Main Entry Point
Scrape entire subreddits including all posts and comments
"""

import argparse
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
import os

from simple_scraper import SimpleRedditScraper

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the simple Reddit scraper"""
    parser = argparse.ArgumentParser(
        description='Simple Reddit Scraper - Scrape entire subreddits with posts and comments'
    )

    # Required arguments
    parser.add_argument(
        'subreddit',
        help='Subreddit name to scrape (without r/)'
    )

    # Optional arguments
    parser.add_argument(
        '-l', '--limit',
        type=int,
        default=1000,
        help='Maximum number of posts to scrape (default: 1000)'
    )
    parser.add_argument(
        '--sort',
        choices=['hot', 'new', 'top', 'rising'],
        default='hot',
        help='How to sort posts (default: hot)'
    )
    parser.add_argument(
        '-t', '--time-filter',
        choices=['hour', 'day', 'week', 'month', 'year', 'all'],
        default='all',
        help='Time filter for "top" sort (default: all)'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['csv', 'json', 'both'],
        default='csv',
        help='Output format (default: csv)'
    )
    parser.add_argument(
        '--no-comments',
        action='store_true',
        help='Skip scraping comments (posts only)'
    )
    parser.add_argument(
        '--info',
        action='store_true',
        help='Display subreddit information and exit'
    )

    args = parser.parse_args()

    # Get Reddit API credentials from environment variables
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "SimpleRedditScraper/1.0")

    if not client_id or not client_secret:
        logger.error("Reddit API credentials not found!")
        logger.error("Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in your .env file")
        logger.error("\nExample .env file:")
        logger.error("REDDIT_CLIENT_ID=your_client_id_here")
        logger.error("REDDIT_CLIENT_SECRET=your_client_secret_here")
        logger.error("REDDIT_USER_AGENT=MyRedditScraper/1.0")
        sys.exit(1)

    try:
        # Initialize scraper
        scraper = SimpleRedditScraper(client_id, client_secret, user_agent)

        # If info flag is set, just show subreddit info and exit
        if args.info:
            info = scraper.get_subreddit_info(args.subreddit)
            if info:
                print(f"\n=== r/{args.subreddit} Information ===")
                print(f"Title: {info['title']}")
                print(f"Subscribers: {info['subscribers']:,}")
                print(f"Created: {info['created_utc']}")
                print(f"Type: {info['subreddit_type']}")
                print(f"NSFW: {info['over18']}")
                print(f"Description: {info['description'][:200]}...")
            return

        # Scrape the subreddit
        logger.info(f"Starting to scrape r/{args.subreddit}")
        data = scraper.scrape_subreddit(
            subreddit_name=args.subreddit,
            post_limit=args.limit,
            sort_by=args.sort,
            time_filter=args.time_filter,
            include_comments=not args.no_comments
        )

        # Save the data
        if args.format in ['csv', 'both']:
            scraper.save_to_csv(data, args.subreddit)

        if args.format in ['json', 'both']:
            scraper.save_to_json(data, args.subreddit)

        # Print summary
        print(f"\n=== Scraping Complete ===")
        print(f"Subreddit: r/{args.subreddit}")
        print(f"Posts scraped: {len(data['posts'])}")
        print(f"Comments scraped: {len(data['comments'])}")
        print(f"Output directory: output/")

    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()