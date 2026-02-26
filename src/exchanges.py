"""Map IB exchange codes to EODHD ticker suffixes."""

# IB exchange code -> EODHD exchange code
# EODHD tickers use the format SYMBOL.EXCHANGE (e.g. "AAPL.US", "VOD.LSE")
IB_TO_EODHD_EXCHANGE: dict[str, str] = {
    # North America
    "SMART": "US",
    "NYSE": "US",
    "NASDAQ": "US",
    "ARCA": "US",
    "AMEX": "US",
    "BATS": "US",
    "IEX": "US",
    "TSE": "TO",          # Toronto Stock Exchange (also Tokyo — disambiguated by currency below)
    "VENTURE": "V",       # TSX Venture
    "MEXI": "MX",         # Mexican Stock Exchange

    # UK & Ireland
    "LSE": "LSE",           # London Stock Exchange
    "LSEETF": "LSE",        # London Stock Exchange (ETFs)
    "ISBX": "LSE",          # London (IOB)

    # Germany
    "IBIS": "XETRA",        # XETRA
    "IBIS2": "XETRA",
    "FWB": "F",              # Frankfurt
    "FWB2": "F",
    "SWB": "STU",            # Stuttgart
    "SWB2": "STU",

    # France
    "SBF": "PA",             # Euronext Paris
    "SBFETH": "PA",

    # Netherlands
    "AEB": "AS",             # Euronext Amsterdam
    "AEBETH": "AS",

    # Belgium
    "EBR": "BR",             # Euronext Brussels

    # Italy
    "BVME": "MI",            # Borsa Italiana / Milan

    # Spain
    "BM": "MC",              # Bolsa de Madrid

    # Switzerland
    "EBS": "SW",             # SIX Swiss Exchange
    "VIRTX": "SW",

    # Nordics
    "SFB": "ST",             # Stockholm (Nasdaq Nordic)
    "CSE": "CO",             # Copenhagen
    "HEX": "HE",             # Helsinki
    "OSE": "OL",             # Oslo

    # Asia-Pacific
    "SEHK": "HK",            # Hong Kong
    "SEHKNTL": "HK",
    "SEHKSZSE": "SHE",       # Shenzhen via SEHK
    "TSEJ": "TSE",           # Tokyo
    "ASX": "AU",             # Australian Securities Exchange
    "SGX": "SG",             # Singapore
    "KSE": "KO",             # Korea (KOSPI)
    "KOSDAQ": "KQ",          # Korea (KOSDAQ)
    "NSE": "NSE",            # National Stock Exchange of India
    "BSE": "BSE",            # Bombay Stock Exchange

    # Other
    "PINK": "US",             # OTC Pink Sheets (US)
    "OTCBB": "US",            # OTC Bulletin Board (US)
    "VALUE": "US",            # US OTC
    "BVL": "LS",              # Lisbon
    "VSE": "VI",              # Vienna
    "WSE": "WAR",             # Warsaw
}

# EODHD exchanges that quote prices in fractional currency (pence/GBX).
# Prices from these exchanges must be divided by 100 to get pounds.
PENCE_QUOTED_EXCHANGES = {"LSE"}


def ib_to_eodhd_symbol(
    symbol: str,
    exchange: str = "",
    currency: str = "",
    primary_exchange: str = "",
) -> str:
    """Convert an IB symbol + exchange to an EODHD ticker.

    EODHD tickers use the format SYMBOL.EXCHANGE (e.g. "VOD.LSE", "AAPL.US").

    Args:
        symbol: IB ticker symbol (e.g. "VOD")
        exchange: IB exchange code (e.g. "LSE")
        currency: Trading currency (e.g. "GBP")
        primary_exchange: IB primary exchange (sometimes more specific)

    Returns:
        EODHD ticker (e.g. "VOD.LSE")
    """
    # Try primary exchange first (more specific), then exchange
    for exch in [primary_exchange, exchange]:
        exch = exch.upper().strip()
        if not exch:
            continue
        # TSE is ambiguous: Toronto (CAD) vs Tokyo (JPY)
        if exch == "TSE":
            cur = currency.upper().strip()
            if cur == "JPY":
                return f"{symbol}.TSE"
            else:
                return f"{symbol}.TO"
        if exch in IB_TO_EODHD_EXCHANGE:
            eodhd_exch = IB_TO_EODHD_EXCHANGE[exch]
            return f"{symbol}.{eodhd_exch}"

    # Fallback: guess from currency
    currency_exchange = {
        "GBP": "LSE",
        "GBX": "LSE",    # GBP pence
        "EUR": "XETRA",  # Default EUR to XETRA (most liquid)
        "CHF": "SW",
        "HKD": "HK",
        "JPY": "TSE",
        "AUD": "AU",
        "CAD": "TO",
        "SEK": "ST",
        "NOK": "OL",
        "DKK": "CO",
        "SGD": "SG",
        "INR": "NSE",
    }

    cur = currency.upper().strip()
    if cur in currency_exchange:
        return f"{symbol}.{currency_exchange[cur]}"

    # If USD or unknown, return US default
    return f"{symbol}.US"
