#!/usr/bin/env python3
"""Fetch latest prices and moving averages for trading positions.

Usage:
    # From CSV file (default)
    python run.py                               # uses data/sample_positions.csv
    python run.py positions.csv                 # specify a positions file

    # From IB TWS (pulls positions + live prices directly)
    python run.py --ib                          # connect to TWS on default port 7497
    python run.py --ib --port 4001              # connect to IB Gateway live
    python run.py --ib --ib-history             # use IB for DMAs too (instead of yfinance)

    # Output options
    python run.py --csv                         # output as CSV
    python run.py --html report.html            # save as styled HTML file
    python run.py --email                       # email report (configure SMTP via .env)
    python run.py --email --email-to a@b.com    # email to specific address
    python run.py --no-color                    # disable color output
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.parser import parse_positions_file
from src.prices import PriceData, fetch_price_data, compute_dmas_from_history
from src.formatter import format_results, format_csv, format_html


def run_csv_mode(args):
    """Load positions from a CSV file and fetch prices via yfinance."""
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            if not file_path.exists():
                alt = Path(__file__).parent / file_path
                if alt.exists():
                    file_path = alt
    else:
        file_path = Path(__file__).parent / "data" / "sample_positions.csv"

    print(f"Reading positions from: {file_path}")
    try:
        positions, excluded = parse_positions_file(file_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not positions:
        print("No equity/ETF/CFD positions found in file.")
        sys.exit(0)

    symbols = [p["symbol"] for p in positions]
    descriptions = {p["symbol"]: p.get("description", "") for p in positions}
    position_sizes = {
        p["symbol"]: p["position"] for p in positions if "position" in p
    }

    if excluded:
        print(f"Skipped {len(excluded)} non-equity position(s)")
    print(f"Found {len(symbols)} equity position(s): {', '.join(symbols)}")
    print("Fetching price data via Yahoo Finance...\n")

    results = fetch_price_data(symbols, descriptions, position_sizes)
    return results, excluded


def run_ib_mode(args):
    """Pull positions directly from IB TWS and fetch DMAs."""
    try:
        from src.ib_client import connect, fetch_positions, fetch_all_historical
    except ImportError:
        print(
            "Error: ib_async is required for --ib mode.\n"
            "Install it with: pip install ib_async",
            file=sys.stderr,
        )
        sys.exit(1)

    host = args.host
    port = args.port
    client_id = args.client_id

    print(f"Connecting to IB TWS/Gateway at {host}:{port} (clientId={client_id})...")
    try:
        ib = connect(host, port, client_id)
    except Exception as e:
        print(f"Error: Could not connect to TWS/Gateway: {e}", file=sys.stderr)
        print(
            "\nMake sure TWS or IB Gateway is running with API enabled:\n"
            "  TWS: Edit > Global Configuration > API > Settings\n"
            "       - Enable ActiveX and Socket Clients\n"
            "       - Socket port: 7497 (paper) or 7496 (live)\n"
            "       - 'Read-Only API' can remain checked (only read access is needed)\n"
            "  Gateway: port 4002 (paper) or 4001 (live)",
            file=sys.stderr,
        )
        sys.exit(1)

    excluded = []
    try:
        print("Fetching portfolio positions...")
        positions, ib_excluded = fetch_positions(ib)

        if ib_excluded:
            print(f"Skipped {len(ib_excluded)} non-equity position(s)")
            excluded = [
                {"symbol": p.symbol, "description": p.description,
                 "asset_class": p.sec_type, "position": p.position}
                for p in ib_excluded
            ]

        if not positions:
            print("No equity/ETF/CFD positions found in your IB account.")
            ib.disconnect()
            sys.exit(0)

        print(f"Found {len(positions)} equity position(s):")
        for p in positions:
            price_str = f" @ {p.market_price:.2f}" if p.market_price else ""
            print(f"  {p.symbol:<8} {p.description:<30} {p.position:>8.0f}{price_str}")
        print()

        if args.ib_history:
            # Use IB historical data for DMAs
            print("Fetching historical data from IB (this may take a moment)...")
            history = fetch_all_historical(ib, positions)

            results = []
            for pos in positions:
                if pos.symbol in history:
                    result = compute_dmas_from_history(
                        symbol=pos.symbol,
                        hist=history[pos.symbol],
                        close_col="close",
                        latest_price=pos.market_price,
                        description=pos.description,
                        position_size=pos.position,
                    )
                else:
                    result = PriceData(
                        symbol=pos.symbol,
                        latest_price=pos.market_price,
                        close_price=None,
                        dma_9=None, dma_21=None, dma_50=None,
                        below_9dma=False,
                        description=pos.description,
                        position_size=pos.position,
                        error=f"No historical data from IB for {pos.symbol}",
                    )
                results.append(result)
            print()
        else:
            # Use yfinance for DMAs, IB for positions + live prices
            from src.exchanges import ib_to_yahoo_symbol

            symbols = [p.symbol for p in positions]
            descriptions = {p.symbol: p.description for p in positions}
            position_sizes = {p.symbol: p.position for p in positions}
            live_prices = {
                p.symbol: p.market_price for p in positions if p.market_price
            }

            # Map IB symbols to Yahoo Finance tickers using exchange info
            yahoo_symbols = {}
            for p in positions:
                yf_sym = ib_to_yahoo_symbol(
                    p.symbol,
                    exchange=p.contract.exchange or "",
                    currency=p.contract.currency or "",
                    primary_exchange=getattr(p.contract, "primaryExchange", "") or "",
                )
                if yf_sym != p.symbol:
                    yahoo_symbols[p.symbol] = yf_sym

            if yahoo_symbols:
                mapped = [f"{s} -> {y}" for s, y in yahoo_symbols.items()]
                print(f"Mapped non-US symbols for Yahoo Finance: {', '.join(mapped)}")

            print("Fetching historical data from Yahoo Finance for DMAs...\n")
            results = fetch_price_data(symbols, descriptions, position_sizes, yahoo_symbols)

            # Override latest price with IB live price where available
            for r in results:
                if r.symbol in live_prices:
                    r.latest_price = live_prices[r.symbol]
                    if r.dma_9 is not None:
                        r.below_9dma = r.latest_price < r.dma_9

            # Fall back to IB historical data for symbols yfinance couldn't find
            failed = [r for r in results if r.error]
            if failed:
                failed_symbols = {r.symbol for r in failed}
                failed_positions = [p for p in positions if p.symbol in failed_symbols]
                print(f"Falling back to IB historical data for {len(failed)} symbol(s) "
                      f"yfinance couldn't resolve: {', '.join(sorted(failed_symbols))}")
                ib_history = fetch_all_historical(ib, failed_positions)

                for i, r in enumerate(results):
                    if r.error and r.symbol in ib_history:
                        results[i] = compute_dmas_from_history(
                            symbol=r.symbol,
                            hist=ib_history[r.symbol],
                            close_col="close",
                            latest_price=live_prices.get(r.symbol),
                            description=descriptions.get(r.symbol, ""),
                            position_size=position_sizes.get(r.symbol),
                        )
                print()

    finally:
        ib.disconnect()
        print("Disconnected from IB.\n")

    return results, excluded


def main():
    parser = argparse.ArgumentParser(
        description="Fetch latest prices and DMAs for your trading positions.",
        epilog="Supports IB TWS live connection, CSV exports, and plain symbol lists.",
    )

    # Source options
    source = parser.add_argument_group("data source")
    source.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to positions file (CSV or plain text symbol list). "
             "Defaults to data/sample_positions.csv. Ignored when --ib is used.",
    )
    source.add_argument(
        "--ib",
        action="store_true",
        help="Pull positions directly from IB TWS/Gateway instead of a file",
    )
    source.add_argument(
        "--ib-history",
        action="store_true",
        help="Use IB historical data for DMAs (default: use Yahoo Finance for DMAs)",
    )

    # IB connection options
    ib_conn = parser.add_argument_group("IB connection (used with --ib)")
    ib_conn.add_argument(
        "--host",
        default="127.0.0.1",
        help="TWS/Gateway host (default: 127.0.0.1)",
    )
    ib_conn.add_argument(
        "--port",
        type=int,
        default=7497,
        help="TWS/Gateway port (default: 7497 for TWS paper trading)",
    )
    ib_conn.add_argument(
        "--client-id",
        type=int,
        default=1,
        help="API client ID (default: 1)",
    )

    # Output options
    output = parser.add_argument_group("output")
    output.add_argument(
        "--csv",
        action="store_true",
        help="Output results as CSV instead of formatted table",
    )
    output.add_argument(
        "--html",
        nargs="?",
        const="auto",
        default=None,
        metavar="FILE",
        help="Save results as styled HTML to reports/ directory "
             "(optionally specify a custom filename)",
    )
    output.add_argument(
        "--email",
        action="store_true",
        help="Email the HTML report (configure SMTP via environment variables, see .env.example)",
    )
    output.add_argument(
        "--email-to",
        default=None,
        metavar="ADDR",
        help="Override recipient email address (default: EMAIL_TO env var)",
    )
    output.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    args = parser.parse_args()

    # Run in appropriate mode
    if args.ib:
        results, excluded = run_ib_mode(args)
    else:
        results, excluded = run_csv_mode(args)

    # Output — multiple flags can be combined
    if args.html:
        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)

        if args.html == "auto":
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            html_path = reports_dir / f"report_{ts}.html"
        else:
            html_path = reports_dir / Path(args.html).name

        html = format_html(results, excluded=excluded)
        html_path.write_text(html)
        print(f"HTML report saved to: {html_path}")

    if args.email:
        from src.emailer import send_report
        html = format_html(results, excluded=excluded)
        try:
            send_report(html, recipient=args.email_to)
            target = args.email_to or "(from EMAIL_TO env var)"
            print(f"Report emailed to: {target}")
        except ValueError as e:
            print(f"Email config error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Failed to send email: {e}", file=sys.stderr)
            sys.exit(1)

    if args.csv:
        print(format_csv(results))
    else:
        # Always show the table to terminal (even alongside --html/--email)
        use_color = not args.no_color and sys.stdout.isatty()
        print(format_results(results, use_color=use_color, excluded=excluded))


if __name__ == "__main__":
    main()
