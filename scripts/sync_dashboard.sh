#!/bin/bash
# Copy the modules the dashboard shares with the toolkit into a clone of the
# dashboard Space, so both projects read and write the same dataset format.
#
# Usage: ./scripts/sync_dashboard.sh /path/to/reddit-dashboard
#
# The dashboard (https://huggingface.co/spaces/milwright/reddit-dashboard)
# carries verbatim copies of these files under src/. Edit them here, run the
# tests, then run this script and push the Space.

set -e

if [ -z "$1" ] || [ ! -d "$1/src" ]; then
    echo "Usage: $0 /path/to/reddit-dashboard   (a folder that contains src/)" >&2
    exit 1
fi

TOOLKIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$1"

mkdir -p "$TARGET/src/rrt" "$TARGET/tests"
for name in __init__ datasets sample errors credentials util; do
    cp "$TOOLKIT_DIR/rrt/$name.py" "$TARGET/src/rrt/$name.py"
done
cp "$TOOLKIT_DIR/simple_scraper.py" "$TARGET/src/simple_scraper.py"
cp "$TOOLKIT_DIR/tests/fake_reddit.py" "$TARGET/tests/fake_reddit.py"

echo "Copied rrt/{__init__,datasets,sample,errors,credentials,util}.py, simple_scraper.py and tests/fake_reddit.py"
echo "into $TARGET. Run the dashboard's tests before you push:  python -m pytest"
