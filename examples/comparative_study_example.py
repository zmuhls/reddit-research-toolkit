#!/usr/bin/env python3
"""
Example: Comparative Study Pipeline
Demonstrates multi-subreddit comparative analysis using standardized methodology.
"""

import sys
from pathlib import Path

# Add toolkit to path
sys.path.append(str(Path(__file__).parent.parent))

from core.reddit_scraper import UniversalRedditScraper
from analyzers.temporal_analyzer import TemporalAnalyzer
from analyzers.text_analyzer import TextAnalyzer
from config.config_manager import ConfigManager
import json
import pandas as pd
from datetime import datetime

def main():
    """
    Example comparative study pipeline:
    1. Configure standardized settings for multiple subreddits
    2. Scrape data from each community
    3. Run parallel analysis with identical parameters
    4. Generate comparative reports
    """

    print("=== Comparative Study Example ===")
    print("Multi-community analysis with standardized methodology")
    print()

    # Define study parameters
    study_subreddits = ['MachineLearning', 'datascience', 'statistics']
    # None means no date filter. Use 'YYYY-MM-DD' strings to restrict a real
    # study to one period.
    study_period = {
        'start_date': None,
        'end_date': None
    }

    config_manager = ConfigManager()
    study_results = {}

    # Step 1: Standardized Configuration
    print("Step 1: Configuration Setup")
    print("-" * 30)

    base_config = config_manager.get_research_context_template('comparative')
    base_config['scraping']['max_users'] = 50  # Limit for example
    base_config['analysis']['topic_modeling_topics'] = 8  # Standardized topics

    print(f"Study subreddits: {', '.join(study_subreddits)}")
    print(f"Study period: {study_period['start_date']} to {study_period['end_date']}")
    print(f"Standardized settings: max_users={base_config['scraping']['max_users']}, topics={base_config['analysis']['topic_modeling_topics']}")
    print()

    # Step 2: Multi-Community Data Collection
    print("Step 2: Multi-Community Data Collection")
    print("-" * 42)

    for subreddit in study_subreddits:
        print(f"Processing r/{subreddit}...")

        # Configure for this subreddit
        config = base_config.copy()
        config['subreddit']['name'] = subreddit
        config['subreddit']['research_focus'] = f'Comparative analysis of {subreddit} community'

        # Standardized paths
        base_name = subreddit.lower()
        config['paths']['database'] = f"examples/output/comparative/{base_name}_data.db"
        config['paths']['checkpoint'] = f"examples/output/comparative/{base_name}_checkpoint.pkl"
        config['paths']['log'] = f"examples/output/comparative/{base_name}.log"
        config['paths']['output_dir'] = f"examples/output/comparative/{base_name}"

        # Create directories
        config_manager.validate_paths(config)

        # Mock data creation for demonstration
        print(f"  📝 Creating mock data for r/{subreddit}...")
        create_comparative_mock_data(config['paths']['database'], subreddit)

        study_results[subreddit] = {
            'config': config,
            'database': config['paths']['database'],
            'output_dir': config['paths']['output_dir']
        }

        print(f"  ✓ r/{subreddit} setup complete")

    print()

    # Step 3: Parallel Analysis
    print("Step 3: Standardized Parallel Analysis")
    print("-" * 40)

    analysis_results = {}

    for subreddit in study_subreddits:
        print(f"Analyzing r/{subreddit}...")

        db_path = study_results[subreddit]['database']
        output_dir = study_results[subreddit]['output_dir']

        # Temporal analysis with identical parameters
        temporal_analyzer = TemporalAnalyzer(db_path, f"{output_dir}/temporal")
        temporal_results = temporal_analyzer.generate_comprehensive_report(
            start_date=study_period['start_date'],
            end_date=study_period['end_date']
        )

        # Text analysis with identical parameters
        text_analyzer = TextAnalyzer(db_path, f"{output_dir}/text")
        text_results = text_analyzer.analyze_text_comprehensively(
            content_types=['submissions', 'comments'],
            start_date=study_period['start_date'],
            end_date=study_period['end_date']
        )

        analysis_results[subreddit] = {
            'temporal': temporal_results,
            'text': text_results
        }

        print(f"  ✓ r/{subreddit} analysis complete")

    print()

    # Step 4: Comparative Analysis
    print("Step 4: Cross-Community Comparison")
    print("-" * 36)

    comparison_metrics = generate_comparison_metrics(analysis_results)

    # Create comparative summary
    comparative_summary = {
        'study_metadata': {
            'subreddits': study_subreddits,
            'study_period': study_period,
            'methodology': 'Standardized comparative analysis',
            'generated_at': datetime.now().isoformat()
        },
        'comparative_metrics': comparison_metrics,
        'individual_results': {
            subreddit: {
                'temporal_insights': results['temporal'].get('insights', {}),
                'text_statistics': results['text'].get('statistics', {})
            }
            for subreddit, results in analysis_results.items()
        }
    }

    # Save comparative summary
    summary_path = Path("examples/output/comparative/comparative_study_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(comparative_summary, f, indent=2, ensure_ascii=False)

    print(f"✓ Comparative summary saved: {summary_path}")

    # Generate comparison report
    generate_comparison_report(comparative_summary, "examples/output/comparative/comparison_report.html")

    print()

    # Step 5: Results Summary
    print("Step 5: Comparative Study Results")
    print("-" * 35)

    print("📊 Community Comparison Highlights:")
    for subreddit in study_subreddits:
        metrics = comparison_metrics[subreddit]
        print(f"   r/{subreddit}:")
        print(f"     • Activity Level: {metrics.get('total_items', 0):,} items")
        print(f"     • Avg Text Length: {metrics.get('avg_text_length', 0):.0f} chars")
        print(f"     • Vocabulary Richness: {metrics.get('vocabulary_richness', 0):.3f}")

    print(f"\n📁 Output Structure:")
    print(f"   examples/output/comparative/")
    for subreddit in study_subreddits:
        print(f"   ├── {subreddit.lower()}/")
        print(f"   │   ├── temporal/")
        print(f"   │   └── text/")
    print(f"   ├── comparative_study_summary.json")
    print(f"   └── comparison_report.html")

    print(f"\n✅ Comparative study completed successfully!")
    print(f"   Cross-community insights available in: {summary_path}")

def create_comparative_mock_data(db_path, subreddit):
    """Build a demonstration database for one community from synthetic data.

    Each community gets a different seed and size, so the comparison has
    something to compare. The rows are invented (see rrt/sample.py).
    """
    import tempfile
    import zlib
    from rrt import sample
    from rrt.bridge import build_database
    from rrt.datasets import STATUS_COMPLETE, DatasetWriter

    seed = zlib.crc32(subreddit.encode('utf-8')) % 10_000
    posts, comments = sample.generate(n_posts=120 + seed % 180, seed=seed)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        writer = DatasetWriter([subreddit], {'seed': seed}, root=Path(scratch), source='synthetic')
        for post in posts:
            writer.add_post({**post, 'subreddit': subreddit})
        for comment in comments:
            writer.add_comment({**comment, 'subreddit': subreddit})
        build_database(writer.close(STATUS_COMPLETE), Path(db_path))

def generate_comparison_metrics(analysis_results):
    """Generate standardized comparison metrics across communities."""
    comparison_metrics = {}

    for subreddit, results in analysis_results.items():
        text_stats = results['text'].get('statistics', {})
        temporal_insights = results['temporal'].get('insights', {})

        comparison_metrics[subreddit] = {
            'total_items': text_stats.get('total_items', 0),
            'unique_authors': text_stats.get('author_stats', {}).get('unique_authors', 0),
            'avg_text_length': text_stats.get('text_length_stats', {}).get('mean_characters', 0),
            'vocabulary_richness': text_stats.get('vocabulary_richness', 0),
            'posts_per_author': text_stats.get('author_stats', {}).get('posts_per_author', 0),
            'temporal_span_days': temporal_insights.get('summary', {}).get('total_days', 0),
            'peak_activity_date': temporal_insights.get('peak_day', {}).get('date', 'N/A')
        }

    return comparison_metrics

def generate_comparison_report(comparative_summary, output_path):
    """Generate HTML comparison report."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Comparative Study Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
            .comparison-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .comparison-table th, .comparison-table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            .comparison-table th {{ background-color: #f2f2f2; }}
            .metric-highlight {{ background-color: #e7f3ff; font-weight: bold; }}
            .section {{ margin: 30px 0; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Reddit Communities Comparative Study</h1>
            <p>Study Period: {comparative_summary['study_metadata']['study_period']['start_date']}
               to {comparative_summary['study_metadata']['study_period']['end_date']}</p>
            <p>Communities: {', '.join(comparative_summary['study_metadata']['subreddits'])}</p>
            <p>Generated: {comparative_summary['study_metadata']['generated_at'][:19]}</p>
        </div>

        <div class="section">
            <h2>Community Metrics Comparison</h2>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Community</th>
                        <th>Total Items</th>
                        <th>Unique Authors</th>
                        <th>Avg Text Length</th>
                        <th>Vocabulary Richness</th>
                        <th>Posts per Author</th>
                    </tr>
                </thead>
                <tbody>
    """

    # Add comparison data
    for subreddit, metrics in comparative_summary['comparative_metrics'].items():
        html_content += f"""
                    <tr>
                        <td><strong>r/{subreddit}</strong></td>
                        <td>{metrics['total_items']:,}</td>
                        <td>{metrics['unique_authors']:,}</td>
                        <td>{metrics['avg_text_length']:.0f} chars</td>
                        <td>{metrics['vocabulary_richness']:.3f}</td>
                        <td>{metrics['posts_per_author']:.1f}</td>
                    </tr>
        """

    html_content += """
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Key Findings</h2>
            <ul>
                <li><strong>Community Size Variation:</strong> Different communities show varying levels of participation</li>
                <li><strong>Discourse Patterns:</strong> Text length and vocabulary usage varies by community focus</li>
                <li><strong>Engagement Levels:</strong> Posts per author indicates different community engagement styles</li>
            </ul>
        </div>

        <div class="section">
            <h2>Methodology</h2>
            <p>This comparative study used standardized data collection and analysis methods across all communities:</p>
            <ul>
                <li>Identical scraping parameters and rate limiting</li>
                <li>Standardized temporal and text analysis procedures</li>
                <li>Consistent time period and sampling methodology</li>
                <li>Cross-community metrics calculated using identical algorithms</li>
            </ul>
        </div>
    </body>
    </html>
    """

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ Comparison report generated: {output_path}")

if __name__ == '__main__':
    main()