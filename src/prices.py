"""Fetch latest prices and calculate moving averages using yfinance or IB data."""

import yfinance as yf
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class PriceData:
    symbol: str
    latest_price: float | None
    close_price: float | None
    dma_9: float | None
    dma_21: float | None
    dma_50: float | None
    below_9dma: bool
    description: str = ""
    position_size: float | None = None
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return self.latest_price is not None


def compute_dmas_from_history(
    symbol: str,
    hist: pd.DataFrame,
    close_col: str = "Close",
    latest_price: float | None = None,
    description: str = "",
    position_size: float | None = None,
) -> PriceData:
    """Compute DMAs from a history DataFrame (works with both yfinance and IB data).

    Args:
        symbol: Ticker symbol
        hist: DataFrame with at least a close price column
        close_col: Name of the close price column
        latest_price: Override for the latest price (e.g. live price from IB)
        description: Security name/description
        position_size: Position quantity
    """
    # Normalize column name - handle case-insensitive matching
    col = None
    for c in hist.columns:
        if str(c).lower() == close_col.lower():
            col = c
            break
    if col is None:
        return PriceData(
            symbol=symbol, latest_price=latest_price, close_price=None,
            dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
            description=description, position_size=position_size,
            error=f"No '{close_col}' column in history",
        )

    close = hist[col].dropna()

    if close.empty:
        return PriceData(
            symbol=symbol, latest_price=latest_price, close_price=None,
            dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
            description=description, position_size=position_size,
            error=f"No close data for {symbol}",
        )

    last_hist_close = float(close.iloc[-1])

    # Use provided live price if available, otherwise use last historical close
    effective_price = latest_price if latest_price is not None else last_hist_close

    # Previous close = second-to-last bar
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_hist_close

    # Compute SMAs
    dma_9 = float(close.rolling(window=9).mean().iloc[-1]) if len(close) >= 9 else None
    dma_21 = float(close.rolling(window=21).mean().iloc[-1]) if len(close) >= 21 else None
    dma_50 = float(close.rolling(window=50).mean().iloc[-1]) if len(close) >= 50 else None

    below_9dma = dma_9 is not None and effective_price < dma_9

    return PriceData(
        symbol=symbol,
        latest_price=effective_price,
        close_price=prev_close,
        dma_9=dma_9,
        dma_21=dma_21,
        dma_50=dma_50,
        below_9dma=below_9dma,
        description=description,
        position_size=position_size,
    )


def fetch_price_data(
    symbols: list[str],
    descriptions: dict[str, str] | None = None,
    position_sizes: dict[str, float] | None = None,
) -> list[PriceData]:
    """Fetch price data and DMAs for a list of symbols via yfinance.

    Uses yfinance to pull ~80 trading days of daily history (enough for 50 DMA)
    and computes 9, 21, and 50 day simple moving averages.
    """
    descriptions = descriptions or {}
    position_sizes = position_sizes or {}
    results = []

    if not symbols:
        return results

    ticker_str = " ".join(symbols)

    try:
        data = yf.download(
            ticker_str,
            period="4mo",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception:
        for symbol in symbols:
            results.append(_fetch_single(
                symbol, descriptions.get(symbol, ""), position_sizes.get(symbol),
            ))
        return results

    for symbol in symbols:
        results.append(_extract_price_data(
            symbol, data, len(symbols) == 1,
            descriptions.get(symbol, ""), position_sizes.get(symbol),
        ))

    return results


def _fetch_single(
    symbol: str, description: str = "", position_size: float | None = None,
) -> PriceData:
    """Fetch data for a single symbol (fallback)."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="4mo")
        if hist.empty:
            return PriceData(
                symbol=symbol, latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                description=description, position_size=position_size,
                error=f"No data found for {symbol}",
            )
        return compute_dmas_from_history(
            symbol, hist, description=description, position_size=position_size,
        )
    except Exception as e:
        return PriceData(
            symbol=symbol, latest_price=None, close_price=None,
            dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
            description=description, position_size=position_size,
            error=str(e),
        )


def _extract_price_data(
    symbol: str,
    data: pd.DataFrame,
    single: bool,
    description: str = "",
    position_size: float | None = None,
) -> PriceData:
    """Extract price data for a symbol from batch download results."""
    try:
        if single:
            hist = data
        else:
            if symbol not in data.columns.get_level_values(0):
                return PriceData(
                    symbol=symbol, latest_price=None, close_price=None,
                    dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                    description=description, position_size=position_size,
                    error=f"No data found for {symbol}",
                )
            hist = data[symbol]

        hist = hist.dropna(how="all")
        if hist.empty:
            return PriceData(
                symbol=symbol, latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                description=description, position_size=position_size,
                error=f"No data found for {symbol}",
            )

        return compute_dmas_from_history(
            symbol, hist, description=description, position_size=position_size,
        )

    except Exception as e:
        return PriceData(
            symbol=symbol, latest_price=None, close_price=None,
            dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
            description=description, position_size=position_size,
            error=str(e),
        )
