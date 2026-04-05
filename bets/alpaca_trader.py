# bets/alpaca_trader.py
# KairosIQ — Alpaca Trade Recommendation + Manual Trade Logger
# NO automatic trading. System surfaces recommendations, human pulls the trigger.

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings

# ── Alpaca Config (read-only market data + account info) ─────────────────────
ALPACA_PAPER_KEY    = settings.ALPACA_PAPER_KEY
ALPACA_PAPER_SECRET = settings.ALPACA_PAPER_SECRET
ALPACA_LIVE_KEY     = settings.ALPACA_LIVE_KEY
ALPACA_LIVE_SECRET  = settings.ALPACA_LIVE_SECRET

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
LIVE_BASE_URL  = "https://api.alpaca.markets/v2"

TICKER_MAP = {
    "USO":  "USO",   "XLE":  "XLE",   "XOM":  "XOM",   "CVX":  "CVX",
    "GLD":  "GLD",   "IAU":  "IAU",   "SLV":  "SLV",
    "LMT":  "LMT",   "RTX":  "RTX",   "NOC":  "NOC",
    "BA":   "BA",    "ITA":  "ITA",
    "SPY":  "SPY",   "QQQ":  "QQQ",   "VIXY": "VIXY",
    "EEM":  "EEM",   "EWZ":  "EWZ",   "EWT":  "EWT",
    "ZIM":  "ZIM",   "PANL": "PANL",
}

UNTRADEABLE = {"XAUUSD", "XAGUSD", "CL=F", "BZ=F", "DXY",
               "USDTRY", "USDRUB", "USDKRW", "VIX", "BTC", "ETH"}


def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Market Data ───────────────────────────────────────────────────────────────

def _data_headers():
    return {
        "APCA-API-KEY-ID":     ALPACA_PAPER_KEY,
        "APCA-API-SECRET-KEY": ALPACA_PAPER_SECRET,
    }

def get_current_price(ticker):
    alpaca_ticker = TICKER_MAP.get(ticker, ticker)
    url = f"https://data.alpaca.markets/v2/stocks/{alpaca_ticker}/trades/latest"
    try:
        r = requests.get(url, headers=_data_headers(), timeout=10)
        if r.status_code == 200:
            return r.json().get("trade", {}).get("p")
    except Exception as e:
        print(f"⚠️  Price fetch error for {ticker}: {e}")
    return None

def get_account_info(live=False):
    key    = ALPACA_LIVE_KEY    if live else ALPACA_PAPER_KEY
    secret = ALPACA_LIVE_SECRET if live else ALPACA_PAPER_SECRET
    base   = LIVE_BASE_URL      if live else PAPER_BASE_URL
    headers = {
        "APCA-API-KEY-ID":     key,
        "APCA-API-SECRET-KEY": secret,
    }
    try:
        r = requests.get(f"{base}/account", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️  Account info error: {e}")
    return None


# ── Trade Recommendations ─────────────────────────────────────────────────────

def build_trade_recommendation(signal_id, signal_strength, convergence_tier,
                                best_asset, event_description):
    if not best_asset:
        return None

    ticker    = best_asset.get("ticker", "")
    direction = best_asset.get("direction", "").lower()
    name      = best_asset.get("name", ticker)
    accuracy  = best_asset.get("accuracy", 0) or 0
    avg_72h   = best_asset.get("avg_move_72h", 0) or 0
    confidence= best_asset.get("confidence", "low")

    if ticker in UNTRADEABLE:
        tradeable = False
        note = "Not directly tradeable on Alpaca (futures/forex)"
    elif ticker in TICKER_MAP:
        tradeable = True
        note = f"Tradeable on Alpaca as {TICKER_MAP[ticker]}"
    else:
        tradeable = False
        note = "Check if available on your broker"

    current_price = get_current_price(ticker) if tradeable else None

    return {
        "signal_id":        signal_id,
        "ticker":           ticker,
        "alpaca_symbol":    TICKER_MAP.get(ticker, ticker),
        "name":             name,
        "direction":        direction,
        "side":             "BUY" if direction == "up" else "SELL SHORT",
        "signal_strength":  signal_strength,
        "convergence_tier": convergence_tier,
        "avg_move_72h":     round(abs(avg_72h), 2),
        "directional_acc":  round(accuracy * 100, 1),
        "asset_confidence": confidence,
        "tradeable":        tradeable,
        "current_price":    current_price,
        "note":             note,
        "event_description": event_description,
        "generated_at":     datetime.now().isoformat(),
    }


# ── Manual Trade Logging ──────────────────────────────────────────────────────

def log_manual_trade(signal_id, ticker, side, notional_usd,
                     entry_price, is_live=False, notes=""):
    try:
        import hashlib
        order_id = hashlib.sha256(
            f"{signal_id}-{ticker}-{side}-{entry_price}-{datetime.now().isoformat()}"
            .encode()
        ).hexdigest()[:32]

        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO alpaca_trades
                (signal_id, ticker, side, notional_usd, order_id,
                 order_status, is_live, entry_price, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, %s, NOW())
            ON CONFLICT (order_id) DO NOTHING
            RETURNING id;
        """, (str(signal_id), ticker, side.lower(), notional_usd,
              order_id, is_live, entry_price, notes))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Manual trade logged: {side} {ticker} @ ${entry_price}")
        return order_id if row else None
    except Exception as e:
        print(f"❌ log_manual_trade error: {e}")
        return None


def close_manual_trade(order_id, exit_price, exit_reason="manual_close"):
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT side, notional_usd, entry_price
            FROM alpaca_trades WHERE order_id = %s;
        """, (order_id,))
        row = cur.fetchone()

        pnl = None
        if row:
            side, notional, entry = row
            if entry and exit_price:
                multiplier = 1 if side == "buy" else -1
                pnl = round(
                    multiplier * (float(exit_price) - float(entry))
                    / float(entry) * float(notional), 4
                )

        cur.execute("""
            UPDATE alpaca_trades
            SET exit_price  = %s,
                pnl_usd     = %s,
                exit_reason = %s,
                closed_at   = NOW()
            WHERE order_id = %s;
        """, (exit_price, pnl, exit_reason, order_id))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Trade closed: P&L ${pnl:+.4f}" if pnl is not None else "✅ Trade closed")
        return pnl
    except Exception as e:
        print(f"❌ close_manual_trade error: {e}")
        return None


# ── Dashboard Data Fetchers ───────────────────────────────────────────────────

def get_open_trades():
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, signal_id, ticker, side, notional_usd,
                   order_id, is_live, entry_price, notes, created_at
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


def get_trade_summary():
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*)                                        AS total,
                COUNT(*) FILTER (WHERE is_live = false)        AS paper,
                COUNT(*) FILTER (WHERE is_live = true)         AS live,
                COUNT(*) FILTER (WHERE pnl_usd > 0)            AS winners,
                COUNT(*) FILTER (WHERE pnl_usd <= 0
                                 AND pnl_usd IS NOT NULL)      AS losers,
                ROUND(SUM(pnl_usd)::numeric, 4)                AS total_pnl,
                COUNT(*) FILTER (WHERE closed_at IS NULL)      AS open_pos
            FROM alpaca_trades;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        print(f"❌ get_trade_summary error: {e}")
        return None


if __name__ == "__main__":
    print("🦙 Alpaca — Account Info")
    acct = get_account_info(live=False)
    if acct:
        print(f"✅ Paper: ${float(acct.get('portfolio_value', 0)):,.2f}")
    acct_live = get_account_info(live=True)
    if acct_live:
        print(f"✅ Live:  ${float(acct_live.get('portfolio_value', 0)):,.2f}")