#!/usr/bin/env python3
"""
Quick Start Example
Simple demonstration of basic toolkit functionality.
"""

import sys
from pathlib import Path

# Add toolkit to path
sys.path.append(str(Path(__file__).parent.parent))

def main():
    """
    Quick start demonstration showing the most basic usage patterns.
    """
    print("🚀 Reddit Scraper Toolkit - Quick Start")
    print("=" * 45)
    print()

    # Show basic CLI usage examples
    print("1. Basic CLI Commands")
    print("-" * 22)
    print("   # Scrape a subreddit:")
    print("   ./scripts/scrape.sh MachineLearning")
    print()
    print("   # Analyze data:")
    print("   ./scripts/analyze.sh --all databases/machinelearning_data.db")
    print()
    print("   # Check status:")
    print("   ./scripts/reddit-toolkit status --database data.db")
    print()

    # Show configuration creation
    print("2. Configuration Setup")
    print("-" * 23)
    print("   # Create configuration from template:")
    print("   ./scripts/reddit-toolkit config --template academic --subreddit MachineLearning")
    print()
    print("   # Set environment variables:")
    print("   export REDDIT_CLIENT_ID='your_client_id'")
    print("   export REDDIT_CLIENT_SECRET='your_client_secret'")
    print()

    # Show programmatic usage
    print("3. Programmatic Usage")
    print("-" * 22)
    print("   ```python")
    print("   from config.config_manager import ConfigManager")
    print("   from core.reddit_scraper import UniversalRedditScraper")
    print()
    print("   # Load configuration")
    print("   config_manager = ConfigManager()")
    print("   config = config_manager.load_config('my_config.yaml')")
    print()
    print("   # Initialize scraper")
    print("   scraper = UniversalRedditScraper(config)")
    print()
    print("   # Collect data")
    print("   scraper.discover_users_from_subreddit(limit=1000)")
    print("   scraper.process_users(batch_size=10)")
    print("   ```")
    print()

    # Show analysis workflow
    print("4. Analysis Workflow")
    print("-" * 20)
    print("   ```python")
    print("   from analyzers.temporal_analyzer import TemporalAnalyzer")
    print("   from analyzers.text_analyzer import TextAnalyzer")
    print()
    print("   # Run temporal analysis")
    print("   temporal = TemporalAnalyzer('data.db')")
    print("   results = temporal.generate_comprehensive_report()")
    print()
    print("   # Run text analysis")
    print("   text = TextAnalyzer('data.db')")
    print("   results = text.analyze_text_comprehensively()")
    print("   ```")
    print()

    # Show output structure
    print("5. Output Structure")
    print("-" * 18)
    print("   output/")
    print("   ├── subreddit_name/")
    print("   │   ├── temporal/")
    print("   │   │   ├── monthly_trends.html")
    print("   │   │   ├── daily_patterns.html")
    print("   │   │   └── temporal_report.html")
    print("   │   ├── text/")
    print("   │   │   ├── word_frequency.json")
    print("   │   │   ├── sentiment_analysis.json")
    print("   │   │   └── text_analysis_report.html")
    print("   │   └── network/")
    print("   │       ├── subreddit_interaction.graphml")
    print("   │       ├── subreddit_coparticipation.gexf")
    print("   │       └── network_analysis_report.html")
    print("   └── analysis_results.json")
    print()

    # Show next steps
    print("6. Next Steps")
    print("-" * 12)
    print("   📖 Read the full README.md for detailed documentation")
    print("   🔧 Check examples/ directory for complete use cases")
    print("   🎯 Run academic_research_example.py for a full demonstration")
    print("   🔄 Try comparative_study_example.py for multi-community analysis")
    print("   📞 Visit GitHub repository for support and updates")
    print()

    # Show helpful tips
    print("7. Helpful Tips")
    print("-" * 14)
    print("   💡 Start with small datasets (max_users=100) for testing")
    print("   ⚡ Use --discover-only first to estimate data size")
    print("   📊 Export data to CSV/JSON for external analysis")
    print("   🔍 Check logs for detailed progress information")
    print("   🛡️  Always respect Reddit's rate limits and terms of service")
    print()

    print("✅ Ready to start scraping and analyzing Reddit communities!")
    print("   Visit the examples/ directory for working code demonstrations.")

if __name__ == '__main__':
    main()