# alpaca_trader.py
# Alpaca brokerage integration for KairosIQ
# Runs paper trades on every signal, real $1 trades on Tier 3 (highest confidence) signals only

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings

# ── Alpaca Config ────────────────────────────────────────────────────────────

ALPACA_PAPER_KEY    = settings.ALPACA_PAPER_KEY
ALPACA_PAPER_SECRET = settings.ALPACA_PAPER_SECRET
ALPACA_LIVE_KEY     = settings.ALPACA_LIVE_KEY
ALPACA_LIVE_SECRET  = settings.ALPACA_LIVE_SECRET

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
LIVE_BASE_URL  = "https://api.alpaca.markets/v2"

# Only Tier 3 (FULL CONVERGENCE) signals with strength >= 80 trigger real trades
LIVE_TRADE_MIN_TIER     = 3
LIVE_TRADE_MIN_STRENGTH = 80
LIVE_TRADE_AMOUNT_USD   = 1.00   # $1 notional per live trade
PAPER_TRADE_AMOUNT_USD  = 100.00 # $100 notional per paper trade

# Assets Alpaca can actually trade (stocks/ETFs only — no forex, futures)
# Maps our asset tickers to Alpaca-tradeable equivalents
TICKER_MAP = {
    # Oil & Energy
    "USO":  "USO",   # US Oil Fund ETF
    "XLE":  "XLE",   # Energy Select Sector ETF
    "XOM":  "XOM",   # ExxonMobil
    "CVX":  "CVX",   # Chevron
    # Gold & Safe Havens
    "GLD":  "GLD",   # SPDR Gold ETF
    "IAU":  "IAU",   # iShares Gold ETF
    "SLV":  "SLV",   # Silver ETF
    # Defense
    "LMT":  "LMT",   # Lockheed Martin
    "RTX":  "RTX",   # Raytheon
    "NOC":  "NOC",   # Northrop Grumman
    "BA":   "BA",    # Boeing
    "ITA":  "ITA",   # iShares Defense ETF
    # Volatility & Broad Market
    "SPY":  "SPY",   # S&P 500 ETF
    "QQQ":  "QQQ",   # Nasdaq ETF
    "VIXY": "VIXY",  # VIX Short-Term Futures ETF
    # Emerging Markets
    "EEM":  "EEM",   # iShares Emerging Markets ETF
    "EWZ":  "EWZ",   # Brazil ETF
    "EWT":  "EWT",   # Taiwan ETF
    # Shipping
    "ZIM":  "ZIM",   # ZIM Integrated Shipping
    "PANL": "PANL",  # Pangaea Logistics
}

# Tickers we cannot trade on Alpaca (forex, futures, crypto not in map)
UNTRADEABLE = {"XAUUSD", "XAGUSD", "CL=F", "BZ=F", "DXY", "USDTRY",
               "USDRUB", "USDKRW", "VIX", "BTC", "ETH"}


def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Alpaca API Helpers ────────────────────────────────────────────────────────

def _headers(live=False):
    key    = ALPACA_LIVE_KEY    if live else ALPACA_PAPER_KEY
    secret = ALPACA_LIVE_SECRET if live else ALPACA_PAPER_SECRET
    return {
        "APCA-API-KEY-ID":     key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type":        "application/json"
    }

def _base(live=False):
    return LIVE_BASE_URL if live else PAPER_BASE_URL


def get_account(live=False):
    """Return Alpaca account info."""
    r = requests.get(f"{_base(live)}/account", headers=_headers(live), timeout=10)
    if r.status_code == 200:
        return r.json()
    print(f"❌ Alpaca account fetch failed ({r.status_code}): {r.text}")
    return None


def get_current_price(ticker):
    """Get latest trade price for a ticker via Alpaca market data."""
    url = f"https://data.alpaca.markets/v2/stocks/{ticker}/trades/latest"
    # Use paper keys for market data (same data feed)
    headers = _headers(live=False)
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 200:
        data = r.json()
        return data.get("trade", {}).get("p")  # price
    return None


def place_order(ticker, side, notional_usd, live=False):
    """
    Place a fractional notional order on Alpaca.
    side: 'buy' or 'sell'
    notional_usd: dollar amount (e.g. 1.00 or 100.00)
    """
    alpaca_ticker = TICKER_MAP.get(ticker)
    if not alpaca_ticker:
        print(f"⚠️  {ticker} not in TICKER_MAP — skipping Alpaca order")
        return None

    payload = {
        "symbol":        alpaca_ticker,
        "notional":      str(round(notional_usd, 2)),
        "side":          side,
        "type":          "market",
        "time_in_force": "day"
    }

    mode = "LIVE" if live else "PAPER"
    print(f"📤 Alpaca {mode} order: {side.upper()} ${notional_usd} of {alpaca_ticker}")

    r = requests.post(
        f"{_base(live)}/orders",
        headers=_headers(live),
        json=payload,
        timeout=10
    )

    if r.status_code in (200, 201):
        order = r.json()
        print(f"✅ Order placed: {order.get('id')} — status: {order.get('status')}")
        return order
    else:
        print(f"❌ Alpaca order failed ({r.status_code}): {r.text}")
        return None


