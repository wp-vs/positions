"""Connect to IB TWS/Gateway via ib_async and fetch positions + historical data."""

from __future__ import annotations

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
    """Connect to TWS/IB Gateway.

    Default ports:
        TWS live:     7496
        TWS paper:    7497
        Gateway live: 4001
        Gateway paper:4002
    """
    ib = IB()
    ib.connect(host, port, clientId=client_id)
    return ib


def fetch_positions(ib: IB, equity_only: bool = True) -> list[IBPosition]:
    """Fetch current portfolio positions from TWS.

    Uses ib.portfolio() which provides market price and P&L alongside positions.
    Falls back to ib.positions() if portfolio data isn't available.
    """
    positions = []

    # portfolio() gives us the richest data (includes market price, P&L)
    portfolio_items = ib.portfolio()

    if portfolio_items:
        for item in portfolio_items:
            contract = item.contract
            sec_type = contract.secType

            if equity_only and sec_type not in EQUITY_SEC_TYPES:
                continue

            # Qualify the contract to get the full description
            description = contract.localSymbol or contract.symbol

            positions.append(IBPosition(
                symbol=contract.symbol,
                description=description,
                sec_type=sec_type,
                position=item.position,
                avg_cost=item.averageCost,
                market_price=item.marketPrice,
                market_value=item.marketValue,
                unrealized_pnl=item.unrealizedPNL,
                contract=contract,
            ))
    else:
        # Fallback to positions() — less data but always available
        for pos in ib.positions():
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

    # Resolve long names via qualifyContracts
    contracts_to_qualify = [p.contract for p in positions]
    if contracts_to_qualify:
        ib.qualifyContracts(*contracts_to_qualify)
        for p in positions:
            if p.contract.longName:
                p.description = p.contract.longName

    return positions


def fetch_historical_bars(
    ib: IB,
    contract: Contract,
    duration: str = "100 D",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
) -> pd.DataFrame:
    """Fetch historical daily bars from IB for a single contract.

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
    """Fetch historical bars for all positions.

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
