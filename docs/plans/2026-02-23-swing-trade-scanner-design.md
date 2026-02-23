# Swing Trade Scanner - Design Document

**Date**: 2026-02-23
**Status**: Approved

## Problem

Dad wants an AI-powered swing trade scanner that produces a clean, one-page report of the top 10-15 stocks to trade. Previous attempts in Claude Chat failed because Claude has no access to real-time financial data APIs. The scanner needs to do programmatic quantitative screening, not manual web searches.

## Solution

A Flask web app backed by the Financial Modeling Prep (FMP) API that:
1. Screens the market programmatically using sector performance and stock screener endpoints
2. Enriches candidates with quote and historical price data
3. Scores and ranks by a composite metric (sector strength, distance from ATH, volume, value positioning)
4. Outputs a clean HTML report table + downloadable CSV

## Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Data API | Financial Modeling Prep (free tier) | 250 calls/day, stock screener endpoint, sector performance, historical prices. Best free option. |
| Backend | Python + Flask | Natural for financial data work. Flask is lightweight, dad-friendly. |
| Frontend | Vanilla HTML/CSS/JS (served by Flask) | No build tools, no framework. Single page, clean UI. |
| AI narratives | Phase 2 | MVP is data-only. Add Claude API qualitative analysis later. |
| Output | HTML report + CSV download | HTML for reading, CSV for spreadsheets/tracking. |

## Screening Pipeline

### Step 1 - Sector Filter (1 API call)
- `/v3/sectors-performance` to get sector performance
- Identify sectors outperforming the S&P 500

### Step 2 - Stock Screener (1-3 API calls)
- `/v3/stock-screener` per winning sector
- Filters: marketCap > $1B, volume > 500K, actively trading, NYSE/NASDAQ
- Produces candidate pool of ~50-150 stocks

### Step 3 - Enrich & Score (~50-150 API calls)
- `/v3/quote/{symbol}` for current price, 52-week high/low
- `/v3/historical-price-full/{symbol}?timeseries=365` for ATH calculation
- Calculate: % below ATH, % below 52-week high, price position in range

### Step 4 - Rank & Filter
- Keep stocks 15-50% below ATH
- Score by: sector strength, proximity to 52-week low, volume trend, upside potential
- Rank and take top 10-15

**API budget**: ~155 calls per scan. Fits within 250/day free tier.

## Output Table Columns

| Column | Source |
|--------|--------|
| Ticker & Name | FMP profile |
| Sector | FMP screener |
| Sector vs S&P 500 | Calculated |
| Current Price | FMP quote |
| 52-Week High | FMP quote |
| % Below ATH | Calculated from historical data |
| Entry Price | Current price |
| Target Price | ATH or 52-week high |
| Potential Upside % | Calculated |
| Conviction Score | Composite ranking score |

## UI

- Single page: header, "Run Scan" button, results table, download buttons
- Loading spinner with progress messages during scan
- Color-coded conviction levels (green/yellow/standard)
- Expandable rows for data detail
- Settings area for API key and filter adjustments

## Project Structure

```
swing-trade-scanner/
├── app.py              # Flask routes, main entry point
├── scanner.py          # Core screening pipeline
├── fmp_client.py       # FMP API wrapper
├── scoring.py          # Ranking/scoring algorithms
├── templates/
│   └── index.html      # UI (HTML + CSS + JS)
├── output/             # Saved reports
├── .env.example        # API key template
├── .gitignore
├── requirements.txt    # Flask, requests, python-dotenv
└── README.md           # Setup instructions
```

## Future Phases

- **Phase 2**: Claude API integration for analyst narratives + Ignition Signals scoring
- **Phase 2**: SAM.gov API for government contract tracking
- **Phase 3**: Automated weekly scheduling + email delivery
- **Phase 3**: Backtesting framework for historical validation
