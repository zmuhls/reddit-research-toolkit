#!/bin/bash
# Resume a previously interrupted scrape
# Usage: ./scripts/resume.sh <subreddit> [--max-posts N] [--batch-size N]

SUBREDDIT=${1:-"python"}
MAX_POSTS=${2:-1000}
BATCH_SIZE=${3:-20}

echo "=== Resuming Reddit Scraper ==="
echo "Subreddit:  r/${SUBREDDIT}"
echo "Max posts:  ${MAX_POSTS}"
echo "Batch size: ${BATCH_SIZE}"
echo ""

python3 tools/cli.py scrape \
    --subreddit "${SUBREDDIT}" \
    --max-posts "${MAX_POSTS}" \
    --batch-size "${BATCH_SIZE}" \
    --time-filter all

echo ""
echo "Scraping complete!"
