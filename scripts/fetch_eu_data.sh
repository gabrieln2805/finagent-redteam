#!/usr/bin/env bash
# Fetches real EU public financial data (no API key, no scraping -- these are
# plain CSV files published under CC-BY via the os-data/eu-structural-funds
# open-data project, itself sourced from the European Commission's Financial
# Transparency System and Romania's ERDF/ESF beneficiary registry).
#
# Source repo: https://github.com/os-data/eu-structural-funds
#
# Usage: bash scripts/fetch_eu_data.sh
set -euo pipefail

OUT_DIR="$(dirname "$0")/../data/raw/eu"
mkdir -p "$OUT_DIR"

BASE="https://raw.githubusercontent.com/os-data/eu-structural-funds/main"

echo "Fetching Romania ERDF/ESF beneficiary list (2007-2013)..."
curl -sSL "$BASE/data/RO.romania/cleaning_romania.csv" -o "$OUT_DIR/cleaning_romania.csv"

echo "Fetching EU Financial Transparency System bulk file (2015)..."
curl -sSL "$BASE/data/Financial%20Transparency%20System/FTS_2015.csv" -o "$OUT_DIR/FTS_2015.csv"

echo "Done. Files written to $OUT_DIR:"
ls -la "$OUT_DIR"
echo
echo "Next: python3 scripts/build_eu_ground_truth.py"
