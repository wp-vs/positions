# Position Price & DMA Monitor

Reads a file of trading positions and fetches the latest price, previous close, and 9/21/50 day moving averages for all equities, ETFs, and CFDs. Highlights positions trading below the 9 DMA.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Use the sample positions file
python run.py

# Point to your own file
python run.py /path/to/your/positions.csv

# Output as CSV for further processing
python run.py --csv positions.csv

# Disable terminal colors
python run.py --no-color
```

## Input File Formats

The tool accepts several formats:

### 1. Simple symbol list (one ticker per line)
```
AAPL
MSFT
SPY
TSLA
```

### 2. Standard CSV with headers
```csv
Symbol,Description,Asset Class,Position,Avg Cost
AAPL,APPLE INC,STK,100,178.50
MSFT,MICROSOFT CORP,STK,50,380.25
SPY,SPDR S&P 500 ETF,STK,200,450.00
```

### 3. IB TWS Rebalance Export
Export from TWS via the Rebalance Portfolio window (File > Export). The tool auto-detects the format.

### 4. IB Activity Statement CSV
Export an Activity Flex Query as CSV from Client Portal. The tool extracts the "Open Positions" section and filters to equities.

## Output

```
Symbol    Latest  Prev Close     9 DMA    21 DMA    50 DMA  Status
----------------------------------------------------------------------
AAPL      178.72     177.15    179.84    176.32    174.50  BELOW 9 DMA (-0.6%)
MSFT      415.30     413.50    412.80    408.20    401.15
SPY       512.40     510.80    513.10    508.40    502.30  BELOW 9 DMA (-0.1%)
----------------------------------------------------------------------
Total positions: 3
ALERT: 2 position(s) trading BELOW 9 DMA: AAPL, SPY
```

Positions below the 9 DMA are highlighted in red in the terminal. Positions within 1% of the 9 DMA are shown in yellow.

## Data Source

Price data is fetched via [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance). Data is typically delayed ~15 minutes for US equities.

## Feeding positions from IB TWS

You can manually export positions from TWS:
1. **Quick method**: Right-click your portfolio/watchlist in TWS > Export Page Contents
2. **Rebalance export**: Open Rebalance Portfolio window > click Export
3. **Flex Query**: Client Portal > Reports > Flex Queries > create an Activity query with Open Positions, export as CSV

Save/copy the file to the `data/` directory or pass the path directly to `run.py`.