def close_position(ticker, live=False):
    """Close any open position for a ticker."""
    alpaca_ticker = TICKER_MAP.get(ticker, ticker)
    mode = "LIVE" if live else "PAPER"
    print(f"📤 Alpaca {mode} close position: {alpaca_ticker}")
    r = requests.delete(
        f"{_base(live)}/positions/{alpaca_ticker}",
        headers=_headers(live),
        timeout=10
    )
    if r.status_code in (200, 201):
        print(f"✅ Position closed: {alpaca_ticker}")
        return r.json()
    elif r.status_code == 404:
        print(f"ℹ️  No open position for {alpaca_ticker}")
        return None
    else:
        print(f"❌ Close position failed ({r.status_code}): {r.text}")
        return None


# ── Trade Logging ─────────────────────────────────────────────────────────────

def log_trade(signal_id, ticker, side, notional_usd, order_id,
              order_status, is_live, entry_price=None, notes=""):
    """Log a trade to the alpaca_trades table."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO alpaca_trades
                (signal_id, ticker, side, notional_usd, order_id,
                 order_status, is_live, entry_price, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (order_id) DO NOTHING;
        """, (str(signal_id), ticker, side, notional_usd, order_id,
              order_status, is_live, entry_price, notes))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Trade logged: {side.upper()} {ticker} (signal {signal_id})")
    except Exception as e:
        print(f"❌ Trade log error: {e}")


def update_trade_exit(order_id, exit_price, pnl_usd, exit_reason="signal_decay"):
    """Record exit price and P&L when a position is closed."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE alpaca_trades
            SET exit_price  = %s,
                pnl_usd     = %s,
                exit_reason = %s,
                closed_at   = NOW()
            WHERE order_id = %s;
        """, (exit_price, pnl_usd, exit_reason, order_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Trade exit update error: {e}")


def get_open_trades():
    """Return all trades that haven't been closed yet."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, signal_id, ticker, side, notional_usd,
                   order_id, is_live, entry_price, created_at
            FROM alpaca_trades
            WHERE closed_at IS NULL
            ORDER BY created_at DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ get_open_trades error: {e}")
        return []


def already_traded_signal(signal_id):
    """Check if we already placed any trade for this signal."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT 1 FROM alpaca_trades WHERE signal_id = %s LIMIT 1;",
            (str(signal_id),)
        )
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        print(f"❌ already_traded_signal error: {e}")
        return False


# ── Core Trading Logic ────────────────────────────────────────────────────────

def execute_signal_trade(signal):
    """
    Main entry point. Called for each new signal.
    signal dict must have:
        id, signal_strength, convergence_tier, best_performer (asset dict),
        event_description
    Always places a paper trade.
    Places a real $1 live trade ONLY if Tier 3 + strength >= 80.
    """
    signal_id        = signal.get("id")
    strength         = signal.get("signal_strength", 0)
    tier             = signal.get("convergence_tier", 1)
    best             = signal.get("best_performer")

    if not best:
        print(f"⚠️  Signal {signal_id}: no best_performer asset — skipping trade")
        return

    ticker    = best.get("ticker", "")
    direction = best.get("direction", "").lower()  # 'up' or 'down'
    name      = best.get("name", ticker)

    if ticker in UNTRADEABLE or ticker not in TICKER_MAP:
        print(f"⚠️  {ticker} ({name}) not tradeable on Alpaca — skipping")
        return

    if already_traded_signal(signal_id):
        print(f"ℹ️  Signal {signal_id} already has trades — skipping")
        return

    side = "buy" if direction == "up" else "sell"

    # ── Paper trade (always) ──────────────────────────────────────────────
    paper_order = place_order(ticker, side, PAPER_TRADE_AMOUNT_USD, live=False)
    if paper_order:
        entry_price = get_current_price(ticker)
        log_trade(
            signal_id   = signal_id,
            ticker      = ticker,
            side        = side,
            notional_usd= PAPER_TRADE_AMOUNT_USD,
            order_id    = paper_order.get("id", ""),
            order_status= paper_order.get("status", ""),
            is_live     = False,
            entry_price = entry_price,
            notes       = f"Signal strength {strength}/100 | Tier {tier} | {name}"
        )

    # ── Live $1 trade (Tier 3 + strength >= 80 only) ──────────────────────
    qualify_for_live = (tier >= LIVE_TRADE_MIN_TIER and
                        strength >= LIVE_TRADE_MIN_STRENGTH and
                        ALPACA_LIVE_KEY)

    if qualify_for_live:
        print(f"🔴 LIVE TRADE TRIGGERED — Tier {tier}, strength {strength}")
        live_order = place_order(ticker, side, LIVE_TRADE_AMOUNT_USD, live=True)
        if live_order:
            entry_price = get_current_price(ticker)
            log_trade(
                signal_id   = signal_id,
                ticker      = ticker,
                side        = side,
                notional_usd= LIVE_TRADE_AMOUNT_USD,
                order_id    = live_order.get("id", ""),
                order_status= live_order.get("status", ""),
                is_live     = True,
                entry_price = entry_price,
                notes       = f"LIVE $1 | Strength {strength}/100 | Tier {tier} | {name}"
            )
    else:
        if not ALPACA_LIVE_KEY:
            print(f"ℹ️  No live key configured — paper only")
        else:
            print(f"ℹ️  Signal {signal_id}: Tier {tier} / strength {strength} "
                  f"— paper only (need Tier {LIVE_TRADE_MIN_TIER}+ and "
                  f"strength {LIVE_TRADE_MIN_STRENGTH}+ for live)")


