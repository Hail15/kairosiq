# KairosIQ

**Geopolitical Intelligence Platform — Pre-Event Signal Detection for Institutional Investors**

KairosIQ detects geopolitical events before they reach public awareness by monitoring multiple independent intelligence sources simultaneously. When sources converge on the same theme, the platform fires a signal and maps it to historically correlated financial assets via a B2B API.

---

## Live Demo

**Dashboard:** [kairosiq.streamlit.app](https://kairosiq.streamlit.app)

---

## How It Works

KairosIQ monitors 15+ independent data sources every 15 minutes. When multiple sources converge on the same geopolitical theme, a signal fires with asset mappings, historical accuracy data, and an AI-generated intelligence brief.

### Signal Sources

| Source | What It Detects |
|--------|----------------|
| **GDELT** | Conflict article spikes — country-level anomaly detection vs 30-day baseline |
| **Options Flow** | Unusual institutional options positioning — put/call ratio extremes |
| **Smart vs Dumb Money** | Divergence between institutional and retail options positioning |
| **Correlation Monitor** | Breakdown of Gold-Treasury, Gold-Equity, Treasury-Equity correlations |
| **Unpriced Risk** | Gap between KairosIQ GPI (geopolitical pressure index) and VIX |
| **Someone Knows** | Cross-source convergence — when unrelated sources confirm the same event |
| **Silence Detector** | Unusual absence of expected state media output |
| **State Media** | Narrative shifts in TASS, RT, Xinhua, Global Times, PressTV, KCNA |
| **News Intelligence** | Reuters, AP, WSJ, FT, BBC, NYT, CNBC, Guardian, Al Jazeera |
| **Cloudflare Radar** | Internet disruption and connectivity anomalies by country |
| **Marine Traffic** | Shipping lane anomalies — Hormuz, Suez, Red Sea |
| **Baltic Dry Index** | Global dry bulk shipping demand anomalies |
| **ACLED** | Armed conflict and protest event data |
| **USGS** | Seismic events with geopolitical relevance |
| **WHO Outbreak** | Disease outbreak alerts |
| **CFTC COT** | Commitment of Traders — institutional positioning in futures |
| **FRED Economic** | Macro economic data anomalies |
| **Congressional Trades** | STOCK Act disclosures — committee members trading geopolitically sensitive assets |
| **Forward Calendar** | Upcoming geopolitical events, elections, central bank decisions |

### Signal Tiers

- **EXTREME** — 4+ independent sources confirm the same event (highest confidence)
- **HIGH** — Full convergence, strong historical precedent
- **MEDIUM** — Dual confirmation, financially relevant

### Asset Mappings

Every signal maps to historically correlated financial assets with:
- Average move at 24h / 72h / 168h
- Directional accuracy (% of historical instances correct)
- Sample size (number of historical instances)
- Combined Pattern Indicator score (RSI + volume + price action)

Covers 90+ tickers across equities, ETFs, commodities, FX, and fixed income.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    RAILWAY                          │
│  scheduler.py — runs every 15 minutes               │
│  ├── 15+ ingestion modules                          │
│  ├── signal_engine.py                               │
│  ├── convergence_engine.py                          │
│  ├── cascade_engine.py                              │
│  ├── regime_detector.py                             │
│  ├── unpriced_risk.py                               │
│  ├── smart_money.py                                 │
│  ├── someone_knows.py                               │
│  ├── silence_detector.py                            │
│  ├── correlation_monitor.py                         │
│  ├── signal_validator.py                            │
│  ├── email_alert.py → Telegram alerts               │
│  └── exit_alert.py → position exit alerts           │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│              SUPABASE / POSTGRESQL                  │
│  signals, probability_snapshots, asset_mappings,   │
│  alpaca_trades, signal_outcomes, congress_trades,   │
│  signal_alerts_sent, signal_briefs                  │
└───────────────────┬─────────────────────────────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
┌──────────────────┐  ┌─────────────────────┐
│ STREAMLIT CLOUD  │  │   FASTAPI (Railway) │
│  app.py          │  │   api_main.py        │
│  Dashboard       │  │   B2B API layer      │
└──────────────────┘  └─────────────────────┘
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend scheduler | Python 3.9, Railway |
| Database | Supabase (PostgreSQL), psycopg2 |
| Dashboard | Streamlit Cloud |
| API | FastAPI + Uvicorn |
| AI briefs | Claude Sonnet (Anthropic) |
| Market data | yfinance, Alpha Vantage |
| Alerts | Telegram Bot API |
| Deployment | Railway (scheduler), Streamlit Cloud (dashboard), GitHub auto-deploy |

---

## Project Structure

```
kairosiq/
│
├── scheduler.py              # Main scheduler — runs every 15 min
├── config.py                 # Environment config
├── schema.sql                # Database schema
│
├── ingestion/
│   ├── polymarket.py         # Polymarket prediction market ingestion
│   ├── kalshi.py             # Kalshi prediction market ingestion
│   ├── metaculus.py          # Metaculus forecast ingestion
│   ├── gdelt.py              # GDELT conflict spike detection
│   ├── state_media.py        # State media RSS monitoring
│   ├── ofac.py               # Global news intelligence (Reuters, AP, WSJ, FT, BBC, etc.)
│   ├── options_flow.py       # Unusual options flow detection
│   ├── cloudflare_radar.py   # Internet disruption detection
│   ├── marine_traffic.py     # Shipping lane anomaly detection
│   ├── baltic_dry.py         # Baltic Dry Index monitoring
│   ├── acled.py              # Armed conflict event data
│   ├── usgs.py               # Seismic event monitoring
│   ├── who_outbreak.py       # WHO disease outbreak alerts
│   ├── cftc_cot.py           # CFTC Commitment of Traders
│   ├── fred_economic.py      # FRED macro economic data
│   ├── congress_trades.py    # Congressional stock disclosures
│   └── forward_calendar.py   # Upcoming geopolitical events
│
├── signals/
│   ├── signal_engine.py      # Core signal detection
│   ├── signal_validator.py   # Validates signal outcomes vs actual asset moves
│   ├── signal_logger.py      # Signal lifecycle management
│   ├── convergence_engine.py # Multi-source convergence detection
│   ├── cascade_engine.py     # Second/third order effect chain detection
│   ├── regime_detector.py    # Macro regime detection (risk-on/off override)
│   ├── correlation_monitor.py# Asset correlation breakdown detection
│   ├── someone_knows.py      # Cross-source intelligence convergence
│   ├── silence_detector.py   # State media silence anomaly detection
│   ├── smart_money.py        # Smart vs dumb money divergence
│   ├── unpriced_risk.py      # GPI vs VIX gap detection
│   └── prediction_engine.py  # Prediction market outcome forecasting
│
├── processing/
│   ├── asset_mapper.py       # Event → asset mapping + signal metadata
│   └── asset_mappings.csv    # Historical asset correlation data (90+ tickers)
│
├── alerts/
│   ├── email_alert.py        # Signal alert logic + Telegram dispatch
│   ├── telegram_alert.py     # Telegram message formatting
│   └── exit_alert.py         # Position exit / stop loss alerts
│
├── bets/
│   ├── bet_recommender.py    # Historical pattern trade recommendations
│   ├── bet_logger.py         # Trade logging
│   └── alpaca_trader.py      # Alpaca paper/live trade execution
│
├── dashboard/
│   └── app.py                # Streamlit dashboard (6 pages, 15 tabs)
│
└── api/
    └── api_main.py           # FastAPI B2B API layer
```

---

## Setup

### Prerequisites

- Python 3.9+
- PostgreSQL (Supabase recommended)
- Railway account (scheduler deployment)
- Streamlit Cloud account (dashboard deployment)

### Environment Variables

Create a `.env` file (never commit this):

```env
DATABASE_URL=postgresql://...
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
KALSHI_API_KEY=...
KALSHI_PRIVATE_KEY=...
POLYMARKET_API_KEY=...
METACULUS_API_TOKEN=...
ALPHA_VANTAGE_API_KEY=...
ALERT_EMAIL_TO=...
```

### Install

```bash
git clone https://github.com/Hail15/kairosiq
cd kairosiq
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Database Setup

```bash
psql $DATABASE_URL < schema.sql
python seed_assets.py
```

### Run Locally

```bash
# Scheduler (backend)
python scheduler.py

# Dashboard
streamlit run streamlit_app.py

# API
uvicorn api_main:app --reload
```

### Deploy

```bash
# Push to GitHub — Railway and Streamlit Cloud auto-deploy
git add .
git commit -m "your message"
git push
```

---

## Dashboard Pages

| Page | Contents |
|------|----------|
| **Overview** | GPI index, live signal count, market pulse |
| **Signals** | Live signals, signal detail + AI brief, probability charts |
| **Portfolio** | Open positions, trade log, P&L tracking |
| **Scenarios** | Hypothetical event builder — project asset impacts |
| **Playbooks** | Intelligence interrogator, probability chart archive |
| **Research** | Signal accuracy leaderboard, correlation monitor, congressional trades |

---

## Track Record

KairosIQ maintains a documented, verifiable accuracy track record. Documented pre-event calls:

**BNO — April 10-13, 2026**
Black Swan signal fired April 10. Entry $47.70, exit $50.82. +6.54% in 3 days.

**FXI — April 9, 2026**
Institutional options convergence detected on China-linked assets. Signal fired 48 hours ahead of US-Iran peace talks convening in Islamabad.

Signal outcomes are validated automatically by `signal_validator.py` — comparing predicted direction vs actual asset movement at 24h, 72h, and 168h windows.

---

## B2B API

KairosIQ exposes a REST API for institutional clients via FastAPI.

```bash
GET /signals          # Active signals with asset mappings
GET /signals/{id}     # Signal detail + AI brief
GET /assets           # Asset correlation data
GET /gpi              # Current geopolitical pressure index
```

Authentication via API key. Contact for access.

---

## Legal

All data sources are publicly available. Congressional trade data is sourced from public STOCK Act disclosures via House Stock Watcher and Senate Stock Watcher APIs.

KairosIQ is not a registered broker-dealer or investment advisor. All signal outputs are framed as historical pattern analysis only and do not constitute investment advice.

---

## Team

**Ian Ostrowski** — Co-Founder  
**Kyle Worsley** — Co-Founder

---

*KairosIQ — Know before the market does.*
