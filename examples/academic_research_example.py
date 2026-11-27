#!/usr/bin/env python3
"""
Example: Academic Research Pipeline
Demonstrates using the Reddit Scraper Toolkit for academic research on online communities.
"""

import sys
from pathlib import Path

# Add toolkit to path
sys.path.append(str(Path(__file__).parent.parent))

from core.reddit_scraper import UniversalRedditScraper
from analyzers.temporal_analyzer import TemporalAnalyzer
from analyzers.text_analyzer import TextAnalyzer
from analyzers.network_analyzer import NetworkAnalyzer
from config.config_manager import ConfigManager
import json

def main():
    """
    Example academic research pipeline:
    1. Configure for academic research context
    2. Scrape a target subreddit
    3. Run comprehensive analysis
    4. Generate research-ready outputs
    """

    # No date filter: analyze everything in the database. Set these to
    # 'YYYY-MM-DD' strings to restrict a real study to one period.
    period_start = None
    period_end = None

    # Configuration for academic research
    config_manager = ConfigManager()

    # Create academic research configuration
    config = config_manager.get_research_context_template('academic')

    # Customize for target subreddit
    target_subreddit = 'MachineLearning'
    config['subreddit']['name'] = target_subreddit
    config['subreddit']['research_focus'] = 'Academic community discourse analysis'

    # Update paths
    base_name = target_subreddit.lower()
    config['paths']['database'] = f"examples/output/{base_name}_data.db"
    config['paths']['checkpoint'] = f"examples/output/{base_name}_checkpoint.pkl"
    config['paths']['log'] = f"examples/output/{base_name}_research.log"
    config['paths']['output_dir'] = f"examples/output/{base_name}_analysis"

    # Academic-appropriate settings
    config['scraping']['batch_size'] = 5  # Conservative for academic use
    config['scraping']['max_users'] = 100  # Limit for example
    config['rate_limits']['content_extraction'] = 3.0  # Respectful rate limiting

    # Create necessary directories
    config_manager.validate_paths(config)

    print("=== Academic Research Example ===")
    print(f"Target Subreddit: r/{target_subreddit}")
    print(f"Research Focus: {config['subreddit']['research_focus']}")
    print(f"Database: {config['paths']['database']}")
    print()

    # Step 1: Data Collection
    print("Step 1: Data Collection")
    print("-" * 30)

    # Note: In a real scenario, you would set actual Reddit API credentials
    # For this example, we'll demonstrate the configuration structure
    if not all([
        config['reddit']['client_id'] != 'YOUR_CLIENT_ID',
        config['reddit']['client_secret'] != 'YOUR_CLIENT_SECRET'
    ]):
        print("⚠️  Reddit API credentials not configured.")
        print("   Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables")
        print("   or update the configuration file with your credentials.")
        print("\n   Skipping scraping step for this example...")
        create_mock_data = True
    else:
        create_mock_data = False

    if not create_mock_data:
        # Initialize scraper with academic configuration
        scraper = UniversalRedditScraper(config)

        # Discover users from recent high-quality posts
        print(f"Discovering users from r/{target_subreddit}...")
        discovered = scraper.discover_users_from_subreddit(
            limit=500,  # Moderate limit for academic research
            time_filter='month'  # Recent activity for relevance
        )
        print(f"✓ Discovered {discovered} users")

        # Process users with academic-appropriate batch size
        print("Processing user data...")
        results = scraper.process_users(
            batch_size=config['scraping']['batch_size'],
            max_users=config['scraping']['max_users']
        )
        print(f"✓ Processing complete: {results}")

        # Get final statistics
        stats = scraper.get_stats()
        print(f"✓ Collected {stats.get('total_submissions', 0):,} posts and {stats.get('total_comments', 0):,} comments")
    else:
        # Mock data creation for demonstration
        print("📝 Creating mock database for demonstration...")
        create_mock_database(config['paths']['database'])

    print()

    # Step 2: Comprehensive Analysis
    print("Step 2: Comprehensive Analysis")
    print("-" * 35)

    db_path = config['paths']['database']
    output_dir = config['paths']['output_dir']

    # Temporal Analysis
    print("Running temporal analysis...")
    temporal_analyzer = TemporalAnalyzer(db_path, f"{output_dir}/temporal")
    temporal_results = temporal_analyzer.generate_comprehensive_report(
        start_date=period_start,  # the past year
        end_date=period_end
    )
    print(f"✓ Temporal analysis complete: {temporal_results['files']['html_report']}")

    # Text Analysis for Academic Content
    print("Running text analysis...")
    text_analyzer = TextAnalyzer(db_path, f"{output_dir}/text")
    text_results = text_analyzer.analyze_text_comprehensively(
        content_types=['submissions', 'comments'],
        start_date=period_start,
        end_date=period_end
    )
    print(f"✓ Text analysis complete: {text_results['files']['html_report']}")

    # Network Analysis for Community Structure
    print("Running network analysis...")
    try:
        network_analyzer = NetworkAnalyzer(db_path, f"{output_dir}/network")
        network_results = network_analyzer.generate_comprehensive_analysis(
            network_types=['interaction', 'coparticipation'],
            start_date=period_start,
            end_date=period_end
        )
        print(f"✓ Network analysis complete: {network_results['files']['html_report']}")
    except ImportError:
        print("⚠️  Network analysis requires NetworkX. Install with: pip install networkx")
        network_results = None

    print()

    # Step 3: Research Summary
    print("Step 3: Academic Research Summary")
    print("-" * 37)

    # Compile research findings
    research_summary = {
        'study_metadata': {
            'subreddit': target_subreddit,
            'research_focus': config['subreddit']['research_focus'],
            'analysis_period': f'{period_start} to {period_end}' if period_start else 'all dates',
            'methodology': 'User-centric Reddit scraping with comprehensive analysis'
        },
        'temporal_insights': temporal_results.get('insights', {}),
        'text_insights': text_results.get('statistics', {}),
        'network_insights': network_results.get('metrics', {}) if network_results else None
    }

    # Save research summary
    summary_path = Path(output_dir) / 'academic_research_summary.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(research_summary, f, indent=2, ensure_ascii=False)

    print(f"✓ Research summary saved: {summary_path}")

    # Generate academic citation format
    print("\n📚 Academic Citation:")
    print(f"   Data collected from r/{target_subreddit} using user-centric methodology")
    print(f"   Analysis period: {period_start} to {period_end}" if period_start else "   Analysis period: all dates")
    print(f"   Processing date: {temporal_results['analysis_timestamp'][:10]}")

    print("\n🎯 Key Research Outputs:")
    print(f"   • Temporal patterns: {temporal_results['files']['html_report']}")
    print(f"   • Content analysis: {text_results['files']['html_report']}")
    if network_results:
        print(f"   • Network structure: {network_results['files']['html_report']}")
    print(f"   • Research summary: {summary_path}")

    print(f"\n✅ Academic research pipeline completed successfully!")
    print(f"   Results available in: {output_dir}")

def create_mock_database(db_path):
    """Build a demonstration database from the toolkit's synthetic sample.

    The rows are invented (see rrt/sample.py). They carry the same tables and
    columns a real scrape produces, so every analyzer runs on them.
    """
    import tempfile
    from rrt import sample
    from rrt.bridge import build_database

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        dataset = sample.write_sample(Path(scratch))
        build_database(dataset, Path(db_path))

    print("✓ Demonstration database created from synthetic sample data")

if __name__ == '__main__':
    main()