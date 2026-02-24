# Swing Trade Scanner

A stock market swing trade scanner that screens for stocks with high upside potential using programmatic sector analysis and technical filters.

## Quick Start

### 1. Get an API Key (free, 2 minutes)

1. Go to [financialmodelingprep.com](https://financialmodelingprep.com/)
2. Click "Get Free API Key"
3. Sign up and copy your API key

### 2. Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Open .env and paste your API key
```

### 3. Run

```bash
python app.py
```

Open **http://localhost:5000** in your browser and click **Run Scan**.

## What It Does

The scanner runs a 4-step pipeline:

1. **Sector Analysis** - Finds sectors outperforming the S&P 500
2. **Stock Screening** - Filters stocks by market cap, volume, and exchange
3. **Enrichment** - Gets price history, calculates distance from all-time high
4. **Ranking** - Scores and ranks top candidates by conviction level

## Output

Each scan produces:
- **HTML report** - Color-coded table of top 10-15 picks
- **CSV download** - For spreadsheets and tracking
- **JSON archive** - Saved to `output/` folder

## Scan Criteria

| Filter | Value |
|--------|-------|
| Market Cap | > $1 billion |
| Daily Volume | > 500,000 shares |
| Exchange | NYSE, NASDAQ |
| Distance from ATH | 15-50% below |
| Sectors | Outperforming S&P 500 |

All filter values are adjustable from the Settings panel in the UI.

## Recommended Workflow

1. Run the scanner weekly (Sunday evening)
2. Review the top 10-15 picks
3. Run picks through [Chaikin Power Gauge](https://chaikinanalytics.com/) as a confirmation filter
4. Stocks that pass both = your watchlist for the week

## Scoring

Each stock gets a conviction score (0-100) based on:

| Factor | Weight |
|--------|--------|
| Upside potential (distance to ATH) | 35% |
| Value positioning (52-week range) | 30% |
| Sector strength | 20% |
| Volume trend (accumulation signal) | 15% |

## API Usage

The free tier of Financial Modeling Prep gives you **250 API calls per day**. Each scan uses approximately 150-200 calls depending on how many stocks match the initial sector filter. You can run 1-2 scans per day on the free tier.
