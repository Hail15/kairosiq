# ingestion/kalshi.py
import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import base64
import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.backends import default_backend

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ============================================================
# ALL RELEVANT EVENT TICKERS — comprehensive geopolitical,
# economic, political, financial, tech coverage
# Every event that could affect financial markets
# ============================================================
GEOPOLITICAL_EVENT_TICKERS = [

    # ── IRAN / MIDDLE EAST CONFLICT ──────────────────────────
    "KXIRANWAR-26",                 # US-Iran war in 2026
    "KXIRANSTRIKE-26",              # US/Israel strike on Iran
    "KXIRANNUKE-26",                # Iran nuclear weapon test
    "KXIRANREGIME-26",              # Iranian regime change
    "KXHORMUZ-26",                  # Strait of Hormuz closure
    "KXISRAELIRAN-26",              # Israel-Iran direct conflict
    "KXIRANDEMOCRACY-27MAR01",      # Will Iran become a democracy
    "KXIRANIMPORTS-27FEB01",        # US imports from Iran
    "KXNEXTISRAELPM-45JAN01",       # Next PM of Israel
    "KXABRAHAMSY-29",               # Israel-Syria normalization
    "KXABRAHAMSA-29",               # Israel-Saudi normalization
    "KXABRAHAMQ-29",                # Israel-Qatar normalization

    # ── OIL / ENERGY ─────────────────────────────────────────
    "KXOILPRICE-100-26",            # Oil hits $100 in 2026
    "KXOILPRICE-120-26",            # Oil hits $120 in 2026
    "KXOILPRICE-80-26",             # Oil stays above $80 in 2026
    "KXBRENT-26",                   # Brent crude price range
    "KXOPECCUT-26",                 # OPEC production cut 2026
    "KXOPECMEET-26",                # OPEC emergency meeting
    "KXGASOLINE-26",                # US gas prices surge
    "KXNATURALGAS-26",              # Natural gas price spike

    # ── GEOPOLITICAL / CONFLICT ──────────────────────────────
    "KXXISUCCESSOR-45JAN01",        # Xi Jinping successor
    "KXG7LEADEROUT-45JAN01",        # G7 leader leaves next
    "KXTAIWANLVL4",                 # US Level 4 travel advisory Taiwan
    "KXAFRICALEADEROUT-35",         # African leaders leaving office
    "KXZELENSKYPUTIN-29",           # Zelenskyy and Putin speak
    "KXPUTINDJTLOCATION-29",        # Where Trump and Putin meet
    "KXPUTINZELENSKYYLOCATION-28",  # Where Putin and Zelenskyy meet
    "KXRECOGROC-29",                # Will Trump recognize Taiwan
    "KXUSAKIM-29",                  # Kim Jong-Un visits US
    "KXLAIOUT-LCHI",                # Lai Ching-te out as Taiwan President
    "KXRECOGSOMALI-29",             # Trump recognizes Somaliland
    "KXBOUGAINVILLEIND",            # Papua New Guinea Bougainville independence
    "KXQUEBEC-29",                  # Quebec referendum

    # ── US POLITICS & POLICY ────────────────────────────────
    "KXBALANCE-29",                # Trump balance budget
    "KXGDPSHAREMANU-29",           # Trump bring back manufacturing
    "KXGOVTCUTS-28",               # Government spending cuts
    "KXDEBTGROWTH-28DEC31",        # US national debt peak
    "KXEOTRUMPTERM-29JAN20",       # Trump executive orders
    "KXECCOMPACT-30",              # Electoral compact
    "KXTRUMPRESIGN",               # Trump resign
    "KXTRUMPREMOVE",               # Trump impeached and removed
    "KXIMPEACH-29",                # Trump impeached
    "KXAMEND22-29",                # Trump 3rd term allowed
    "KXAMEND25-29",                # 25th Amendment used
    "KXTRUMPRUN",                  # Trump run for third term
    "KXINSURRECTION-29",           # Trump invoke Insurrection Act
    "KXHABEAS-29",                 # Trump suspend habeas corpus
    "KXMARTIAL-29JAN20",           # Trump impose martial law
    "KXCAPCONTROL-29",             # Trump impose capital controls
    "KXINDJUDICIARY-29",           # Independence of judiciary weakened
    "KXSTATE51-29",                # 51st state added
    "KXSTATE-29",                  # Trump add 51st state
    "KXGREELAND-29",               # Trump buy Greenland
    "KXGREENTERRITORY-29",         # US take control of Greenland
    "KXCANTERRITORY-29",           # US take control of Canada
    "KXCANAL-29",                  # Trump take back Panama Canal
    "KXUSAEXPANDTERRITORY",        # US acquire new territory
    "KXWITHDRAW-29",               # What US will withdraw from
    "KXDOED-29",                   # Trump abolish Dept of Education
    "KXFEDEND-29",                 # Trump end Federal Reserve
    "KXACAREPEAL-29",              # Obamacare repealed
    "KXTERMLIMITS-29",             # Trump impose term limits
    "KXTAFTHARTLEY-29",            # Trump invoke Taft-Hartley
    "KXAGENCYELIM-29",             # Which agencies Trump eliminates
    "KXH1B-29",                    # Trump expand H1-B
    "KXFREEIVF-29",                # Trump make IVF free
    "KXVETOOVERRIDE-29JAN20",      # Congress override Trump veto
    "KXSCOTUSRESIGN-29",           # Supreme Court justices resign
    "KXSCOTUSCHANGE-29",           # Supreme Court size changed
    "KXSCOURT-29",                 # Next Supreme Court justice
    "KXSCOTUSPOWER-29",            # Supreme Court composition
    "KXOBERGEFELL-29",             # Supreme Court overturn gay marriage
    "KXDEMOCRACYUS-28",            # US democracy under Trump
    "KXNEXTSPEAKER-31",            # Next Speaker of the House
    "KXNEXTAG-29",                 # Trump next Attorney General
    "KXNEXTDEF-29",                # Trump next Secretary of Defense
    "KXNEXTSTATE-29",              # Trump next Secretary of State
    "KXCABOUT-26APR",              # Who leaves Trump Cabinet next
    "KXTRUMPBULLCASECOMBO-27DEC",  # Trump dream year 2026
    "KXTRUMPBEARCASECOMBO-27DEC",  # Trump bad year 2026
    "KXIRSCOLLECT-26",             # IRS tax collection
    "KXTARIFFREVENUE-26DEC31",     # US tariff revenue 2026
    "KXTRADEDEFICIT-27FEB28",      # US trade deficit 2026
    "KXNFPROD-27MAR04",            # US nonfarm productivity
    "POWER-28",                    # 2028 Presidency House Senate
    "KXGDPUSMAX-28",               # Trump economic boom
    "KXINEQUALITY-28",             # Trump reduce inequality

    # ── FEDERAL RESERVE & MONETARY POLICY ───────────────────
    "KXFEDCHAIRCONFIRM",           # Who confirmed as Fed chair
    "KXFEDDECISION-27APR",         # Fed decision Apr 2027
    "KXFEDDECISION-27JUN",         # Fed decision Jun 2027
    "KXFEDDECISION-27JUL",         # Fed decision Jul 2027
    "KXFEDDECISION-27SEP",         # Fed decision Sep 2027
    "KXFEDDECISION-27OCT",         # Fed decision Oct 2027
    "KXFEDDECISION-27DEC",         # Fed decision Dec 2027
    "KXFEDDECISION-28JAN",         # Fed decision Jan 2028
    "KXFED-27APR",                 # Fed funds rate Apr 2027
    "KXU3MAX-30",                  # Unemployment before 2030
    "KXPPIVSCPI-27FEB01",          # PPI vs CPI 2026

    # ── 2028 ELECTIONS ───────────────────────────────────────
    "KXPRESPERSON-28",             # 2028 Presidential winner
    "KXPRESPARTY-2028",            # 2028 Presidential party
    "KXPRESNOMR-28",               # 2028 Republican nominee
    "KXPRESNOMD-28",               # 2028 Democratic nominee
    "KXVPRESNOMR-28",              # 2028 Republican VP nominee
    "KXVPRESNOMD-28",              # 2028 Democratic VP nominee
    "KXPRESELECTIONOCCUR-28",      # Will 2028 election occur
    "KXTRUMPPRES-28",              # Trump family 2028 nominee
    "KXSANDERSPRES-28",            # Bernie Sanders 2028

    # ── GLOBAL ELECTIONS ─────────────────────────────────────
    "KXNEXTUKPM-30",               # Next UK Prime Minister
    "KXUKPARTY-29",                # UK general election party
    "KXFRENCHPRES-27",             # 2027 French presidential election
    "KXTURKEYPRES-28",             # Next Turkish presidential election
    "KXPARLITURKEY-28",            # Next Turkish general election
    "KXPRESTAIWAN-28",             # Next Taiwanese presidential election
    "KXFULLTERMSKPRES-29",         # South Korean President full term
    "KXARGENTINAPRES-27",          # Next Argentine presidential election
    "KXMOLDOVAPRES-28",            # Next Moldovan presidential election
    "KXGEORGIAPARLI-28",           # Next Georgian parliamentary election
    "KXAUSTRALIAHOUSE-28",         # Next Australian House election
    "KXAUSTRALIASENATE-28",        # Next Australian Senate election
    "KXPHILIPPINESPRES-28",        # Next Philippine presidential election
    "KXPHILIPPINESSENATE-28",      # Next Philippine Senate election
    "KXPHILIPPINESHOUSE-28",       # Next Philippine House election
    "KXGHANAPRES-28",              # Next Ghanaian presidential election
    "KXGHANAPARLI-28",             # Next Ghanaian parliamentary election
    "KXKENYASENATE-27",            # Next Kenyan Senate election
    "KXKENYAASSEMBLY-27",          # Next Kenyan National Assembly
    "KXSPAINPARLI-27",             # Next Spanish general election
    "KXGREECEPARLI-27",            # Next Greek general election
    "KXPOLANDSEJM-27",             # Next Polish general election
    "KXSLOVAKIAPARLI-27",          # Next Slovak parliamentary election
    "KXITALYSENATE-27",            # Next Italian Senate election
    "KXITALYDEPUTIES-27",          # Next Italian Chamber of Deputies
    "KXFINLANDPARLI-27",           # Next Finnish general election
    "KXMALAYSIAPARLI-2-27",        # Next Malaysian general election
    "KXMEXICODEPUTIES-27",         # Next Mexican Chamber election
    "KXMONGOLIAPRES-27",           # Next Mongolian presidential election
    "KXGUATEMALACONGRESS-27",      # Next Guatemalan Congressional election
    "KXCOLOM BIAPRES1R-26MAY31",   # Colombian presidential election
    "KXBRAZILPRES1R-26OCT04",      # Brazil Presidential election
    "KXALBERTAREFYES-29",          # Alberta secession
    "KXBRUVSEAT-35",               # UK far right party seat

    # ── EU / EUROPE ──────────────────────────────────────────
    "KXEUREF-30",                  # EU referendum
    "KXEUEXITCOUNTRY-30",          # Countries leaving EU
    "EUEXPANSION",                 # EU gains member
    "EUEXIT",                      # EU loses member
    "CHINAUSGDP",                  # China overtakes US GDP

    # ── TECH / IPO / FINANCIAL ───────────────────────────────
    "KXOAIANTH-40",                # OpenAI or Anthropic IPO first
    "KXUSTAKEOVER-30",             # US government AI takeover
    "KXJPMCEONEW",                 # JPMorgan CEO succession
    "AMAZONFTC-29DEC31",           # Amazon monopoly
    "APPLEUS",                     # Apple monopoly
    "KXAGICO-COMP",                # When company achieves AGI
    "KXSTRIPEIPO",                 # Stripe IPO
    "KXIPOSPACEX",                 # SpaceX IPO
    "KXIPOSTARLINK",               # Starlink IPO
    "KXIPOOPENAI",                 # OpenAI IPO
    "KXIPORIPPLING",               # Rippling IPO
    "KXIPORAMP",                   # Ramp IPO
    "KXIPOBREX",                   # Brex IPO
    "KXIPODISCORD",                # Discord IPO
    "KXIPOGLEAN",                  # Glean IPO
    "KXIPOANDURIL",                # Anduril IPO (defense tech)
    "KXIPOFANNIE",                 # Fannie Mae IPO
    "KXFREDDIE",                   # Freddie Mac IPO
    "KXIPOAIRTABLE",               # Airtable IPO
    "KXRIPPLINGDEEL-28",           # Rippling vs Deel lawsuit
    "KXOAIDAMAGE-28",              # OpenAI tort claim
    "KXANTHROPICDOD-28",           # Anthropic vs Pentagon
    "NYTOAI-27DEC31",              # NYT wins OpenAI lawsuit
    "KXTRUMPVSLAUGHTER",           # Trump fire FTC commissioners
    "KXCOMPANYACTIONMERGER-27",    # Tesla SpaceX merger
    "EVSHARE-30JAN",               # EV market share 2030

    # ── CLIMATE / ENERGY ─────────────────────────────────────
    "KXWARMING-50",                # Global warming 2 degrees
    "KXDATACENTER-30",             # Nuclear data center military base
    "KXCO2LEVEL-30",               # CO2 levels
    "EUCLIMATE",                   # EU climate goals
    "INDIACLIMATE-30",             # India climate goals
    "USCLIMATE",                   # US climate goals
    "KXPRIMEENGCONSUMPTION-30",    # Primary energy source 2030
    "KXSUPERSONIC-28",             # Supersonic flight ban lifted

    # ── MACRO ECONOMIC INDICATORS ────────────────────────────
    "KXGDPUSMAX-28",               # US GDP under Trump
    "KXNFPROD-27MAR04",            # US nonfarm productivity
    "KXPPIVSCPI-27FEB01",          # PPI vs CPI
    "KXTARIFFREVENUE-26DEC31",     # Tariff revenue
    "KXTRADEDEFICIT-27FEB28",      # Trade deficit
    "KXIRSCOLLECT-26",             # IRS tax collection
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_auth_headers(method, path):
    timestamp_ms = int(datetime.datetime.now().timestamp() * 1000)
    timestamp_str = str(timestamp_ms)
    message = f"{timestamp_str}{method}{path}"
    try:
        key_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "kalshi_private_key.pem"
        )
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )
        signature = private_key.sign(
            message.encode("utf-8"),
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode("utf-8")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "KairosIQ/1.0",
            "KALSHI-ACCESS-KEY": settings.KALSHI_API_KEY,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
            "KALSHI-ACCESS-SIGNATURE": signature_b64
        }
    except Exception as e:
        print(f"❌ Error generating auth headers: {e}")
        return None

