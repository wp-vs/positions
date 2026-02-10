"""Map IB exchange codes to Yahoo Finance ticker suffixes."""

# IB exchange code -> Yahoo Finance suffix
# Sources: IB exchange list, Yahoo Finance exchange list (SLN2310)
IB_TO_YAHOO_SUFFIX: dict[str, str] = {
    # North America (no suffix needed for major US exchanges)
    "SMART": "",
    "NYSE": "",
    "NASDAQ": "",
    "ARCA": "",
    "AMEX": "",
    "BATS": "",
    "IEX": "",
    "TSE": ".TO",          # Toronto Stock Exchange (also Tokyo — disambiguated by currency below)
    "VENTURE": ".V",       # TSX Venture
    "MEXI": ".MX",         # Mexican Stock Exchange

    # UK & Ireland
    "LSE": ".L",            # London Stock Exchange
    "LSEETF": ".L",         # London Stock Exchange (ETFs)
    "ISBX": ".L",           # London (IOB)

    # Germany
    "IBIS": ".DE",           # XETRA
    "IBIS2": ".DE",          # XETRA
    "FWB": ".F",             # Frankfurt
    "FWB2": ".F",
    "SWB": ".SG",            # Stuttgart
    "SWB2": ".SG",

    # France
    "SBF": ".PA",            # Euronext Paris
    "SBFETH": ".PA",

    # Netherlands
    "AEB": ".AS",            # Euronext Amsterdam
    "AEBETH": ".AS",

    # Belgium
    "BVME": ".MI",           # Borsa Italiana / Milan (note: BVME is IB's code)
    "EBR": ".BR",            # Euronext Brussels

    # Italy
    "BVME": ".MI",           # Borsa Italiana / Milan

    # Spain
    "BM": ".MC",             # Bolsa de Madrid

    # Switzerland
    "EBS": ".SW",            # SIX Swiss Exchange
    "VIRTX": ".SW",

    # Nordics
    "SFB": ".ST",            # Stockholm (Nasdaq Nordic)
    "CSE": ".CO",            # Copenhagen
    "HEX": ".HE",            # Helsinki
    "OSE": ".OL",            # Oslo

    # Asia-Pacific
    "SEHK": ".HK",           # Hong Kong
    "SEHKNTL": ".HK",
    "SEHKSZSE": ".SZ",       # Shenzhen via SEHK
    # Note: "TSE" for Tokyo is handled via currency fallback (JPY -> .T)
    # since IB uses "TSE" for both Toronto and Tokyo.
    "TSEJ": ".T",             # Tokyo
    "ASX": ".AX",             # Australian Securities Exchange
    "SGX": ".SI",             # Singapore
    "KSE": ".KS",             # Korea (KOSPI)
    "KOSDAQ": ".KQ",          # Korea (KOSDAQ)
    "NSE": ".NS",             # National Stock Exchange of India
    "BSE": ".BO",             # Bombay Stock Exchange

    # Other
    "PINK": "",               # OTC Pink Sheets (US)
    "OTCBB": "",              # OTC Bulletin Board (US)
    "VALUE": "",              # US OTC
    "MEXI": ".MX",            # Mexico
    "BVL": ".LS",             # Lisbon
    "VSE": ".VI",             # Vienna
    "WSE": ".WA",             # Warsaw
}


def ib_to_yahoo_symbol(
    symbol: str,
    exchange: str = "",
    currency: str = "",
    primary_exchange: str = "",
) -> str:
    """Convert an IB symbol + exchange to a Yahoo Finance ticker.

    Uses the exchange code to determine the suffix. Falls back to
    currency-based guessing if the exchange isn't in our mapping.

    Args:
        symbol: IB ticker symbol (e.g. "RWE")
        exchange: IB exchange code (e.g. "IBIS")
        currency: Trading currency (e.g. "EUR")
        primary_exchange: IB primary exchange (sometimes more specific)

    Returns:
        Yahoo Finance ticker (e.g. "RWE.DE")
    """
    # Try primary exchange first (more specific), then exchange
    for exch in [primary_exchange, exchange]:
        exch = exch.upper().strip()
        # TSE is ambiguous: Toronto (CAD) vs Tokyo (JPY)
        if exch == "TSE":
            cur = currency.upper().strip()
            if cur == "JPY":
                return f"{symbol}.T"
            else:
                return f"{symbol}.TO"
        if exch in IB_TO_YAHOO_SUFFIX:
            suffix = IB_TO_YAHOO_SUFFIX[exch]
            if suffix:
                return f"{symbol}{suffix}"
            return symbol

    # Fallback: guess from currency
    currency_suffix = {
        "GBP": ".L",
        "GBX": ".L",    # GBP pence
        "EUR": ".DE",   # Default EUR to XETRA (most liquid)
        "CHF": ".SW",
        "HKD": ".HK",
        "JPY": ".T",
        "AUD": ".AX",
        "CAD": ".TO",
        "SEK": ".ST",
        "NOK": ".OL",
        "DKK": ".CO",
        "SGD": ".SI",
        "INR": ".NS",
    }

    cur = currency.upper().strip()
    if cur in currency_suffix:
        return f"{symbol}{currency_suffix[cur]}"

    # If USD or unknown, return bare symbol (US default)
    return symbol
