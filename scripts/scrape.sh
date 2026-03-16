#!/bin/bash
# Quick scraping script with common options

set -e

# Default values
SUBREDDIT=""
MAX_POSTS=10000
BATCH_SIZE=10
TIME_FILTER="all"
DISCOVER_ONLY=false
PROCESS_ONLY=false

# Help function
show_help() {
    cat << EOF
Reddit Scraper - Quick Scraping Script

Usage: $0 [OPTIONS] SUBREDDIT

Arguments:
    SUBREDDIT       Subreddit name (without r/)

Options:
    -p, --max-posts NUM        Maximum posts to scan for discovery [default: 10000]
    -b, --batch-size NUM       User processing batch size [default: 10]
    -f, --time-filter FILTER   Time filter (hour, day, week, month, year, all) [default: all]
    -d, --discover-only        Only discover users, don't process them
    -r, --process-only         Only process existing users
    -h, --help                 Show this help message

Examples:
    $0 MachineLearning
    $0 -p 20000 -b 20 MachineLearning
    $0 --discover-only --max-posts 5000 MachineLearning

Environment Variables:
    REDDIT_CLIENT_ID       Reddit API client ID (required)
    REDDIT_CLIENT_SECRET   Reddit API client secret (required)
    REDDIT_USER_AGENT      Reddit API user agent (optional)

Note: Set credentials in .env file or export as environment variables
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--max-posts)
            MAX_POSTS="$2"
            shift 2
            ;;
        -b|--batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        -f|--time-filter)
            TIME_FILTER="$2"
            shift 2
            ;;
        -d|--discover-only)
            DISCOVER_ONLY=true
            shift
            ;;
        -r|--process-only)
            PROCESS_ONLY=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            show_help
            exit 1
            ;;
        *)
            if [ -z "$SUBREDDIT" ]; then
                SUBREDDIT="$1"
            else
                echo "Error: Multiple subreddits specified" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate required arguments
if [ -z "$SUBREDDIT" ]; then
    echo "Error: Subreddit name is required" >&2
    show_help
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_SCRIPT="$SCRIPT_DIR/reddit-toolkit"

# Build command
CMD=("$TOOLKIT_SCRIPT" "scrape" "--subreddit" "$SUBREDDIT")

# Add optional parameters
CMD+=("--max-posts" "$MAX_POSTS")
CMD+=("--batch-size" "$BATCH_SIZE")
CMD+=("--time-filter" "$TIME_FILTER")

if [ "$DISCOVER_ONLY" = true ]; then
    CMD+=("--discover-only")
fi

if [ "$PROCESS_ONLY" = true ]; then
    CMD+=("--process-only")
fi

# Display configuration
echo "Reddit Scraper Configuration:"
echo "  Subreddit: r/$SUBREDDIT"
echo "  Max Posts: $MAX_POSTS"
echo "  Batch Size: $BATCH_SIZE"
echo "  Time Filter: $TIME_FILTER"
echo "  Discover Only: $DISCOVER_ONLY"
echo "  Process Only: $PROCESS_ONLY"
echo ""

# Execute command
echo "Executing: ${CMD[*]}"
echo ""
exec "${CMD[@]}"