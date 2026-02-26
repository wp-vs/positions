"""Fetch latest prices and calculate moving averages using EODHD or IB data."""

import os
import requests
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

EODHD_BASE = "https://eodhd.com/api"

# EODHD exchanges that quote in pence (GBX) — divide by 100 to get pounds
PENCE_QUOTED_EXCHANGES = {"LSE"}


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
    close_date: str | None = None
    exposure_gbp: float | None = None
    pct_of_capital: float | None = None
    currency: str = ""
    loss_to_9dma: float | None = None
    loss_to_21dma: float | None = None
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return self.latest_price is not None


def _get_api_token() -> str:
    """Get EODHD API token from environment."""
    token = os.environ.get("EODHD_API_KEY", "")
    if not token:
        raise ValueError(
            "EODHD_API_KEY environment variable not set. "
            "Get your API key from https://eodhd.com/ and set it:\n"
            "  export EODHD_API_KEY=your_api_key_here"
        )
    return token


def _is_pence_quoted(eodhd_symbol: str) -> bool:
    """Check if an EODHD symbol is quoted in pence (fractional currency).

    LSE stocks are quoted in GBX (pence). We divide by 100 to get pounds
    so that prices are consistent with IB (which reports in GBP).
    """
    parts = eodhd_symbol.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].upper() in PENCE_QUOTED_EXCHANGES
    return False


def _fetch_eodhd_history(
    eodhd_symbol: str, api_token: str, days: int = 150,
) -> pd.DataFrame:
    """Fetch historical EOD data from EODHD.

    Args:
        eodhd_symbol: EODHD ticker (e.g. "AAPL.US", "VOD.LSE")
        api_token: EODHD API key
        days: Number of calendar days of history to fetch

    Returns:
        DataFrame with date index and close/open/high/low/volume columns.
        For LSE stocks, prices are converted from pence to pounds.
    """
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{EODHD_BASE}/eod/{eodhd_symbol}"
    params = {
        "from": date_from,
        "period": "d",
        "api_token": api_token,
        "fmt": "json",
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # Convert pence to pounds for LSE stocks
    if _is_pence_quoted(eodhd_symbol):
        for col in ["open", "high", "low", "close", "adjusted_close"]:
            if col in df.columns:
                df[col] = df[col] / 100.0

    return df


def compute_dmas_from_history(
    symbol: str,
    hist: pd.DataFrame,
    close_col: str = "Close",
    latest_price: float | None = None,
    description: str = "",
    position_size: float | None = None,
) -> PriceData:
    """Compute DMAs from a history DataFrame (works with both EODHD and IB data).

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

    # Extract the date of the previous close
    close_date = None
    if len(close) >= 2:
        idx = close.index[-2]
        if hasattr(idx, 'strftime'):
            close_date = idx.strftime("%d %b")
    elif len(close) == 1:
        idx = close.index[-1]
        if hasattr(idx, 'strftime'):
            close_date = idx.strftime("%d %b")

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
        close_date=close_date,
    )


def fetch_price_data(
    symbols: list[str],
    descriptions: dict[str, str] | None = None,
    position_sizes: dict[str, float] | None = None,
    eodhd_symbols: dict[str, str] | None = None,
) -> list[PriceData]:
    """Fetch price data and DMAs for a list of symbols via EODHD.

    Uses EODHD to pull ~100 trading days of daily history (enough for 50 DMA)
    and computes 9, 21, and 50 day simple moving averages.

    Args:
        symbols: List of position symbols (as displayed, e.g. "RWE")
        descriptions: {symbol: description} mapping
        position_sizes: {symbol: quantity} mapping
        eodhd_symbols: {symbol: eodhd_ticker} mapping for exchange resolution
                       (e.g. {"RWE": "RWE.XETRA", "VOD": "VOD.LSE"})
                       Symbols not in this mapping default to SYMBOL.US
    """
    descriptions = descriptions or {}
    position_sizes = position_sizes or {}
    eodhd_symbols = eodhd_symbols or {}
    results = []

    if not symbols:
        return results

    try:
        api_token = _get_api_token()
    except ValueError as e:
        for symbol in symbols:
            results.append(PriceData(
                symbol=symbol, latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                description=descriptions.get(symbol, ""),
                position_size=position_sizes.get(symbol),
                error=str(e),
            ))
        return results

    def _fetch_one(symbol: str) -> PriceData:
        eodhd_sym = eodhd_symbols.get(symbol, f"{symbol}.US")
        try:
            hist = _fetch_eodhd_history(eodhd_sym, api_token)
            if hist.empty:
                return PriceData(
                    symbol=symbol, latest_price=None, close_price=None,
                    dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                    description=descriptions.get(symbol, ""),
                    position_size=position_sizes.get(symbol),
                    error=f"No data from EODHD for {eodhd_sym}",
                )
            return compute_dmas_from_history(
                symbol, hist, close_col="close",
                description=descriptions.get(symbol, ""),
                position_size=position_sizes.get(symbol),
            )
        except Exception as e:
            return PriceData(
                symbol=symbol, latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                description=descriptions.get(symbol, ""),
                position_size=position_sizes.get(symbol),
                error=f"EODHD error for {eodhd_sym}: {e}",
            )

    # Fetch all symbols in parallel (EODHD has no batch endpoint)
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_symbol = {executor.submit(_fetch_one, s): s for s in symbols}
        result_map = {}
        for future in as_completed(future_to_symbol):
            sym = future_to_symbol[future]
            result_map[sym] = future.result()

    # Return in original order
    results = [result_map[s] for s in symbols]
    return results


def fetch_fx_rates(currencies: set[str], target: str = "GBP") -> dict[str, float]:
    """Fetch FX rates to convert each currency to the target currency via EODHD.

    Returns {currency: rate} where rate * amount_in_currency = amount_in_target.
    For example, if target='GBP' and currency='USD', rate ~0.79.
    """
    rates = {target: 1.0}
    to_fetch = currencies - {target}

    if not to_fetch:
        return rates

    try:
        api_token = _get_api_token()
    except ValueError:
        return rates

    date_from = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    for ccy in to_fetch:
        # Try direct pair first: CCYTARGET (e.g. USDGBP → rate * USD = GBP)
        # Then inverse pair: TARGETCCY (e.g. GBPUSD → need to invert)
        for pair, invert in [(f"{ccy}{target}", False), (f"{target}{ccy}", True)]:
            try:
                url = f"{EODHD_BASE}/eod/{pair}.FOREX"
                params = {
                    "from": date_from,
                    "period": "d",
                    "api_token": api_token,
                    "fmt": "json",
                }
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    val = float(data[-1]["close"])
                    if val > 0:
                        rates[ccy] = (1.0 / val) if invert else val
                        break
            except Exception:
                continue

    return rates
