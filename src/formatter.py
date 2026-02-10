"""Format price/DMA data for terminal output."""

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
        return "   N/A"
    return f"{val:>10.2f}"


def _pct_from_dma(price: float | None, dma: float | None) -> str:
    """Show % distance from DMA."""
    if price is None or dma is None:
        return ""
    pct = ((price - dma) / dma) * 100
    sign = "+" if pct >= 0 else ""
    return f" ({sign}{pct:.1f}%)"


def format_results(results: list[PriceData], use_color: bool = True) -> str:
    """Format price data as a table with DMA highlighting.

    Positions trading below 9 DMA are highlighted in red.
    """
    if not results:
        return "No positions to display."

    lines = []

    # Header
    header = (
        f"{'Symbol':<8} {'Latest':>10} {'Prev Close':>10} "
        f"{'9 DMA':>10} {'21 DMA':>10} {'50 DMA':>10}  Status"
    )
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

        row = (
            f"{r.symbol:<8} "
            f"{_fmt_price(r.latest_price)} "
            f"{_fmt_price(r.close_price)} "
            f"{_fmt_price(r.dma_9)} "
            f"{_fmt_price(r.dma_21)} "
            f"{_fmt_price(r.dma_50)}  "
            f"{status}"
        )

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

    return "\n".join(lines)


def format_csv(results: list[PriceData]) -> str:
    """Format results as CSV for further processing."""
    lines = ["Symbol,Latest Price,Prev Close,9 DMA,21 DMA,50 DMA,Below 9 DMA"]
    for r in results:
        if r.error:
            continue
        lines.append(
            f"{r.symbol},"
            f"{r.latest_price or ''},"
            f"{r.close_price or ''},"
            f"{r.dma_9 or ''},"
            f"{r.dma_21 or ''},"
            f"{r.dma_50 or ''},"
            f"{r.below_9dma}"
        )
    return "\n".join(lines)
