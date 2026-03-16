#!/bin/bash
# Quick analysis script with common options

set -e

# Default values
DATABASE=""
OUTPUT_DIR=""
TEMPORAL=false
TEXT=false
NETWORK=false
ALL_ANALYSES=false
START_DATE=""
END_DATE=""

# Help function
show_help() {
    cat << EOF
Reddit Analyzer - Quick Analysis Script

Usage: $0 [OPTIONS] DATABASE

Arguments:
    DATABASE                Database file path

Options:
    -o, --output DIR        Output directory
    -t, --temporal          Run temporal analysis
    -x, --text              Run text analysis
    -n, --network           Run network analysis
    -a, --all               Run all analyses
    -s, --start-date DATE   Start date for analysis (YYYY-MM-DD)
    -e, --end-date DATE     End date for analysis (YYYY-MM-DD)
    -h, --help              Show this help message

Examples:
    $0 --all data/machinelearning_data.db
    $0 --temporal --text data/machinelearning_data.db
    $0 --all --start-date 2020-01-01 --end-date 2020-12-31 data.db

Note: Network analysis requires additional dependencies (networkx, plotly).
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -t|--temporal)
            TEMPORAL=true
            shift
            ;;
        -x|--text)
            TEXT=true
            shift
            ;;
        -n|--network)
            NETWORK=true
            shift
            ;;
        -a|--all)
            ALL_ANALYSES=true
            shift
            ;;
        -s|--start-date)
            START_DATE="$2"
            shift 2
            ;;
        -e|--end-date)
            END_DATE="$2"
            shift 2
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
            if [ -z "$DATABASE" ]; then
                DATABASE="$1"
            else
                echo "Error: Multiple databases specified" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate required arguments
if [ -z "$DATABASE" ]; then
    echo "Error: Database file is required" >&2
    show_help
    exit 1
fi

# Check if database exists
if [ ! -f "$DATABASE" ]; then
    echo "Error: Database file not found: $DATABASE" >&2
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_SCRIPT="$SCRIPT_DIR/reddit-toolkit"

# Build command
CMD=("$TOOLKIT_SCRIPT" "analyze" "--database" "$DATABASE")

# Add output directory if specified
if [ -n "$OUTPUT_DIR" ]; then
    CMD+=("--output" "$OUTPUT_DIR")
fi

# Add analysis types
if [ "$ALL_ANALYSES" = true ]; then
    CMD+=("--all")
else
    if [ "$TEMPORAL" = true ]; then
        CMD+=("--temporal")
    fi
    if [ "$TEXT" = true ]; then
        CMD+=("--text")
    fi
    if [ "$NETWORK" = true ]; then
        CMD+=("--network")
    fi

    # If no specific analysis type is selected, run all by default
    if [ "$TEMPORAL" = false ] && [ "$TEXT" = false ] && [ "$NETWORK" = false ]; then
        echo "No analysis type specified, running all analyses..."
        CMD+=("--all")
        ALL_ANALYSES=true
    fi
fi

# Add date range if specified
if [ -n "$START_DATE" ]; then
    CMD+=("--start-date" "$START_DATE")
fi
if [ -n "$END_DATE" ]; then
    CMD+=("--end-date" "$END_DATE")
fi

# Display configuration
echo "Reddit Analysis Configuration:"
echo "  Database: $DATABASE"
echo "  Output Directory: ${OUTPUT_DIR:-auto-generated}"
echo "  Temporal Analysis: $TEMPORAL"
echo "  Text Analysis: $TEXT"
echo "  Network Analysis: $NETWORK"
echo "  All Analyses: $ALL_ANALYSES"
if [ -n "$START_DATE" ] || [ -n "$END_DATE" ]; then
    echo "  Date Range: ${START_DATE:-any} to ${END_DATE:-any}"
fi
echo ""

# Check for optional dependencies
echo "Checking dependencies..."
python3 -c "import pandas, sqlite3, plotly; print('✓ Core dependencies available')" || {
    echo "✗ Missing core dependencies (pandas, plotly)"
    echo "Install with: pip install -r config/requirements.txt"
    exit 1
}

if [ "$NETWORK" = true ] || [ "$ALL_ANALYSES" = true ]; then
    python3 -c "import networkx; print('✓ Network analysis dependencies available')" 2>/dev/null || {
        echo "⚠ Network analysis dependencies missing (networkx)"
        echo "Install with: pip install networkx"
        echo "Network analysis will be skipped..."
    }
fi

if [ "$TEXT" = true ] || [ "$ALL_ANALYSES" = true ]; then
    python3 -c "import nltk; print('✓ Text analysis dependencies available')" 2>/dev/null || {
        echo "⚠ Advanced text analysis dependencies missing (nltk)"
        echo "Install with: pip install nltk"
        echo "Basic text analysis will still work..."
    }
fi

echo ""

# Execute command
echo "Executing: ${CMD[*]}"
echo ""
exec "${CMD[@]}"