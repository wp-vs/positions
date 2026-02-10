"""Connect to IB TWS/Gateway via ib_async and fetch positions + historical data.

All operations are read-only — no orders or account modifications are made.
Works with the TWS "Read-Only API" setting enabled.
"""

from __future__ import annotations

import asyncio
import pandas as pd
from dataclasses import dataclass

from ib_async import IB, Stock, Contract, util


# Equity-like security types from IB
EQUITY_SEC_TYPES = {"STK", "CFD"}


@dataclass
class IBPosition:
    symbol: str
    description: str
    sec_type: str
    position: float
    avg_cost: float
    market_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    contract: Contract


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


def fetch_positions(ib: IB, equity_only: bool = True) -> list[IBPosition]:
    """Fetch current positions from TWS using read-only API calls.

    Uses reqPositions() which is a one-shot read-only request.
    Then resolves contract details via reqContractDetails() (also read-only)
    to get long security names. Finally fetches market data snapshots for
    live prices.
    """
    # reqPositions() is a read-only request that returns all positions
    ib_positions = ib.reqPositions()

    positions = []
    for pos in ib_positions:
        contract = pos.contract
        sec_type = contract.secType

        if equity_only and sec_type not in EQUITY_SEC_TYPES:
            continue

        positions.append(IBPosition(
            symbol=contract.symbol,
            description=contract.localSymbol or contract.symbol,
            sec_type=sec_type,
            position=pos.position,
            avg_cost=pos.avgCost,
            market_price=None,
            market_value=None,
            unrealized_pnl=None,
            contract=contract,
        ))

    if not positions:
        return positions

    # Resolve full security names via qualifyContracts (read-only: uses reqContractDetails)
    contracts_to_qualify = [p.contract for p in positions]
    ib.qualifyContracts(*contracts_to_qualify)
    for p in positions:
        if p.contract.longName:
            p.description = p.contract.longName

    # Fetch live price snapshots (read-only market data request)
    _fetch_market_snapshots(ib, positions)

    return positions


def _fetch_market_snapshots(ib: IB, positions: list[IBPosition]) -> None:
    """Fetch live price snapshots for all positions (read-only).

    Uses delayed/frozen market data (type 4) which doesn't require
    real-time market data subscriptions.
    """
    # Request delayed frozen data — works without paid market data subscriptions
    ib.reqMarketDataType(4)

    tickers = []
    for pos in positions:
        ticker = ib.reqMktData(pos.contract, snapshot=True)
        tickers.append((pos, ticker))

    # Wait for snapshots to fill in (up to 5 seconds)
    timeout = 5.0
    ib.sleep(timeout)

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
