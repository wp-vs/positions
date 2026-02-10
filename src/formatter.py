"""Format price/DMA data for terminal, HTML, and CSV output."""

from datetime import datetime
from .prices import PriceData

# ANSI color codes
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _fmt_price(val: float | None) -> str:
    if val is None:
        return "      N/A"
    return f"{val:>9.2f}"


def _fmt_pos(val: float | None) -> str:
    if val is None:
        return "     "
    if val == int(val):
        return f"{int(val):>5}"
    return f"{val:>5.0f}"


def _pct_from_dma(price: float | None, dma: float | None) -> str:
    """Show % distance from DMA."""
    if price is None or dma is None:
        return ""
    pct = ((price - dma) / dma) * 100
    sign = "+" if pct >= 0 else ""
    return f" ({sign}{pct:.1f}%)"


def format_results(
    results: list[PriceData],
    use_color: bool = True,
    excluded: list[dict] | None = None,
) -> str:
    """Format price data as a table with DMA highlighting.

    Positions trading below 9 DMA are highlighted in red.
    """
    if not results:
        return "No positions to display."

    # Check if we have descriptions/positions to show
    has_desc = any(r.description for r in results if not r.error)
    has_pos = any(r.position_size is not None for r in results if not r.error)

    lines = []

    # Determine close date from results for column header
    close_dates = [r.close_date for r in results if r.close_date and not r.error]
    close_label = f"Cls ({close_dates[0]})" if close_dates else "Prev Cls"

    # Build header
    parts = []
    parts.append(f"{'Symbol':<8}")
    if has_desc:
        parts.append(f"{'Name':<24}")
    if has_pos:
        parts.append(f"{'Pos':>5}")
    parts.append(f"{'Latest':>9}")
    parts.append(f"{close_label:>12}")
    parts.append(f"{'9 DMA':>9}")
    parts.append(f"{'21 DMA':>9}")
    parts.append(f"{'50 DMA':>9}")
    parts.append(f"  Status")

    header = " ".join(parts)
    separator = "-" * len(header)

    if use_color:
        lines.append(f"{BOLD}{header}{RESET}")
    else:
        lines.append(header)
    lines.append(separator)

    # Track alerts
    below_9dma = []
    errors = []

    for r in results:
        if r.error:
            errors.append(r)
            continue

        status = ""
        row_color = ""

        if r.below_9dma:
            status = "BELOW 9 DMA" + _pct_from_dma(r.latest_price, r.dma_9)
            row_color = RED
            below_9dma.append(r)
        elif r.dma_9 is not None and r.latest_price is not None:
            pct = ((r.latest_price - r.dma_9) / r.dma_9) * 100
            if pct < 1.0:
                status = f"Near 9 DMA (+{pct:.1f}%)"
                row_color = YELLOW

        row_parts = []
        row_parts.append(f"{r.symbol:<8}")
        if has_desc:
            desc = (r.description[:22] + "..") if len(r.description) > 24 else r.description
            row_parts.append(f"{desc:<24}")
        if has_pos:
            row_parts.append(f"{_fmt_pos(r.position_size)}")
        row_parts.append(f"{_fmt_price(r.latest_price)}")
        row_parts.append(f"{_fmt_price(r.close_price):>12}")
        row_parts.append(f"{_fmt_price(r.dma_9)}")
        row_parts.append(f"{_fmt_price(r.dma_21)}")
        row_parts.append(f"{_fmt_price(r.dma_50)}")
        row_parts.append(f"  {status}")

        row = " ".join(row_parts)

        if use_color and row_color:
            lines.append(f"{row_color}{row}{RESET}")
        else:
            lines.append(row)

    # Summary
    lines.append(separator)
    total = len(results) - len(errors)
    lines.append(f"Total positions: {total}")

    if below_9dma:
        alert = f"ALERT: {len(below_9dma)} position(s) trading BELOW 9 DMA:"
        symbols = ", ".join(r.symbol for r in below_9dma)
        if use_color:
            lines.append(f"{RED}{BOLD}{alert}{RESET} {symbols}")
        else:
            lines.append(f"{alert} {symbols}")

    if errors:
        lines.append("")
        err_header = "Errors (could not fetch data):"
        if use_color:
            lines.append(f"{DIM}{err_header}{RESET}")
        else:
            lines.append(err_header)
        for e in errors:
            msg = f"  {e.symbol}: {e.error}"
            if use_color:
                lines.append(f"{DIM}{msg}{RESET}")
            else:
                lines.append(msg)

    if excluded:
        lines.append("")
        exc_header = f"Other positions not included in scan ({len(excluded)}):"
        if use_color:
            lines.append(f"{DIM}{exc_header}{RESET}")
        else:
            lines.append(exc_header)
        for p in excluded:
            sym = p.get("symbol", "?")
            desc = p.get("description", "")
            asset = p.get("asset_class", "")
            pos = p.get("position")
            parts = [f"  {sym:<8}"]
            if desc:
                parts.append(f"{desc[:30]:<30}")
            if asset:
                parts.append(f"[{asset}]")
            if pos is not None:
                parts.append(f"qty: {pos:g}")
            msg = "  ".join(parts)
            if use_color:
                lines.append(f"{DIM}{msg}{RESET}")
            else:
                lines.append(msg)

    return "\n".join(lines)