def fetch_markets_for_event(event_ticker, headers):
    path = "/trade-api/v2/markets"
    url = f"https://api.elections.kalshi.com{path}"
    try:
        response = requests.get(
            url,
            headers=headers,
            params={
                "status": "open",
                "event_ticker": event_ticker,
                "limit": 50
            },
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get("markets", [])
        return []
    except Exception:
        return []

def fetch_kalshi_markets():
    print("📡 Fetching Kalshi markets across all categories...")
    path = "/trade-api/v2/markets"
    headers = get_auth_headers("GET", path)
    if not headers:
        print("❌ Could not generate auth headers.")
        return []

    all_markets = []
    found_events = 0

    for event_ticker in GEOPOLITICAL_EVENT_TICKERS:
        markets = fetch_markets_for_event(event_ticker, headers)
        if markets:
            found_events += 1
            all_markets.extend(markets)

    # Deduplicate by ticker
    seen = set()
    unique = []
    for m in all_markets:
        mid = m.get("ticker", "")
        if mid not in seen:
            seen.add(mid)
            unique.append(m)

    print(f"   Found {len(unique)} markets across {found_events} events")
    return unique

def is_clean(question_text):
    """Final safety — block any sports that slipped through."""
    text = question_text.lower().strip()
    if text.startswith("yes "):
        return False
    if text.startswith("no "):
        return False
    if ",yes " in text:
        return False
    if "wins by over" in text:
        return False
    if "points scored" in text:
        return False
    if "runs scored" in text:
        return False
    if "goals scored" in text:
        return False
    return True

def extract_probability(market):
    try:
        last_price = market.get("last_price")
        if last_price is not None and last_price > 0:
            return round(float(last_price), 2)
        yes_bid = market.get("yes_bid", 0) or 0
        yes_ask = market.get("yes_ask", 0) or 0
        if yes_bid > 0 and yes_ask > 0:
            return round((yes_bid + yes_ask) / 2, 2)
        if yes_ask > 0:
            return round(float(yes_ask), 2)
        if yes_bid > 0:
            return round(float(yes_bid), 2)
        no_bid = market.get("no_bid", 0) or 0
        no_ask = market.get("no_ask", 0) or 0
        if no_bid > 0 and no_ask > 0:
            return round(100 - ((no_bid + no_ask) / 2), 2)
        return None
    except (ValueError, TypeError):
        return None

def save_question(cur, market):
    platform_id = market.get("ticker", "")
    question_text = market.get("title", "")
    probability = extract_probability(market)
    resolution_date = market.get("close_time", None)

    if not platform_id or not question_text:
        return None

    if not is_clean(question_text):
        return None

    cur.execute("""
        INSERT INTO prediction_questions
            (platform, platform_id, question_text, category, region,
             current_probability, is_active, resolution_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (platform, platform_id)
        DO UPDATE SET
            current_probability = EXCLUDED.current_probability,
            updated_at = NOW()
        RETURNING id;
    """, (
        "kalshi", platform_id, question_text,
        "geopolitical", "global", probability, True, resolution_date
    ))

    row = cur.fetchone()
    return row[0] if row else None

def save_snapshot(cur, question_id, probability):
    if probability is None:
        return
    cur.execute("""
        INSERT INTO probability_snapshots
            (question_id, probability, snapshot_time)
        VALUES (%s, %s, NOW());
    """, (question_id, probability))

def run_kalshi_ingestion():
    print("\n🔄 Starting Kalshi ingestion...")
    markets = fetch_kalshi_markets()
    if not markets:
        print("   No markets returned. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for market in markets:
        question_id = save_question(cur, market)
        if question_id:
            probability = extract_probability(market)
            save_snapshot(cur, question_id, probability)
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Kalshi ingestion complete. {saved} questions saved/updated.")

if __name__ == "__main__":
    run_kalshi_ingestion()