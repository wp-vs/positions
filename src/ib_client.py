"""Connect to IB TWS/Gateway via ib_async and fetch positions + historical data.

All operations are read-only — no orders or account modifications are made.
Works with the TWS "Read-Only API" setting enabled.
"""

from __future__ import annotations

import pandas as pd
from dataclasses import dataclass

from ib_async import IB, Contract, util


# Equity-like security types from IB
EQUITY_SEC_TYPES = {"STK", "CFD"}


@dataclass
class IBPosition:
    symbol: str
    description: str
    sec_type: str
    currency: str
    position: float
    avg_cost: float
    market_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    contract: Contract


def _silent_error_handler(reqId, errorCode, errorString, contract):
    """Swallow expected IB errors (e.g. 'No security definition found')."""
    pass


def connect(host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> IB:
    """Connect to TWS/IB Gateway in read-only mode.

    readonly=True avoids subscribing to account updates and open orders,
    which would require write API access in TWS.

    Default ports:
        TWS live:     7496
        TWS paper:    7497
        Gateway live: 4001
        Gateway paper:4002
    """
    ib = IB()
    ib.connect(host, port, clientId=client_id, readonly=True)
    return ib


def fetch_positions(ib: IB, equity_only: bool = True) -> tuple[list[IBPosition], list[IBPosition]]:
    """Fetch current positions from TWS using read-only API calls.

    Uses reqPositions() which is a one-shot read-only request.
    Then resolves contract details via reqContractDetails() (also read-only)
    to get long security names. Finally fetches market data snapshots for
    live prices.

    Returns:
        (equity_positions, excluded_positions) — excluded are non-equity
        positions (forex, options, futures, etc.) when equity_only=True.
    """
    # reqPositions() is a read-only request that returns all positions
    ib_positions = ib.reqPositions()

    positions = []
    excluded = []
    for pos in ib_positions:
        contract = pos.contract
        sec_type = contract.secType

        if equity_only and sec_type not in EQUITY_SEC_TYPES:
            excluded.append(IBPosition(
                symbol=contract.symbol,
                description=contract.localSymbol or contract.symbol,
                sec_type=sec_type,
                currency=contract.currency or "",
                position=pos.position,
                avg_cost=pos.avgCost,
                market_price=None,
                market_value=None,
                unrealized_pnl=None,
                contract=contract,
            ))
            continue

        positions.append(IBPosition(
            symbol=contract.symbol,
            description=contract.localSymbol or contract.symbol,
            sec_type=sec_type,
            currency=contract.currency or "",
            position=pos.position,
            avg_cost=pos.avgCost,
            market_price=None,
            market_value=None,
            unrealized_pnl=None,
            contract=contract,
        ))

    if not positions:
        return positions, excluded

    # Resolve full security names via reqContractDetails (read-only)
    # longName lives on ContractDetails, not on Contract itself.
    # Temporarily mute IB error events — some contracts (e.g. PINK sheet
    # preferreds) trigger "No security definition" errors that are expected.
    ib.errorEvent -= ib._onError
    ib.errorEvent += _silent_error_handler
    unresolved = []
    try:
        for p in positions:
            try:
                details_list = ib.reqContractDetails(p.contract)
                if details_list:
                    p.description = details_list[0].longName or p.description
                else:
                    unresolved.append(p.symbol)
            except Exception:
                unresolved.append(p.symbol)
    finally:
        ib.errorEvent -= _silent_error_handler
        ib.errorEvent += ib._onError

    if unresolved:
        print(f"  Note: Could not resolve details for: {', '.join(unresolved)}")

    # Fetch live price snapshots (read-only market data request)
    _fetch_market_snapshots(ib, positions)

    return positions, excluded


def _fetch_market_snapshots(ib: IB, positions: list[IBPosition]) -> None:
    """Fetch live price snapshots for all positions (read-only).

    Uses delayed/frozen market data (type 4) which doesn't require
    real-time market data subscriptions.
    """
    # Request delayed frozen data — works without paid market data subscriptions
    ib.reqMarketDataType(4)

    # Mute errors for contracts that may not support market data (e.g. PINK sheet)
    ib.errorEvent -= ib._onError
    ib.errorEvent += _silent_error_handler

    tickers = []
    for pos in positions:
        try:
            ticker = ib.reqMktData(pos.contract, snapshot=True)
            tickers.append((pos, ticker))
        except Exception:
            pass

    # Wait for snapshots to fill in (up to 5 seconds)
    ib.sleep(5.0)

    ib.errorEvent -= _silent_error_handler
    ib.errorEvent += ib._onError

    for pos, ticker in tickers:
        # Use last price, or close, or previous close — whichever is available
        price = None
        for field in [ticker.last, ticker.close, ticker.marketPrice()]:
            if field is not None and field == field and field > 0:  # not NaN
                price = float(field)
                break
        pos.market_price = price


def fetch_historical_bars(
    ib: IB,
    contract: Contract,
    duration: str = "100 D",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
) -> pd.DataFrame:
    """Fetch historical daily bars from IB for a single contract (read-only).

    Returns a DataFrame with columns: date, open, high, low, close, volume.
    """
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",  # now
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what_to_show,
        useRTH=True,  # regular trading hours only
        formatDate=1,
    )

    if not bars:
        return pd.DataFrame()

    df = util.df(bars)
    return df


