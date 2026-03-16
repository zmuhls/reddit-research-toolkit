#!/usr/bin/env python3
"""
Simple Reddit Scraper
Scrapes all posts and comments from a subreddit and saves to CSV/JSON
"""

import praw
import pandas as pd
import logging
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from tqdm import tqdm
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleRedditScraper:
    """Simple scraper to collect all posts and comments from a subreddit"""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """
        Initialize the scraper with Reddit API credentials

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        logger.info("Reddit scraper initialized")

    def scrape_subreddit(
        self,
        subreddit_name: str,
        post_limit: int = 1000,
        sort_by: str = 'hot',
        time_filter: str = 'all',
        include_comments: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scrape all posts and optionally comments from a subreddit

        Args:
            subreddit_name: Name of the subreddit (without r/)
            post_limit: Maximum number of posts to scrape (None for all available)
            sort_by: How to sort posts ('hot', 'new', 'top', 'rising')
            time_filter: Time filter for 'top' sort ('hour', 'day', 'week', 'month', 'year', 'all')
            include_comments: Whether to scrape comments from each post

        Returns:
            Dictionary with 'posts' and 'comments' lists
        """
        logger.info(f"Starting scrape of r/{subreddit_name}")
        subreddit = self.reddit.subreddit(subreddit_name)

        # Get posts based on sort method
        logger.info(f"Fetching {sort_by} posts (limit: {post_limit})")
        if sort_by == 'hot':
            posts = subreddit.hot(limit=post_limit)
        elif sort_by == 'new':
            posts = subreddit.new(limit=post_limit)
        elif sort_by == 'top':
            posts = subreddit.top(time_filter=time_filter, limit=post_limit)
        elif sort_by == 'rising':
            posts = subreddit.rising(limit=post_limit)
        else:
            posts = subreddit.hot(limit=post_limit)

        posts_data = []
        comments_data = []

        # Scrape posts
        for post in tqdm(posts, desc="Scraping posts", unit="post"):
            post_dict = {
                'post_id': post.id,
                'title': post.title,
                'author': str(post.author) if post.author else '[deleted]',
                'created_utc': datetime.fromtimestamp(post.created_utc).isoformat(),
                'score': post.score,
                'upvote_ratio': post.upvote_ratio,
                'num_comments': post.num_comments,
                'permalink': f"https://reddit.com{post.permalink}",
                'url': post.url,
                'selftext': post.selftext,
                'is_self': post.is_self,
                'is_video': post.is_video,
                'over_18': post.over_18,
                'spoiler': post.spoiler,
                'stickied': post.stickied,
                'flair': post.link_flair_text,
                'domain': post.domain if hasattr(post, 'domain') else None,
            }
            posts_data.append(post_dict)

            # Scrape comments if requested
            if include_comments and post.num_comments > 0:
                post_comments = self._scrape_post_comments(post)
                comments_data.extend(post_comments)

        logger.info(f"Scraped {len(posts_data)} posts and {len(comments_data)} comments")
        return {'posts': posts_data, 'comments': comments_data}

    def _scrape_post_comments(self, submission) -> List[Dict[str, Any]]:
        """
        Scrape all comments from a single post

        Args:
            submission: PRAW submission object

        Returns:
            List of comment dictionaries
        """
        comments_data = []

        try:
            # Replace "MoreComments" objects to get all comments
            submission.comments.replace_more(limit=None)

            def extract_comment(comment, depth=0):
                """Recursively extract comment data"""
                if not hasattr(comment, 'body'):
                    return

                comment_dict = {
                    'comment_id': comment.id,
                    'post_id': submission.id,
                    'parent_id': comment.parent_id,
                    'author': str(comment.author) if comment.author else '[deleted]',
                    'body': comment.body,
                    'score': comment.score,
                    'created_utc': datetime.fromtimestamp(comment.created_utc).isoformat(),
                    'edited': bool(comment.edited),
                    'is_submitter': comment.is_submitter,
                    'stickied': comment.stickied,
                    'depth': depth,
                    'permalink': f"https://reddit.com{comment.permalink}",
                }
                comments_data.append(comment_dict)

                # Process replies recursively
                if hasattr(comment, 'replies'):
                    for reply in comment.replies:
                        extract_comment(reply, depth + 1)

            # Extract all top-level comments and their replies
            for comment in submission.comments:
                extract_comment(comment)

        except Exception as e:
            logger.warning(f"Error scraping comments from post {submission.id}: {e}")

        return comments_data

    def save_to_csv(self, data: Dict[str, List[Dict]], subreddit_name: str):
        """
        Save scraped data to CSV files

        Args:
            data: Dictionary with 'posts' and 'comments' lists
            subreddit_name: Name of the subreddit (for filename)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save posts
        if data['posts']:
            posts_df = pd.DataFrame(data['posts'])
            posts_file = self.output_dir / f"{subreddit_name}_posts_{timestamp}.csv"
            posts_df.to_csv(posts_file, index=False, encoding='utf-8')
            logger.info(f"Posts saved to {posts_file}")

        # Save comments
        if data['comments']:
            comments_df = pd.DataFrame(data['comments'])
            comments_file = self.output_dir / f"{subreddit_name}_comments_{timestamp}.csv"
            comments_df.to_csv(comments_file, index=False, encoding='utf-8')
            logger.info(f"Comments saved to {comments_file}")

    def save_to_json(self, data: Dict[str, List[Dict]], subreddit_name: str):
        """
        Save scraped data to JSON file

        Args:
            data: Dictionary with 'posts' and 'comments' lists
            subreddit_name: Name of the subreddit (for filename)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.output_dir / f"{subreddit_name}_data_{timestamp}.json"

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Data saved to {json_file}")

    def get_subreddit_info(self, subreddit_name: str) -> Dict[str, Any]:
        """
        Get basic information about a subreddit

        Args:
            subreddit_name: Name of the subreddit

        Returns:
            Dictionary with subreddit metadata
        """
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            info = {
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.public_description,
                'subscribers': subreddit.subscribers,
                'created_utc': datetime.fromtimestamp(subreddit.created_utc).isoformat(),
                'over18': subreddit.over18,
                'subreddit_type': subreddit.subreddit_type,
            }
            return info
        except Exception as e:
            logger.error(f"Error getting subreddit info: {e}")
            return {}
