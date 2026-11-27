#!/bin/bash
# Resume an interrupted archive: process the users already discovered.
#
# Usage: ./scripts/resume.sh SUBREDDIT [extra options for 'scrape']
#
#   ./scripts/resume.sh CUNY
#   ./scripts/resume.sh CUNY --max-users 500 --batch-size 20

set -e

if [ -z "$1" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

SUBREDDIT="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/reddit-toolkit" scrape --subreddit "$SUBREDDIT" --process-only "$@"