def fetch_all_historical(
    ib: IB,
    positions: list[IBPosition],
    duration: str = "100 D",
) -> dict[str, pd.DataFrame]:
    """Fetch historical bars for all positions (read-only).

    Returns {symbol: DataFrame} mapping.
    IB has pacing limits (~60 requests per 10 minutes), so this throttles
    automatically via ib_async's built-in pacing.
    """
    history = {}
    for pos in positions:
        try:
            df = fetch_historical_bars(ib, pos.contract, duration=duration)
            if not df.empty:
                history[pos.symbol] = df
        except Exception as e:
            print(f"  Warning: Could not fetch history for {pos.symbol}: {e}")
    return history


def fetch_account_value(ib: IB) -> tuple[float | None, str]:
    """Fetch total account value (NetLiquidation) from TWS (read-only).

    Tries multiple approaches:
    1. reqAccountSummary (explicit subscription)
    2. accountValues() (auto-populated if account updates are active)

    Returns (net_liquidation_value, base_currency).
    """
    # Method 1: reqAccountSummary — explicit read-only subscription
    try:
        summary = ib.reqAccountSummary(
            group="All",
            tags="NetLiquidation",
        )
        # Wait longer for data to arrive — subscription fills asynchronously
        for _ in range(20):
            ib.sleep(0.5)
            if summary:
                break

        if summary:
            print(f"  reqAccountSummary returned {len(summary)} item(s):")
            for av in summary:
                print(f"    tag={av.tag}  value={av.value}  currency={av.currency}  account={av.account}")

            for av in summary:
                if av.tag == "NetLiquidation" and av.currency:
                    try:
                        val = float(av.value)
                        if val > 0:
                            try:
                                ib.cancelAccountSummary()
                            except Exception:
                                pass
                            return val, av.currency
                    except (ValueError, TypeError):
                        continue
        else:
            print("  reqAccountSummary returned no data after 10s")

        try:
            ib.cancelAccountSummary()
        except Exception:
            pass

    except Exception as e:
        print(f"  reqAccountSummary failed: {e}")

    # Method 2: Check accountValues() — populated if ib_async auto-subscribed
    try:
        acct_vals = ib.accountValues()
        if acct_vals:
            print(f"  Trying accountValues() ({len(acct_vals)} item(s))...")
            for av in acct_vals:
                if av.tag == "NetLiquidation" and av.currency and av.currency != "BASE":
                    try:
                        val = float(av.value)
                        if val > 0:
                            print(f"    Found NetLiquidation: {av.currency} {val}")
                            return val, av.currency
                    except (ValueError, TypeError):
                        continue
    except Exception as e:
        print(f"  accountValues() failed: {e}")

    print("  Warning: Could not retrieve account NAV from IB")
    print("  Tip: Use --nav <amount> to specify account NAV manually (in GBP)")
    return None, ""