def format_csv(results: list[PriceData]) -> str:
    """Format results as CSV for further processing."""
    close_dates = [r.close_date for r in results if r.close_date and not r.error]
    close_header = f"Close ({close_dates[0]})" if close_dates else "Prev Close"
    lines = [f"Symbol,Name,Position,Latest Price,{close_header},9 DMA,21 DMA,50 DMA,Below 9 DMA"]
    for r in results:
        if r.error:
            continue
        lines.append(
            f"{r.symbol},"
            f"\"{r.description}\","
            f"{r.position_size or ''},"
            f"{r.latest_price or ''},"
            f"{r.close_price or ''},"
            f"{r.dma_9 or ''},"
            f"{r.dma_21 or ''},"
            f"{r.dma_50 or ''},"
            f"{r.below_9dma}"
        )
    return "\n".join(lines)


def _html_price(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}"


def format_html(results: list[PriceData], excluded: list[dict] | None = None) -> str:
    """Format results as a self-contained HTML page with styled table."""
    if not results:
        return "<html><body><p>No positions to display.</p></body></html>"

    has_desc = any(r.description for r in results if not r.error)
    has_pos = any(r.position_size is not None for r in results if not r.error)

    valid = [r for r in results if not r.error]
    errors = [r for r in results if r.error]
    below_9dma = [r for r in valid if r.below_9dma]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine close date from results for column header
    close_dates = [r.close_date for r in valid if r.close_date]
    close_header = f"Close ({close_dates[0]})" if close_dates else "Prev Close"

    # Build table headers
    headers = ["Symbol"]
    if has_desc:
        headers.append("Name")
    if has_pos:
        headers.append("Pos")
    headers.extend(["Latest", close_header, "9 DMA", "21 DMA", "50 DMA", "Status"])

    header_cells = "".join(f"<th>{h}</th>" for h in headers)

    # Build table rows
    rows_html = []
    for r in valid:
        status = ""
        row_class = ""

        if r.below_9dma:
            status = "BELOW 9 DMA" + _pct_from_dma(r.latest_price, r.dma_9)
            row_class = "below-9dma"
        elif r.dma_9 is not None and r.latest_price is not None:
            pct = ((r.latest_price - r.dma_9) / r.dma_9) * 100
            if pct < 1.0:
                status = f"Near 9 DMA (+{pct:.1f}%)"
                row_class = "near-9dma"

        cells = [f"<td class='symbol'>{r.symbol}</td>"]
        if has_desc:
            cells.append(f"<td class='name'>{r.description}</td>")
        if has_pos:
            pos_str = f"{int(r.position_size)}" if r.position_size and r.position_size == int(r.position_size) else f"{r.position_size or ''}"
            cells.append(f"<td class='num'>{pos_str}</td>")
        cells.append(f"<td class='num'>{_html_price(r.latest_price)}</td>")
        cells.append(f"<td class='num'>{_html_price(r.close_price)}</td>")
        cells.append(f"<td class='num'>{_html_price(r.dma_9)}</td>")
        cells.append(f"<td class='num'>{_html_price(r.dma_21)}</td>")
        cells.append(f"<td class='num'>{_html_price(r.dma_50)}</td>")
        cells.append(f"<td class='status'>{status}</td>")

        class_attr = f" class='{row_class}'" if row_class else ""
        rows_html.append(f"<tr{class_attr}>{''.join(cells)}</tr>")

    # Alert section
    alert_html = ""
    if below_9dma:
        symbols = ", ".join(r.symbol for r in below_9dma)
        alert_html = f"""
        <div class="alert">
            {len(below_9dma)} position(s) trading BELOW 9 DMA: <strong>{symbols}</strong>
        </div>"""

    # Errors section
    errors_html = ""
    if errors:
        err_items = "".join(f"<li>{e.symbol}: {e.error}</li>" for e in errors)
        errors_html = f"""
        <div class="errors">
            <p>Could not fetch data:</p>
            <ul>{err_items}</ul>
        </div>"""

    # Excluded (non-equity) positions section
    excluded_html = ""
    if excluded:
        exc_rows = []
        for p in excluded:
            sym = p.get("symbol", "?")
            desc = p.get("description", "")
            asset = p.get("asset_class", "")
            pos = p.get("position")
            pos_str = f"{pos:g}" if pos is not None else ""
            exc_rows.append(
                f"<tr><td class='symbol'>{sym}</td>"
                f"<td>{desc}</td>"
                f"<td>{asset}</td>"
                f"<td class='num'>{pos_str}</td></tr>"
            )
        excluded_html = f"""
        <div class="excluded">
            <p>Other positions not included in scan ({len(excluded)}):</p>
            <table class="excluded-table">
                <thead><tr><th>Symbol</th><th>Description</th><th>Type</th><th>Qty</th></tr></thead>
                <tbody>{''.join(exc_rows)}</tbody>
            </table>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Position DMA Report - {timestamp}</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        max-width: 1200px;
        margin: 20px auto;
        padding: 0 20px;
        background: #f8f9fa;
        color: #212529;
    }}
    h1 {{
        font-size: 1.4em;
        color: #343a40;
        border-bottom: 2px solid #dee2e6;
        padding-bottom: 8px;
    }}
    .timestamp {{
        color: #6c757d;
        font-size: 0.85em;
        margin-bottom: 16px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        background: #fff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        font-size: 0.9em;
    }}
    th {{
        background: #343a40;
        color: #fff;
        padding: 10px 12px;
        text-align: left;
        font-weight: 600;
    }}
    td {{
        padding: 8px 12px;
        border-bottom: 1px solid #e9ecef;
    }}
    td.num {{
        text-align: right;
        font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
    }}
    td.symbol {{
        font-weight: 600;
    }}
    td.status {{
        font-weight: 600;
        font-size: 0.85em;
    }}
    tr:hover {{
        background: #f1f3f5;
    }}
    tr.below-9dma {{
        background: #fff5f5;
    }}
    tr.below-9dma td.status {{
        color: #c92a2a;
    }}
    tr.near-9dma {{
        background: #fffbeb;
    }}
    tr.near-9dma td.status {{
        color: #e67700;
    }}
    .summary {{
        margin-top: 12px;
        color: #495057;
        font-size: 0.9em;
    }}
    .alert {{
        margin-top: 12px;
        padding: 10px 14px;
        background: #fff5f5;
        border-left: 4px solid #c92a2a;
        color: #c92a2a;
        font-size: 0.9em;
    }}
    .errors {{
        margin-top: 12px;
        padding: 10px 14px;
        background: #f8f9fa;
        border-left: 4px solid #adb5bd;
        color: #6c757d;
        font-size: 0.85em;
    }}
    .errors ul {{
        margin: 4px 0 0 0;
        padding-left: 20px;
    }}
    .excluded {{
        margin-top: 20px;
        padding: 10px 14px;
        background: #f8f9fa;
        border-left: 4px solid #dee2e6;
        color: #6c757d;
        font-size: 0.85em;
    }}
    .excluded p {{
        margin: 0 0 8px 0;
        font-weight: 600;
        color: #495057;
    }}
    .excluded-table {{
        width: auto;
        font-size: 0.95em;
        box-shadow: none;
        background: transparent;
    }}
    .excluded-table th {{
        background: #6c757d;
        padding: 6px 10px;
    }}
    .excluded-table td {{
        padding: 4px 10px;
        border-bottom: 1px solid #dee2e6;
    }}
</style>
</head>
<body>
    <h1>Position DMA Report</h1>
    <div class="timestamp">Generated: {timestamp}</div>
    {alert_html}
    <table>
        <thead><tr>{header_cells}</tr></thead>
        <tbody>
            {''.join(rows_html)}
        </tbody>
    </table>
    <div class="summary">Total positions: {len(valid)}</div>
    {errors_html}
    {excluded_html}
</body>
</html>"""
