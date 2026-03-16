#!/usr/bin/env python3
"""
Reddit Scraper - Main scraping module for subreddit data collection
"""

import praw
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import time
from ratelimit import limits, sleep_and_retry
import os
import json
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedditScraper:
    """Main Reddit scraper class for collecting subreddit data"""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """
        Initialize Reddit scraper with API credentials

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string for API requests
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)

        logger.info("Reddit scraper initialized successfully")

    @sleep_and_retry
    @limits(calls=60, period=60)  # Rate limit: 60 calls per minute
    def scrape_subreddit_posts(
        self,
        subreddit_name: str,
        limit: int = 100,
        time_filter: str = 'week',
        sort_by: str = 'hot'
    ) -> List[Dict[str, Any]]:
        """
        Scrape posts from a specific subreddit

        Args:
            subreddit_name: Name of the subreddit to scrape
            limit: Maximum number of posts to retrieve
            time_filter: Time filter for posts ('all', 'day', 'week', 'month', 'year')
            sort_by: Sort method ('hot', 'new', 'top', 'rising')

        Returns:
            List of post dictionaries
        """
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts_data = []

            logger.info(f"Scraping r/{subreddit_name} - {sort_by} posts (limit: {limit})")

            # Get posts based on sort method
            if sort_by == 'hot':
                posts = subreddit.hot(limit=limit)
            elif sort_by == 'new':
                posts = subreddit.new(limit=limit)
            elif sort_by == 'top':
                posts = subreddit.top(time_filter=time_filter, limit=limit)
            elif sort_by == 'rising':
                posts = subreddit.rising(limit=limit)
            else:
                posts = subreddit.hot(limit=limit)

            for post in posts:
                post_data = {
                    'id': post.id,
                    'title': post.title,
                    'author': str(post.author) if post.author else '[deleted]',
                    'created_utc': datetime.fromtimestamp(post.created_utc),
                    'score': post.score,
                    'upvote_ratio': post.upvote_ratio,
                    'num_comments': post.num_comments,
                    'permalink': f"https://reddit.com{post.permalink}",
                    'url': post.url,
                    'selftext': post.selftext,
                    'subreddit': subreddit_name,
                    'is_video': post.is_video,
                    'is_original_content': post.is_original_content,
                    'over_18': post.over_18,
                    'spoiler': post.spoiler,
                    'stickied': post.stickied,
                    'locked': post.locked,
                    'distinguished': post.distinguished,
                    'link_flair_text': post.link_flair_text,
                    'scraped_at': datetime.now()
                }
                posts_data.append(post_data)

            logger.info(f"Successfully scraped {len(posts_data)} posts from r/{subreddit_name}")
            return posts_data

        except Exception as e:
            logger.error(f"Error scraping r/{subreddit_name}: {str(e)}")
            return []

    @sleep_and_retry
    @limits(calls=60, period=60)
    def scrape_post_comments(
        self,
        post_id: str,
        limit: Optional[int] = None,
        depth: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Scrape comments from a specific post

        Args:
            post_id: Reddit post ID
            limit: Maximum number of comments to retrieve (None for all)
            depth: Maximum depth of comment tree to traverse

        Returns:
            List of comment dictionaries
        """
        try:
            submission = self.reddit.submission(id=post_id)
            submission.comments.replace_more(limit=limit)

            comments_data = []

            def extract_comment_data(comment, parent_id=None, level=0):
                """Recursively extract comment data"""
                if level > depth:
                    return

                comment_data = {
                    'id': comment.id,
                    'post_id': post_id,
                    'parent_id': parent_id,
                    'author': str(comment.author) if comment.author else '[deleted]',
                    'body': comment.body,
                    'score': comment.score,
                    'created_utc': datetime.fromtimestamp(comment.created_utc),
                    'edited': comment.edited,
                    'is_submitter': comment.is_submitter,
                    'stickied': comment.stickied,
                    'distinguished': comment.distinguished,
                    'level': level,
                    'permalink': f"https://reddit.com{comment.permalink}",
                    'scraped_at': datetime.now()
                }
                comments_data.append(comment_data)

                # Process replies
                for reply in comment.replies:
                    extract_comment_data(reply, comment.id, level + 1)

            # Extract all comments
            for comment in submission.comments:
                extract_comment_data(comment)

            logger.info(f"Successfully scraped {len(comments_data)} comments from post {post_id}")
            return comments_data

        except Exception as e:
            logger.error(f"Error scraping comments for post {post_id}: {str(e)}")
            return []

    @sleep_and_retry
    @limits(calls=60, period=60)
    def scrape_subreddit_info(self, subreddit_name: str) -> Dict[str, Any]:
        """
        Scrape metadata about a subreddit

        Args:
            subreddit_name: Name of the subreddit

        Returns:
            Dictionary containing subreddit information
        """
        try:
            subreddit = self.reddit.subreddit(subreddit_name)

            info = {
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.public_description,
                'subscribers': subreddit.subscribers,
                'created_utc': datetime.fromtimestamp(subreddit.created_utc),
                'over18': subreddit.over18,
                'lang': subreddit.lang,
                'subreddit_type': subreddit.subreddit_type,
                'submission_type': subreddit.submission_type,
                'allow_images': subreddit.allow_images,
                'allow_videos': subreddit.allow_videos,
                'spoilers_enabled': subreddit.spoilers_enabled,
                'scraped_at': datetime.now()
            }

            logger.info(f"Successfully scraped info for r/{subreddit_name}")
            return info

        except Exception as e:
            logger.error(f"Error scraping subreddit info for r/{subreddit_name}: {str(e)}")
            return {}

    def scrape_user_posts(
        self,
        username: str,
        limit: int = 100,
        time_filter: str = 'all'
    ) -> List[Dict[str, Any]]:
        """
        Scrape posts from a specific user

        Args:
            username: Reddit username
            limit: Maximum number of posts to retrieve
            time_filter: Time filter for posts

        Returns:
            List of post dictionaries
        """
        try:
            user = self.reddit.redditor(username)
            posts_data = []

            logger.info(f"Scraping posts from user u/{username}")

            for submission in user.submissions.new(limit=limit):
                post_data = {
                    'id': submission.id,
                    'title': submission.title,
                    'author': username,
                    'created_utc': datetime.fromtimestamp(submission.created_utc),
                    'score': submission.score,
                    'upvote_ratio': submission.upvote_ratio,
                    'num_comments': submission.num_comments,
                    'permalink': f"https://reddit.com{submission.permalink}",
                    'url': submission.url,
                    'selftext': submission.selftext,
                    'subreddit': str(submission.subreddit),
                    'scraped_at': datetime.now()
                }
                posts_data.append(post_data)

            logger.info(f"Successfully scraped {len(posts_data)} posts from u/{username}")
            return posts_data

        except Exception as e:
            logger.error(f"Error scraping user posts for u/{username}: {str(e)}")
            return []

    def save_to_csv(self, data: List[Dict], filename: str, subfolder: str = ""):
        """
        Save scraped data to CSV file

        Args:
            data: List of dictionaries to save
            filename: Output filename (without extension)
            subfolder: Optional subfolder in data directory
        """
        if not data:
            logger.warning("No data to save")
            return

        # Create subfolder if specified
        save_dir = self.data_dir / subfolder if subfolder else self.data_dir
        save_dir.mkdir(exist_ok=True)

        # Save to CSV
        df = pd.DataFrame(data)
        filepath = save_dir / f"{filename}.csv"
        df.to_csv(filepath, index=False)
        logger.info(f"Data saved to {filepath}")

    def save_to_json(self, data: List[Dict], filename: str, subfolder: str = ""):
        """
        Save scraped data to JSON file

        Args:
            data: List of dictionaries to save
            filename: Output filename (without extension)
            subfolder: Optional subfolder in data directory
        """
        if not data:
            logger.warning("No data to save")
            return

        # Create subfolder if specified
        save_dir = self.data_dir / subfolder if subfolder else self.data_dir
        save_dir.mkdir(exist_ok=True)

        # Convert datetime objects to strings for JSON serialization
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # Save to JSON
        filepath = save_dir / f"{filename}.json"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=json_serializer)
        logger.info(f"Data saved to {filepath}")

    def bulk_scrape_subreddits(
        self,
        subreddit_names: List[str],
        limit: int = 100,
        save_format: str = 'csv'
    ):
        """
        Scrape multiple subreddits and save data

        Args:
            subreddit_names: List of subreddit names to scrape
            limit: Maximum posts per subreddit
            save_format: Output format ('csv' or 'json')
        """
        all_posts = []

        for subreddit_name in subreddit_names:
            logger.info(f"Processing r/{subreddit_name}...")

            # Scrape posts
            posts = self.scrape_subreddit_posts(subreddit_name, limit=limit)
            all_posts.extend(posts)

            # Save individual subreddit data
            if save_format == 'csv':
                self.save_to_csv(posts, f"{subreddit_name}_posts", "subreddits")
            else:
                self.save_to_json(posts, f"{subreddit_name}_posts", "subreddits")

            # Add delay between subreddits
            time.sleep(2)

        # Save combined data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_format == 'csv':
            self.save_to_csv(all_posts, f"all_posts_{timestamp}")
        else:
            self.save_to_json(all_posts, f"all_posts_{timestamp}")

        logger.info(f"Completed scraping {len(subreddit_names)} subreddits")


if __name__ == "__main__":
    # Example usage (requires API credentials)
    # Load credentials from environment or config file
    from dotenv import load_dotenv
    load_dotenv()

    CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "your_client_id")
    CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "your_client_secret")
    USER_AGENT = os.getenv("REDDIT_USER_AGENT", "RedditScraper/1.0")

    # Initialize scraper
    scraper = RedditScraper(CLIENT_ID, CLIENT_SECRET, USER_AGENT)

    # Example: Scrape a single subreddit
    # posts = scraper.scrape_subreddit_posts("python", limit=10)
    # scraper.save_to_csv(posts, "python_posts")

    # Example: Scrape multiple subreddits
    # subreddits = ["python", "datascience", "machinelearning"]
    # scraper.bulk_scrape_subreddits(subreddits, limit=50)