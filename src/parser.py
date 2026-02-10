"""Parse position files exported from IB TWS or manually created CSVs."""

import csv
import re
from pathlib import Path

# Asset classes we care about (equities, ETFs, CFDs on equities)
EQUITY_ASSET_CLASSES = {"STK", "EQUITY", "ETF", "CFD", "STOCK"}

# Common column name mappings - IB exports use varied naming
SYMBOL_COLUMNS = {"symbol", "ticker", "financial instrument", "contract", "underlying"}
ASSET_CLASS_COLUMNS = {"asset class", "sectype", "sec type", "security type", "type", "asset category"}
POSITION_COLUMNS = {"position", "quantity", "qty", "shares"}


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _find_column(headers: list[str], candidates: set[str]) -> int | None:
    """Find the index of a column matching any of the candidate names."""
    for i, h in enumerate(headers):
        if _normalize_header(h) in candidates:
            return i
    return None


def _detect_delimiter(file_path: Path) -> str:
    with open(file_path, "r") as f:
        sample = f.read(2048)
    # Check tab first since CSVs might contain commas in descriptions
    if "\t" in sample:
        tab_count = sample.count("\t")
        comma_count = sample.count(",")
        if tab_count > comma_count:
            return "\t"
    return ","


def _is_equity_type(asset_class: str) -> bool:
    """Check if an asset class string represents equity/ETF/CFD."""
    val = asset_class.strip().upper()
    if val in EQUITY_ASSET_CLASSES:
        return True
    # IB sometimes uses longer descriptions
    for keyword in ("STOCK", "EQUITY", "ETF", "CFD"):
        if keyword in val:
            return True
    return False


def _clean_symbol(raw: str) -> str:
    """Clean up a ticker symbol from IB format."""
    symbol = raw.strip().upper()
    # Remove exchange suffix (e.g., "AAPL.NASDAQ" or "AAPL NASDAQ")
    symbol = re.split(r"[.\s]", symbol)[0]
    # Remove any non-alphanumeric except common ticker chars (., -)
    symbol = re.sub(r"[^A-Z0-9.\-/]", "", symbol)
    return symbol


def parse_positions_file(file_path: str | Path) -> list[dict]:
    """Parse a positions file and return equity/ETF/CFD symbols.

    Supports:
    - Simple CSV: Symbol,Description,Asset Class,Position,Avg Cost
    - IB TWS rebalance export
    - IB Activity Statement CSV (filters to Open Positions section)
    - Plain text list of symbols (one per line)

    Returns a list of dicts with at minimum {"symbol": "AAPL"}.
    Additional fields (position, avg_cost, description) included when available.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Positions file not found: {file_path}")

    content = file_path.read_text().strip()
    if not content:
        raise ValueError(f"Positions file is empty: {file_path}")

    # Try plain text list first (one symbol per line, no commas/tabs)
    lines = content.splitlines()
    if all(re.match(r"^[A-Za-z0-9.\-/]+$", line.strip()) for line in lines if line.strip()):
        return [{"symbol": _clean_symbol(line)} for line in lines if line.strip()]

    # CSV parsing
    delimiter = _detect_delimiter(file_path)

    # Check if this is an IB Activity Statement (has section headers)
    if _is_activity_statement(content):
        return _parse_activity_statement(file_path, delimiter)

    return _parse_standard_csv(file_path, delimiter)


def _is_activity_statement(content: str) -> bool:
    """Detect IB Activity Statement format (sections like 'Open Positions')."""
    return "Open Positions" in content and "Header" in content


def _parse_activity_statement(file_path: Path, delimiter: str) -> list[dict]:
    """Parse IB Activity Statement CSV, extracting Open Positions section."""
    positions = []
    in_positions_section = False
    headers = []

    with open(file_path, "r", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if len(row) < 2:
                continue

            section = row[0].strip()
            row_type = row[1].strip()

            if "Open Positions" in section:
                if row_type == "Header":
                    headers = [h.strip().lower() for h in row]
                    in_positions_section = True
                    continue
                elif row_type == "Data" and in_positions_section:
                    pos = _extract_position_from_row(row, headers)
                    if pos:
                        positions.append(pos)
            elif in_positions_section and section != "Open Positions":
                in_positions_section = False

    return positions


def _parse_standard_csv(file_path: Path, delimiter: str) -> list[dict]:
    """Parse a standard CSV with headers."""
    positions = []

    with open(file_path, "r", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        raw_headers = next(reader, None)
        if not raw_headers:
            return []

        headers = [_normalize_header(h) for h in raw_headers]

        sym_idx = _find_column(raw_headers, SYMBOL_COLUMNS)
        asset_idx = _find_column(raw_headers, ASSET_CLASS_COLUMNS)
        pos_idx = _find_column(raw_headers, POSITION_COLUMNS)

        if sym_idx is None:
            # Fall back: assume first column is symbol
            sym_idx = 0

        for row in reader:
            if len(row) <= sym_idx:
                continue

            symbol = _clean_symbol(row[sym_idx])
            if not symbol:
                continue

            # Filter by asset class if column exists
            if asset_idx is not None and len(row) > asset_idx:
                if not _is_equity_type(row[asset_idx]):
                    continue

            pos = {"symbol": symbol}

            # Extract optional fields
            if pos_idx is not None and len(row) > pos_idx:
                try:
                    pos["position"] = float(row[pos_idx].replace(",", ""))
                except ValueError:
                    pass

            # Look for description
            desc_idx = None
            for i, h in enumerate(headers):
                if h in ("description", "desc", "name", "security name"):
                    desc_idx = i
                    break
            if desc_idx is not None and len(row) > desc_idx:
                pos["description"] = row[desc_idx].strip()

            # Look for avg cost
            for i, h in enumerate(headers):
                if h in ("avg cost", "average cost", "cost basis", "avg price"):
                    try:
                        pos["avg_cost"] = float(row[i].replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                    break

            positions.append(pos)

    return positions


def _extract_position_from_row(row: list[str], headers: list[str]) -> dict | None:
    """Extract a position dict from an activity statement row."""
    sym_idx = _find_column(headers, SYMBOL_COLUMNS)
    asset_idx = _find_column(headers, ASSET_CLASS_COLUMNS)

    if sym_idx is None:
        return None

    if len(row) <= sym_idx:
        return None

    # Filter to equities only
    if asset_idx is not None and len(row) > asset_idx:
        if not _is_equity_type(row[asset_idx]):
            return None

    symbol = _clean_symbol(row[sym_idx])
    if not symbol:
        return None

    pos = {"symbol": symbol}

    pos_idx = _find_column(headers, POSITION_COLUMNS)
    if pos_idx is not None and len(row) > pos_idx:
        try:
            pos["position"] = float(row[pos_idx].replace(",", ""))
        except ValueError:
            pass

    return pos
