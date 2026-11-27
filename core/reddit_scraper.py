#!/usr/bin/env python3
"""
Universal Reddit Scraper Core
A generalized, reusable Reddit scraping framework for academic research.
Uses user-centric methodology to bypass Reddit API limitations.
"""

import praw
import sqlite3
import json
import time
import os
import sys
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Set, Dict, List, Optional, Tuple, Any
import argparse
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from threading import Lock
import signal
import re

class UniversalRedditScraper:
    """
    A generalized Reddit scraper that can be configured for any subreddit
    or research use case. Uses user-centric methodology for comprehensive data collection.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the scraper with a configuration dictionary.

        Args:
            config: Dictionary containing Reddit API credentials, subreddit info,
                   output paths, and scraping parameters
        """
        # Reddit API setup
        self.reddit = praw.Reddit(
            client_id=config['reddit']['client_id'],
            client_secret=config['reddit']['client_secret'],
            user_agent=config['reddit']['user_agent']
        )

        # Subreddit configuration
        self.subreddit_name = self._validate_subreddit_name(config['subreddit']['name'])
        self.research_context = config.get('research_context', 'general')

        # File paths
        self.db_path = config['paths']['database']
        self.checkpoint_file = config['paths']['checkpoint']
        self.log_file = config['paths'].get('log', 'scraper.log')
        self.output_dir = config['paths'].get('output_dir') or '.'

        # Scraping parameters
        self.rate_limits = config.get('rate_limits', {
            'user_discovery': 1.0,
            'content_extraction': 1.5,
            'comment_expansion': 2.0,
            'batch_processing': 2.0,
            'rate_limit_backoff': 60.0
        })

        # Initialize tracking sets
        self.discovered_users: Set[str] = set()
        self.processed_users: Set[str] = set()
        self.failed_users: Set[str] = set()
        self.stats = defaultdict(int)

        # Thread safety
        self.db_lock = Lock()
        self.checkpoint_lock = Lock()

        # Setup logging
        self._setup_logging()

        # Initialize database and load checkpoint
        self._setup_database()
        self._load_checkpoint()

        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        self.shutdown_requested = False

        logger.info(f"Initialized scraper for r/{self.subreddit_name} in {self.research_context} context")

    def _setup_logging(self):
        """Log to the archive's log file, and to the console if nothing else does."""
        global logger
        logger = logging.getLogger("rrt.core")
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        log_dir = os.path.dirname(self.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.abspath(self.log_file)
        if not any(getattr(handler, 'baseFilename', None) == log_path for handler in logger.handlers):
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        # The CLI sets up console logging on the root logger. When this class is
        # used on its own (a notebook, a script), add a console handler here.
        if not logging.getLogger().handlers and not any(
                isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
                for handler in logger.handlers):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    def _validate_subreddit_name(self, name: str) -> str:
        """Validate and clean subreddit name."""
        name = re.sub(r'^r/', '', name.strip())

        if not name:
            raise ValueError("Subreddit name cannot be empty")
        if not re.match(r'^[A-Za-z0-9_]+$', name):
            raise ValueError(f"Invalid subreddit name: {name}")

        return name

    def _signal_handler(self, signum, frame):
        """Handle shutdown signal gracefully."""
        logger.info("Stop requested. Finishing the current user, then saving progress. "
                    "Run the same command again to resume.")
        self.shutdown_requested = True
        self._save_checkpoint()

    def _setup_database(self):
        """Initialize SQLite database with standard schema."""
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Users table for tracking discovery and processing
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    status TEXT CHECK(status IN ('pending', 'completed', 'failed')) DEFAULT 'pending',
                    discovered_at TEXT DEFAULT (datetime('now')),
                    processed_at TEXT,
                    discovery_source TEXT,
                    post_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    total_karma INTEGER DEFAULT 0,
                    account_created TEXT,
                    error_message TEXT,
                    last_attempt TEXT
                )
            ''')

            # Submissions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    selftext TEXT,
                    author TEXT,
                    created_utc INTEGER,
                    score INTEGER,
                    upvote_ratio REAL,
                    num_comments INTEGER,
                    permalink TEXT,
                    url TEXT,
                    domain TEXT,
                    flair_text TEXT,
                    is_self BOOLEAN,
                    stickied BOOLEAN,
                    locked BOOLEAN,
                    source_user TEXT,
                    collected_at TEXT DEFAULT (datetime('now'))
                )
            ''')

            # Comments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    body TEXT,
                    author TEXT,
                    created_utc INTEGER,
                    score INTEGER,
                    submission_id TEXT,
                    parent_id TEXT,
                    permalink TEXT,
                    is_submitter BOOLEAN,
                    stickied BOOLEAN,
                    source_user TEXT,
                    collected_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (submission_id) REFERENCES submissions(id)
                )
            ''')

            # User activity table for temporal analysis
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    username TEXT,
                    activity_date TEXT,
                    posts INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    total_score INTEGER DEFAULT 0,
                    PRIMARY KEY (username, activity_date),
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')

            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_submissions_author ON submissions(author)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_utc)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_submission ON comments(submission_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_utc)')

            conn.commit()

    def _load_checkpoint(self):
        """Load checkpoint data if it exists."""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'rb') as f:
                    checkpoint = pickle.load(f)
                    self.discovered_users = checkpoint.get('discovered_users', set())
                    self.processed_users = checkpoint.get('processed_users', set())
                    self.failed_users = checkpoint.get('failed_users', set())
                    self.stats = checkpoint.get('stats', defaultdict(int))
                    logger.info(f"Loaded checkpoint: {len(self.discovered_users)} discovered, "
                              f"{len(self.processed_users)} processed, {len(self.failed_users)} failed")
            except Exception as e:
                logger.error(f"Error loading checkpoint: {e}")

    def _save_checkpoint(self):
        """Save current progress to checkpoint file."""
        with self.checkpoint_lock:
            checkpoint = {
                'discovered_users': self.discovered_users,
                'processed_users': self.processed_users,
                'failed_users': self.failed_users,
                'stats': dict(self.stats),
                'timestamp': datetime.now().isoformat()
            }

            try:
                with open(self.checkpoint_file, 'wb') as f:
                    pickle.dump(checkpoint, f)
                logger.debug("Checkpoint saved")
            except Exception as e:
                logger.error(f"Error saving checkpoint: {e}")

    def discover_users_from_subreddit(self, limit: int = 1000, time_filter: str = 'all') -> int:
        """
        Discover users by scanning subreddit posts and comments.

        Args:
            limit: Maximum number of posts to scan
            time_filter: Time filter for posts ('hour', 'day', 'week', 'month', 'year', 'all')

        Returns:
            Number of new users discovered
        """
        initial_count = len(self.discovered_users)
        subreddit = self.reddit.subreddit(self.subreddit_name)

        logger.info(f"Starting user discovery from r/{self.subreddit_name}")

        try:
            # Scan various post categories
            post_sources = [
                ('hot', subreddit.hot(limit=min(limit, 1000))),
                ('new', subreddit.new(limit=min(limit, 1000))),
                ('top', subreddit.top(time_filter=time_filter, limit=min(limit, 1000))),
                ('rising', subreddit.rising(limit=min(limit, 1000)))
            ]

            for source_name, posts in post_sources:
                logger.info(f"Scanning {source_name} posts...")
                post_count = 0

                for post in posts:
                    if self.shutdown_requested:
                        break

                    post_count += 1
                    if post_count % 50 == 0:
                        logger.info(f"  Processed {post_count} {source_name} posts, discovered {len(self.discovered_users)} total users")
                        # Save checkpoint periodically during discovery
                        self._save_checkpoint()

                    # Add post author
                    if hasattr(post, 'author') and post.author:
                        self._add_discovered_user(post.author.name, f"{source_name}_post")

                    # Scan only already-loaded comments (no expansion to avoid hanging)
                    try:
                        # Don't call replace_more - just get what's already loaded
                        for comment in post.comments:
                            if hasattr(comment, 'author') and comment.author:
                                self._add_discovered_user(comment.author.name, f"{source_name}_comment")
                    except Exception as e:
                        logger.debug(f"Error scanning comments for post {post.id}: {e}")

                    time.sleep(0.5)  # Reduced from rate_limits to speed up discovery

                logger.info(f"  Completed {source_name}: {post_count} posts scanned")

                if self.shutdown_requested:
                    break

        except Exception as e:
            # Bad credentials, a missing or private community, or a failure
            # before anything was found: stop here so the caller can explain it.
            # A hiccup part-way through keeps the users found so far.
            from rrt.errors import explain
            problem = explain(e, self.subreddit_name)
            fatal = problem.code in ('bad-credentials', 'forbidden', 'no-such-subreddit', 'not-found', 'legal-block')
            if fatal or len(self.discovered_users) == initial_count:
                self._save_checkpoint()
                raise
            logger.error(f"User discovery stopped early ({problem.title}). Continuing with the users found so far.")

        new_users = len(self.discovered_users) - initial_count
        logger.info(f"Discovered {new_users} new users (total: {len(self.discovered_users)})")

        self._save_checkpoint()
        return new_users

    def _add_discovered_user(self, username: str, source: str):
        """Add a user to the discovered set and database."""
        if username and username not in ['[deleted]', 'AutoModerator']:
            if username not in self.discovered_users:
                self.discovered_users.add(username)

                with self.db_lock:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            'INSERT OR IGNORE INTO users (username, discovery_source) VALUES (?, ?)',
                            (username, source)
                        )
                        conn.commit()

    def process_users(self, batch_size: int = 10, max_users: Optional[int] = None) -> Dict[str, int]:
        """
        Process discovered users to extract their content.

        Args:
            batch_size: Number of users to process in each batch
            max_users: Maximum number of users to process (None for all)

        Returns:
            Statistics about processed users
        """
        pending_users = self.discovered_users - self.processed_users - self.failed_users

        if max_users:
            pending_users = list(pending_users)[:max_users]

        logger.info(f"Processing {len(pending_users)} users in batches of {batch_size}")

        results = {'success': 0, 'failed': 0, 'skipped': 0}

        for i in range(0, len(pending_users), batch_size):
            if self.shutdown_requested:
                break

            batch = list(pending_users)[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: users {i+1}-{min(i+batch_size, len(pending_users))}")

            for username in batch:
                if self.shutdown_requested:
                    break

                try:
                    success = self._process_single_user(username)
                    if success:
                        self.processed_users.add(username)
                        results['success'] += 1
                    else:
                        self.failed_users.add(username)
                        results['failed'] += 1

                except Exception as e:
                    logger.error(f"Error processing user {username}: {e}")
                    self.failed_users.add(username)
                    results['failed'] += 1

                # Minimal delay between users (removed excessive rate limiting)
                time.sleep(0.05)

            # Save checkpoint after each batch
            self._save_checkpoint()
            # Minimal delay between batches
            time.sleep(0.1)

        logger.info(f"User processing complete: {results}")
        return results

    def _process_single_user(self, username: str) -> bool:
        """
        Process a single user's content from the target subreddit.

        Args:
            username: Username to process

        Returns:
            True if successful, False otherwise
        """
        try:
            user = self.reddit.redditor(username)

            # Get user info
            try:
                user_created = datetime.fromtimestamp(user.created_utc).isoformat()
                total_karma = getattr(user, 'total_karma', 0)
            except:
                user_created = None
                total_karma = 0

            posts_collected = 0
            comments_collected = 0

            # Collect submissions from the target subreddit (limited to 200 most recent)
            try:
                for submission in user.submissions.new(limit=200):
                    if submission.subreddit.display_name.lower() == self.subreddit_name.lower():
                        self._store_submission(submission, username)
                        posts_collected += 1
                    # Removed sleep - no delay between items
            except Exception as e:
                logger.warning(f"Error collecting submissions for {username}: {e}")

            # Collect comments from the target subreddit (limited to 1000 most recent)
            try:
                for comment in user.comments.new(limit=1000):
                    if hasattr(comment, 'subreddit') and comment.subreddit.display_name.lower() == self.subreddit_name.lower():
                        self._store_comment(comment, username)
                        comments_collected += 1
                    # Removed sleep - no delay between items
            except Exception as e:
                logger.warning(f"Error collecting comments for {username}: {e}")

            # Update user record
            with self.db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE users SET
                            status = 'completed',
                            processed_at = datetime('now'),
                            post_count = ?,
                            comment_count = ?,
                            total_karma = ?,
                            account_created = ?
                        WHERE username = ?
                    ''', (posts_collected, comments_collected, total_karma, user_created, username))
                    conn.commit()

            logger.info(f"Processed {username}: {posts_collected} posts, {comments_collected} comments")
            return True

        except Exception as e:
            # Update user record with error
            with self.db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE users SET
                            status = 'failed',
                            error_message = ?,
                            last_attempt = datetime('now')
                        WHERE username = ?
                    ''', (str(e), username))
                    conn.commit()

            logger.error(f"Failed to process {username}: {e}")
            return False

    def _store_submission(self, submission, source_user: str):
        """Store submission in database."""
        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT OR IGNORE INTO submissions
                    (id, title, selftext, author, created_utc, score, upvote_ratio,
                     num_comments, permalink, url, domain, flair_text, is_self,
                     stickied, locked, source_user)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    submission.id,
                    submission.title,
                    submission.selftext,
                    submission.author.name if submission.author else '[deleted]',
                    int(submission.created_utc),
                    submission.score,
                    getattr(submission, 'upvote_ratio', None),
                    submission.num_comments,
                    submission.permalink,
                    submission.url,
                    getattr(submission, 'domain', None),
                    getattr(submission, 'link_flair_text', None),
                    submission.is_self,
                    submission.stickied,
                    getattr(submission, 'locked', False),
                    source_user
                ))
                conn.commit()

    def _store_comment(self, comment, source_user: str):
        """Store comment in database."""
        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Ensure submission_id has t3_ prefix for proper linking
                submission_id = comment.submission.id
                if not submission_id.startswith('t3_'):
                    submission_id = f't3_{submission_id}'

                cursor.execute('''
                    INSERT OR IGNORE INTO comments
                    (id, body, author, created_utc, score, submission_id, parent_id,
                     permalink, is_submitter, stickied, source_user)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    comment.id,
                    comment.body,
                    comment.author.name if comment.author else '[deleted]',
                    int(comment.created_utc),
                    comment.score,
                    submission_id,
                    comment.parent_id,
                    comment.permalink,
                    comment.is_submitter,
                    comment.stickied,
                    source_user
                ))
                conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive scraping statistics."""
        stats = {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # User statistics
            cursor.execute('SELECT status, COUNT(*) FROM users GROUP BY status')
            user_stats = dict(cursor.fetchall())
            stats['users'] = user_stats

            # Content statistics
            cursor.execute('SELECT COUNT(*) FROM submissions')
            stats['total_submissions'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM comments')
            stats['total_comments'] = cursor.fetchone()[0]

            # Date range
            cursor.execute('SELECT MIN(created_utc), MAX(created_utc) FROM submissions WHERE created_utc IS NOT NULL')
            date_range = cursor.fetchone()
            if date_range[0] and date_range[1]:
                stats['date_range'] = {
                    'start': datetime.fromtimestamp(date_range[0]).isoformat(),
                    'end': datetime.fromtimestamp(date_range[1]).isoformat()
                }

        return stats

    def export_data(self, format: str = 'json', output_path: str = None) -> str:
        """
        Export collected data in various formats.

        Args:
            format: Export format ('json', 'csv', 'jsonl')
            output_path: Output file path (auto-generated if None)

        Returns:
            Path to exported file
        """
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(self.output_dir, exist_ok=True)
            output_path = os.path.join(self.output_dir, f"{self.subreddit_name}_export_{timestamp}.{format}")

        if format == 'json':
            self._export_json(output_path)
        elif format == 'csv':
            self._export_csv(output_path)
        elif format == 'jsonl':
            self._export_jsonl(output_path)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Data exported to {output_path}")
        return output_path

    def _export_json(self, output_path: str):
        """Export data as JSON."""
        data = {'metadata': self.get_stats(), 'submissions': [], 'comments': []}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM submissions ORDER BY created_utc')
            data['submissions'] = [dict(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM comments ORDER BY created_utc')
            data['comments'] = [dict(row) for row in cursor.fetchall()]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _export_csv(self, output_path: str):
        """Export data as CSV files."""
        import pandas as pd

        base_path = str(Path(output_path).with_suffix(''))

        with sqlite3.connect(self.db_path) as conn:
            # Export submissions
            df_submissions = pd.read_sql_query('SELECT * FROM submissions ORDER BY created_utc', conn)
            df_submissions.to_csv(f"{base_path}_submissions.csv", index=False)

            # Export comments
            df_comments = pd.read_sql_query('SELECT * FROM comments ORDER BY created_utc', conn)
            df_comments.to_csv(f"{base_path}_comments.csv", index=False)

            # Export users
            df_users = pd.read_sql_query('SELECT * FROM users ORDER BY discovered_at', conn)
            df_users.to_csv(f"{base_path}_users.csv", index=False)

    def _export_jsonl(self, output_path: str):
        """Export data as JSONL (one JSON object per line)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            with open(output_path, 'w', encoding='utf-8') as f:
                # Export submissions
                cursor.execute('SELECT * FROM submissions ORDER BY created_utc')
                for row in cursor.fetchall():
                    record = dict(row)
                    record['type'] = 'submission'
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

                # Export comments
                cursor.execute('SELECT * FROM comments ORDER BY created_utc')
                for row in cursor.fetchall():
                    record = dict(row)
                    record['type'] = 'comment'
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

# Global logger will be set up by the scraper instance
logger = None