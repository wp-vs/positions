#!/usr/bin/env python3
"""Fetch latest prices and moving averages for trading positions.

Usage:
    python run.py                           # uses data/sample_positions.csv
    python run.py positions.csv             # specify a positions file
    python run.py /path/to/positions.csv    # absolute path
    python run.py --csv positions.csv       # output as CSV
    python run.py --no-color positions.csv  # disable color output
"""

import argparse
import sys
from pathlib import Path

from src.parser import parse_positions_file
from src.prices import fetch_price_data
from src.formatter import format_results, format_csv


def main():
    parser = argparse.ArgumentParser(
        description="Fetch latest prices and DMAs for your trading positions.",
        epilog="Supports IB TWS CSV exports, plain symbol lists, and standard CSVs.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to positions file (CSV or plain text list of symbols). "
             "Defaults to data/sample_positions.csv",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output results as CSV instead of formatted table",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    args = parser.parse_args()

    # Resolve file path
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            # Try relative to CWD first, then relative to script dir
            if not file_path.exists():
                alt = Path(__file__).parent / file_path
                if alt.exists():
                    file_path = alt
    else:
        file_path = Path(__file__).parent / "data" / "sample_positions.csv"

    # Parse positions
    print(f"Reading positions from: {file_path}")
    try:
        positions = parse_positions_file(file_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not positions:
        print("No equity/ETF/CFD positions found in file.")
        sys.exit(0)

    symbols = [p["symbol"] for p in positions]
    print(f"Found {len(symbols)} position(s): {', '.join(symbols)}")
    print("Fetching price data...\n")

    # Fetch prices
    results = fetch_price_data(symbols)

    # Output
    if args.csv:
        print(format_csv(results))
    else:
        use_color = not args.no_color and sys.stdout.isatty()
        print(format_results(results, use_color=use_color))


if __name__ == "__main__":
    main()
