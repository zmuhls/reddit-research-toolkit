#!/usr/bin/env python3
"""
Command Line Interface for Reddit Scraper Toolkit
Provides easy-to-use CLI commands for scraping and analysis.
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List, Optional
import json

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, continue without it

# Add toolkit to path
sys.path.append(str(Path(__file__).parent.parent))

from core.reddit_scraper import UniversalRedditScraper
from analyzers.temporal_analyzer import TemporalAnalyzer
from analyzers.text_analyzer import TextAnalyzer
from analyzers.network_analyzer import NetworkAnalyzer
from config.config_manager import ConfigManager

def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def cmd_scrape(args):
    """Execute scraping command."""
    config_manager = ConfigManager()

    if args.config:
        config = config_manager.load_config(args.config)
    else:
        # Create simple default configuration
        base_name = args.subreddit.lower()
        config = {
            'subreddit': {
                'name': args.subreddit,
                'display_name': f'r/{args.subreddit}'
            },
            'reddit': {
                'client_id': args.client_id or '',
                'client_secret': args.client_secret or '',
                'user_agent': args.user_agent or f'Reddit Scraper for r/{args.subreddit}'
            },
            'paths': {
                'database': f"databases/{base_name}_data.db",
                'checkpoint': f"checkpoints/{base_name}_checkpoint.pkl",
                'log': f"logs/{base_name}.log",
                'output_dir': f"output/{base_name}"
            },
            'rate_limits': {
                'user_discovery': 0.5,
                'content_extraction': 0.05,  # Optimized: 10 users per 10 seconds
                'comment_expansion': 0.01,
                'batch_processing': 0.1,  # Minimal batch delay
                'rate_limit_backoff': 60.0
            },
            'scraping': {
                'batch_size': args.batch_size or 20,  # Increased from 10
                'max_users': args.max_users,
                'max_posts_per_discovery': args.max_posts or 1000,
                'time_filter': args.time_filter or 'all',
                'resume_on_interrupt': True,
                'save_checkpoint_interval': 50  # Checkpoint less frequently for speed
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

    # Update from environment variables (will override empty values)
    config = config_manager.update_config_from_env(config)

    # Create necessary directories
    created_dirs = config_manager.validate_paths(config)
    if created_dirs:
        print(f"Created directories: {', '.join(created_dirs)}")

    # Initialize scraper
    scraper = UniversalRedditScraper(config)

    if args.discover_only:
        # Only discover users
        discovered = scraper.discover_users_from_subreddit(
            limit=args.max_posts or 1000,
            time_filter=args.time_filter or 'all'
        )
        print(f"Discovered {discovered} new users")

    elif args.process_only:
        # Only process existing users
        results = scraper.process_users(
            batch_size=args.batch_size or 10,
            max_users=args.max_users
        )
        print(f"Processing results: {results}")

    else:
        # Full scraping workflow
        print(f"Starting full scrape of r/{config['subreddit']['name']}")

        # Discover users
        discovered = scraper.discover_users_from_subreddit(
            limit=args.max_posts or 1000,
            time_filter=args.time_filter or 'all'
        )
        print(f"Discovered {discovered} new users")

        # Process users
        results = scraper.process_users(
            batch_size=args.batch_size or 10,
            max_users=args.max_users
        )
        print(f"Processing results: {results}")

    # Export data if requested
    if args.export:
        export_path = scraper.export_data(format=args.export_format or 'json')
        print(f"Data exported to: {export_path}")

    # Show final statistics
    stats = scraper.get_stats()
    print(f"\nFinal Statistics:")
    print(f"  Total Users: {stats.get('users', {})}")
    print(f"  Total Submissions: {stats.get('total_submissions', 0):,}")
    print(f"  Total Comments: {stats.get('total_comments', 0):,}")

def cmd_analyze(args):
    """Execute analysis command."""
    db_path = args.database

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    output_dir = args.output or f"output/{Path(db_path).stem.replace('_data', '').replace('_historical_data', '')}"

    results = {}

    if args.temporal or args.all:
        print("Running temporal analysis...")
        analyzer = TemporalAnalyzer(db_path, f"{output_dir}/temporal")
        temporal_results = analyzer.generate_comprehensive_report(
            start_date=args.start_date,
            end_date=args.end_date
        )
        results['temporal'] = temporal_results
        print(f"Temporal analysis complete. Report: {temporal_results['files']['html_report']}")

    if args.text or args.all:
        print("Running text analysis...")
        analyzer = TextAnalyzer(db_path, f"{output_dir}/text")
        text_results = analyzer.analyze_text_comprehensively(
            content_types=args.content_types or ['submissions', 'comments'],
            start_date=args.start_date,
            end_date=args.end_date
        )
        results['text'] = text_results
        print(f"Text analysis complete. Report: {text_results['files']['html_report']}")

    if args.network or args.all:
        print("Running network analysis...")
        try:
            analyzer = NetworkAnalyzer(db_path, f"{output_dir}/network")
            network_results = analyzer.generate_comprehensive_analysis(
                network_types=args.network_types or ['interaction', 'coparticipation'],
                start_date=args.start_date,
                end_date=args.end_date
            )
            results['network'] = network_results
            print(f"Network analysis complete. Report: {network_results['files']['html_report']}")
        except ImportError as e:
            print(f"Network analysis requires additional dependencies: {e}")

    # Save combined results
    results_file = Path(output_dir) / "analysis_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nAnalysis complete! Results saved to: {results_file}")
    return 0

def cmd_config(args):
    """Execute configuration command."""
    config_manager = ConfigManager()

    if args.create_templates:
        config_manager.create_default_templates()
        print("Default configuration templates created in config/templates/")
        return 0

    if args.template and args.subreddit:
        config_path = config_manager.create_config_from_template(
            args.template,
            args.subreddit,
            args.output
        )
        print(f"Configuration created: {config_path}")
        print(f"Please edit the file to add your Reddit API credentials.")
        return 0

    if args.validate and args.config_file:
        try:
            config = config_manager.load_config(args.config_file)
            print(f"Configuration is valid: {args.config_file}")

            # Show configuration summary
            print(f"  Subreddit: r/{config['subreddit']['name']}")
            print(f"  Research Context: {config.get('research_context', 'not specified')}")
            print(f"  Database: {config['paths']['database']}")

            return 0
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return 1

    if args.schema:
        schema_path = config_manager.export_config_schema(args.schema)
        print(f"Configuration schema exported to: {schema_path}")
        return 0

    print("Please specify an action: --create-templates, --template, --validate, or --schema")
    return 1

def cmd_status(args):
    """Show status of scraping progress."""
    if not Path(args.database).exists():
        print(f"Database not found: {args.database}")
        return 1

    import sqlite3
    with sqlite3.connect(args.database) as conn:
        cursor = conn.cursor()

        # User statistics
        cursor.execute("SELECT status, COUNT(*) FROM users GROUP BY status")
        user_stats = dict(cursor.fetchall())

        # Content statistics
        cursor.execute("SELECT COUNT(*) FROM submissions")
        num_submissions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM comments")
        num_comments = cursor.fetchone()[0]

        # Date range
        cursor.execute("SELECT MIN(created_utc), MAX(created_utc) FROM submissions WHERE created_utc IS NOT NULL")
        date_range = cursor.fetchone()

        print(f"\nScraping Status for {Path(args.database).stem}:")
        print(f"  Users: {user_stats}")
        print(f"  Submissions: {num_submissions:,}")
        print(f"  Comments: {num_comments:,}")

        if date_range[0] and date_range[1]:
            from datetime import datetime
            start_date = datetime.fromtimestamp(date_range[0]).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(date_range[1]).strftime('%Y-%m-%d')
            print(f"  Date Range: {start_date} to {end_date}")

    return 0

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Reddit Scraper Toolkit - Comprehensive Reddit data collection and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape a subreddit (credentials from .env file)
  reddit-toolkit scrape --subreddit MachineLearning

  # Scrape with custom options
  reddit-toolkit scrape --subreddit MachineLearning --max-posts 2000 --batch-size 20

  # Scrape with custom configuration file
  reddit-toolkit scrape --config my_config.yaml

  # Run comprehensive analysis
  reddit-toolkit analyze --database databases/machinelearning_data.db --all

  # Check scraping status
  reddit-toolkit status --database databases/machinelearning_data.db
        """
    )

    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Set logging level')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Scrape Reddit data')
    scrape_parser.add_argument('--subreddit', required=True, help='Subreddit name (without r/)')
    scrape_parser.add_argument('--config', help='Configuration file path (optional, will use defaults if not provided)')
    scrape_parser.add_argument('--client-id', help='Reddit API client ID (or set REDDIT_CLIENT_ID env var)')
    scrape_parser.add_argument('--client-secret', help='Reddit API client secret (or set REDDIT_CLIENT_SECRET env var)')
    scrape_parser.add_argument('--user-agent', help='Reddit API user agent (or set REDDIT_USER_AGENT env var)')
    scrape_parser.add_argument('--max-posts', type=int, default=10000, help='Maximum posts to scan for user discovery (default: 10000)')
    scrape_parser.add_argument('--max-users', type=int, help='Maximum users to process (default: unlimited)')
    scrape_parser.add_argument('--batch-size', type=int, default=10, help='Batch size for user processing (default: 10)')
    scrape_parser.add_argument('--time-filter', choices=['hour', 'day', 'week', 'month', 'year', 'all'],
                              default='all', help='Time filter for post discovery (default: all)')
    scrape_parser.add_argument('--discover-only', action='store_true', help='Only discover users, don\'t process')
    scrape_parser.add_argument('--process-only', action='store_true', help='Only process existing users')
    scrape_parser.add_argument('--export', action='store_true', help='Export data after scraping')
    scrape_parser.add_argument('--export-format', choices=['json', 'csv', 'jsonl'], default='json',
                              help='Export format (default: json)')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze scraped data')
    analyze_parser.add_argument('--database', required=True, help='Database file path')
    analyze_parser.add_argument('--output', help='Output directory')
    analyze_parser.add_argument('--temporal', action='store_true', help='Run temporal analysis')
    analyze_parser.add_argument('--text', action='store_true', help='Run text analysis')
    analyze_parser.add_argument('--network', action='store_true', help='Run network analysis')
    analyze_parser.add_argument('--all', action='store_true', help='Run all analyses')
    analyze_parser.add_argument('--start-date', help='Start date for analysis (YYYY-MM-DD)')
    analyze_parser.add_argument('--end-date', help='End date for analysis (YYYY-MM-DD)')
    analyze_parser.add_argument('--content-types', nargs='+', choices=['submissions', 'comments'],
                               default=['submissions', 'comments'], help='Content types to analyze')
    analyze_parser.add_argument('--network-types', nargs='+',
                               choices=['interaction', 'coparticipation'],
                               default=['interaction', 'coparticipation'],
                               help='Network types to analyze')

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configurations')
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
    status_parser = subparsers.add_parser('status', help='Check scraping status')
    status_parser.add_argument('--database', required=True, help='Database file path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    setup_logging(args.log_level)

    try:
        if args.command == 'scrape':
            return cmd_scrape(args)
        elif args.command == 'analyze':
            return cmd_analyze(args)
        elif args.command == 'config':
            return cmd_config(args)
        elif args.command == 'status':
            return cmd_status(args)
        else:
            print(f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        logging.error(f"Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())