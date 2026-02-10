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
    close_date: str | None = None
    exposure_gbp: float | None = None
    pct_of_capital: float | None = None
    currency: str = ""
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
    yahoo_symbols: dict[str, str] | None = None,
) -> list[PriceData]:
    """Fetch price data and DMAs for a list of symbols via yfinance.

    Uses yfinance to pull ~80 trading days of daily history (enough for 50 DMA)
    and computes 9, 21, and 50 day simple moving averages.

    Args:
        symbols: List of position symbols (as displayed, e.g. "RWE")
        descriptions: {symbol: description} mapping
        position_sizes: {symbol: quantity} mapping
        yahoo_symbols: {symbol: yahoo_ticker} mapping for non-US stocks
                       (e.g. {"RWE": "RWE.DE", "PRY": "PRY.MI"})
    """
    descriptions = descriptions or {}
    position_sizes = position_sizes or {}
    yahoo_symbols = yahoo_symbols or {}
    results = []

    if not symbols:
        return results

    # Build the list of Yahoo tickers to download
    yf_tickers = [yahoo_symbols.get(s, s) for s in symbols]
    # Map Yahoo ticker back to display symbol
    yf_to_display = {yahoo_symbols.get(s, s): s for s in symbols}

    ticker_str = " ".join(yf_tickers)

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
            yf_sym = yahoo_symbols.get(symbol, symbol)
            results.append(_fetch_single(
                symbol, descriptions.get(symbol, ""), position_sizes.get(symbol),
                yf_ticker=yf_sym,
            ))
        return results

    for symbol in symbols:
        yf_sym = yahoo_symbols.get(symbol, symbol)
        results.append(_extract_price_data(
            symbol, data, len(symbols) == 1,
            descriptions.get(symbol, ""), position_sizes.get(symbol),
            yf_ticker=yf_sym,
        ))

    return results


def _fetch_single(
    symbol: str, description: str = "", position_size: float | None = None,
    yf_ticker: str | None = None,
) -> PriceData:
    """Fetch data for a single symbol (fallback)."""
    lookup = yf_ticker or symbol
    try:
        ticker = yf.Ticker(lookup)
        hist = ticker.history(period="4mo")
        if hist.empty:
            return PriceData(
                symbol=symbol, latest_price=None, close_price=None,
                dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                description=description, position_size=position_size,
                error=f"No data found for {symbol} (tried {lookup})",
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
    yf_ticker: str | None = None,
) -> PriceData:
    """Extract price data for a symbol from batch download results."""
    # Use Yahoo ticker for looking up in batch data, display symbol for output
    lookup = yf_ticker or symbol
    try:
        if single:
            hist = data
        else:
            # Try Yahoo ticker first, then display symbol
            if lookup in data.columns.get_level_values(0):
                hist = data[lookup]
            elif symbol in data.columns.get_level_values(0):
                hist = data[symbol]
            else:
                return PriceData(
                    symbol=symbol, latest_price=None, close_price=None,
                    dma_9=None, dma_21=None, dma_50=None, below_9dma=False,
                    description=description, position_size=position_size,
                    error=f"No data found for {symbol} (tried {lookup})",
                )

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


def fetch_fx_rates(currencies: set[str], target: str = "GBP") -> dict[str, float]:
    """Fetch FX rates to convert each currency to the target currency via yfinance.

    Returns {currency: rate} where rate * amount_in_currency = amount_in_target.
    For example, if target='GBP' and currency='USD', rate ~0.79.
    """
    rates = {target: 1.0}
    to_fetch = currencies - {target}

    if not to_fetch:
        return rates

    # Try batch download first — more reliable than individual Ticker lookups.
    # Yahoo Finance uses standard pair conventions (e.g. GBPUSD=X not USDGBP=X),
    # so we try the inverse pair (target+ccy) and invert the rate.
    tickers_inv = {ccy: f"{target}{ccy}=X" for ccy in to_fetch}
    ticker_str = " ".join(tickers_inv.values())

    try:
        data = yf.download(ticker_str, period="5d", progress=False, threads=True)
        for ccy, pair in tickers_inv.items():
            try:
                if len(tickers_inv) == 1:
                    close = data["Close"].dropna()
                else:
                    close = data["Close"][pair].dropna() if pair in data["Close"].columns else pd.Series()
                if not close.empty:
                    inv_rate = float(close.iloc[-1])
                    if inv_rate > 0:
                        rates[ccy] = 1.0 / inv_rate
            except Exception:
                pass
    except Exception:
        pass

    # For any currencies still missing, try direct pair (ccy+target)
    still_missing = to_fetch - set(rates.keys())
    if still_missing:
        tickers_direct = {ccy: f"{ccy}{target}=X" for ccy in still_missing}
        ticker_str = " ".join(tickers_direct.values())
        try:
            data = yf.download(ticker_str, period="5d", progress=False, threads=True)
            for ccy, pair in tickers_direct.items():
                try:
                    if len(tickers_direct) == 1:
                        close = data["Close"].dropna()
                    else:
                        close = data["Close"][pair].dropna() if pair in data["Close"].columns else pd.Series()
                    if not close.empty:
                        rate = float(close.iloc[-1])
                        if rate > 0:
                            rates[ccy] = rate
                except Exception:
                    pass
        except Exception:
            pass

    # Last resort — individual ticker lookups for anything still missing
    still_missing = to_fetch - set(rates.keys())
    for ccy in still_missing:
        for pair, invert in [(f"{target}{ccy}=X", True), (f"{ccy}{target}=X", False)]:
            try:
                hist = yf.Ticker(pair).history(period="5d")
                if not hist.empty:
                    val = float(hist["Close"].dropna().iloc[-1])
                    if val > 0:
                        rates[ccy] = (1.0 / val) if invert else val
                        break
            except Exception:
                continue

    return rates
