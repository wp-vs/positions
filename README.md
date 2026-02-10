# Position Price & DMA Monitor

Pulls trading positions (from IB TWS or a CSV file) and displays the latest price, previous close, and 9/21/50 day moving averages for all equities, ETFs, and CFDs. Highlights positions trading below the 9 DMA.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### From IB TWS (recommended)

Connects directly to TWS/IB Gateway via the API — pulls positions, live prices, and security names automatically.

```bash
# Connect to TWS paper trading (default port 7497)
python run.py --ib

# Connect to IB Gateway (live)
python run.py --ib --port 4001

# Use IB historical data for DMAs (instead of Yahoo Finance)
python run.py --ib --ib-history

# Custom connection
python run.py --ib --host 127.0.0.1 --port 7496 --client-id 2
```

**TWS setup required**: Edit > Global Configuration > API > Settings:
- Enable ActiveX and Socket Clients
- Socket port: 7497 (paper) / 7496 (live)
- Uncheck "Read-Only API" if you want full access

**IB Gateway ports**: 4002 (paper) / 4001 (live)

#### DMA data source

By default `--ib` pulls positions and live prices from IB, then uses Yahoo Finance for the historical data needed to compute DMAs. Add `--ib-history` to use IB's own historical data instead:

| Flag | Positions | Live Price | DMA History |
|------|-----------|------------|-------------|
| `--ib` | IB | IB | Yahoo Finance |
| `--ib --ib-history` | IB | IB | IB |

### From a CSV file

```bash
# Use the sample positions file
python run.py

# Point to your own file
python run.py /path/to/your/positions.csv

# Output as CSV for further processing
python run.py --csv positions.csv
```

### Input file formats

The CSV parser accepts several formats:

**Simple symbol list** (one ticker per line):
```
AAPL
MSFT
SPY
```

**Standard CSV with headers**:
```csv
Symbol,Description,Asset Class,Position,Avg Cost
AAPL,APPLE INC,STK,100,178.50
MSFT,MICROSOFT CORP,STK,50,380.25
```

**IB TWS exports**: Rebalance export, Activity Statement CSV, and page content exports are all auto-detected.

## Output

```
Symbol   Name                       Pos    Latest  Prev Cls    9 DMA   21 DMA   50 DMA  Status
-----------------------------------------------------------------------------------------------
AAPL     APPLE INC                  100    178.72   177.15   179.84   176.32   174.50  BELOW 9 DMA (-0.6%)
MSFT     MICROSOFT CORP              50    415.30   413.50   412.80   408.20   401.15
SPY      SPDR S&P 500 ETF           200    512.40   510.80   513.10   508.40   502.30  BELOW 9 DMA (-0.1%)
-----------------------------------------------------------------------------------------------
Total positions: 3
ALERT: 2 position(s) trading BELOW 9 DMA: AAPL, SPY
```

- Red: below 9 DMA
- Yellow: within 1% of 9 DMA

## Data sources

| Source | Latency | Notes |
|--------|---------|-------|
| IB TWS (`--ib`) | Real-time | Requires TWS/Gateway running with API enabled |
| Yahoo Finance (default) | ~15 min delay | No setup needed, free |
