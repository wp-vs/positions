"""Fetch latest prices and calculate moving averages using yfinance."""

import yfinance as yf
import pandas as pd
from dataclasses import dataclass


@dataclass
class PriceData:
    symbol: str
    latest_price: float | None
    close_price: float | None
    dma_9: float | None
    dma_21: float | None
    dma_50: float | None
    below_9dma: bool
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return self.latest_price is not None


def fetch_price_data(symbols: list[str]) -> list[PriceData]:
    """Fetch price data and DMAs for a list of symbols.

    Uses yfinance to pull ~70 days of daily history (enough for 50 DMA)
    and computes 9, 21, and 50 day simple moving averages.

    Returns a PriceData for each symbol (with error info if fetch failed).
    """
    results = []

    # Batch download for efficiency
    if not symbols:
        return results

    ticker_str = " ".join(symbols)

    try:
        data = yf.download(
            ticker_str,
            period="4mo",  # ~80 trading days, enough for 50 DMA
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as e:
        # If batch download fails, fall back to individual
        for symbol in symbols:
            results.append(_fetch_single(symbol))
        return results

    for symbol in symbols:
        results.append(_extract_price_data(symbol, data, len(symbols) == 1))

    return results


def _fetch_single(symbol: str) -> PriceData:
    """Fetch data for a single symbol (fallback)."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="4mo")
        if hist.empty:
            return PriceData(
                symbol=symbol,
                latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None,
                below_9dma=False,
                error=f"No data found for {symbol}",
            )
        return _compute_from_history(symbol, hist)
    except Exception as e:
        return PriceData(
            symbol=symbol,
            latest_price=None, close_price=None,
            dma_9=None, dma_21=None, dma_50=None,
            below_9dma=False,
            error=str(e),
        )


def _extract_price_data(symbol: str, data: pd.DataFrame, single: bool) -> PriceData:
    """Extract price data for a symbol from batch download results."""
    try:
        if single:
            hist = data
        else:
            if symbol not in data.columns.get_level_values(0):
                return PriceData(
                    symbol=symbol,
                    latest_price=None, close_price=None,
                    dma_9=None, dma_21=None, dma_50=None,
                    below_9dma=False,
                    error=f"No data found for {symbol}",
                )
            hist = data[symbol]

        hist = hist.dropna(how="all")
        if hist.empty:
            return PriceData(
                symbol=symbol,
                latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None,
                below_9dma=False,
                error=f"No data found for {symbol}",
            )

        return _compute_from_history(symbol, hist)

    except Exception as e:
        return PriceData(
            symbol=symbol,
            latest_price=None, close_price=None,
            dma_9=None, dma_21=None, dma_50=None,
            below_9dma=False,
            error=str(e),
        )


def _compute_from_history(symbol: str, hist: pd.DataFrame) -> PriceData:
    """Compute latest price, close, and DMAs from historical data."""
    close = hist["Close"].dropna()

    if close.empty:
        return PriceData(
            symbol=symbol,
            latest_price=None, close_price=None,
            dma_9=None, dma_21=None, dma_50=None,
            below_9dma=False,
            error=f"No close data for {symbol}",
        )

    latest_price = float(close.iloc[-1])
    close_price = float(close.iloc[-1])

    # If we have intraday data, latest != close of previous day
    # With daily data, latest_price = most recent close
    # The previous trading day's close
    if len(close) >= 2:
        prev_close = float(close.iloc[-2])
    else:
        prev_close = close_price

    # Compute SMAs
    dma_9 = float(close.rolling(window=9).mean().iloc[-1]) if len(close) >= 9 else None
    dma_21 = float(close.rolling(window=21).mean().iloc[-1]) if len(close) >= 21 else None
    dma_50 = float(close.rolling(window=50).mean().iloc[-1]) if len(close) >= 50 else None

    below_9dma = dma_9 is not None and latest_price < dma_9

    return PriceData(
        symbol=symbol,
        latest_price=latest_price,
        close_price=prev_close,
        dma_9=dma_9,
        dma_21=dma_21,
        dma_50=dma_50,
        below_9dma=below_9dma,
    )