def run_exit_check():
    """
    Called every cycle. Checks open trades against their signals.
    Closes position if the signal has expired or a counter-signal fired.
    """
    open_trades = get_open_trades()
    if not open_trades:
        return

    print(f"\n🔍 Checking {len(open_trades)} open Alpaca positions...")

    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, status FROM signals
            WHERE status IN ('expired', 'invalidated');
        """)
        dead_signals = {str(row[0]): row[1] for row in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Exit check DB error: {e}")
        return

    for trade in open_trades:
        (trade_id, signal_id, ticker, side, notional_usd,
         order_id, is_live, entry_price, created_at) = trade

        if str(signal_id) in dead_signals:
            reason = dead_signals[str(signal_id)]
            print(f"🚪 Closing {ticker} — signal {signal_id} is {reason}")

            closed = close_position(ticker, live=is_live)
            if closed:
                exit_price = get_current_price(ticker)
                if exit_price and entry_price:
                    multiplier = 1 if side == "buy" else -1
                    pnl = round(
                        multiplier * (exit_price - float(entry_price)) /
                        float(entry_price) * float(notional_usd), 4
                    )
                else:
                    pnl = None

                update_trade_exit(order_id, exit_price, pnl, exit_reason=reason)


def get_trade_summary():
    """Return P&L summary for dashboard display."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*)                                        AS total_trades,
                COUNT(*) FILTER (WHERE is_live = false)        AS paper_trades,
                COUNT(*) FILTER (WHERE is_live = true)         AS live_trades,
                COUNT(*) FILTER (WHERE pnl_usd > 0)            AS winners,
                COUNT(*) FILTER (WHERE pnl_usd < 0)            AS losers,
                ROUND(AVG(pnl_usd)::numeric, 4)                AS avg_pnl,
                ROUND(SUM(pnl_usd)::numeric, 4)                AS total_pnl,
                COUNT(*) FILTER (WHERE closed_at IS NULL)      AS open_positions
            FROM alpaca_trades;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {}

        total, paper, live, winners, losers, avg_pnl, total_pnl, open_pos = row
        win_rate = round(winners / total * 100, 1) if total else 0

        return {
            "total_trades":    total,
            "paper_trades":    paper,
            "live_trades":     live,
            "winners":         winners,
            "losers":          losers,
            "win_rate_pct":    win_rate,
            "avg_pnl_usd":     float(avg_pnl or 0),
            "total_pnl_usd":   float(total_pnl or 0),
            "open_positions":  open_pos
        }
    except Exception as e:
        print(f"❌ get_trade_summary error: {e}")
        return {}


if __name__ == "__main__":
    print("🦙 Alpaca Trader — Connection Test")
    acct = get_account(live=False)
    if acct:
        print(f"✅ Paper account connected")
        print(f"   Buying power: ${float(acct.get('buying_power', 0)):,.2f}")
        print(f"   Portfolio value: ${float(acct.get('portfolio_value', 0)):,.2f}")
    else:
        print("❌ Could not connect to Alpaca paper account")
        print("   Check ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET env vars")