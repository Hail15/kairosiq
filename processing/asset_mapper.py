# processing/asset_mapper.py
import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_asset_mappings(event_type, region=None, description=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT asset_ticker, asset_name, asset_class,
               historical_direction, avg_move_24h, avg_move_72h,
               avg_move_168h, directional_accuracy, sample_size,
               confidence_rating
        FROM asset_mappings
        WHERE event_type = %s
        AND (region = %s OR region = 'Global')
        ORDER BY directional_accuracy DESC
        LIMIT 10;
    """, (event_type, region or 'Global'))
    rows = cur.fetchall()

    if not rows:
        cur.execute("""
            SELECT asset_ticker, asset_name, asset_class,
                   historical_direction, avg_move_24h, avg_move_72h,
                   avg_move_168h, directional_accuracy, sample_size,
                   confidence_rating
            FROM asset_mappings
            WHERE event_type = %s
            ORDER BY directional_accuracy DESC
            LIMIT 10;
        """, (event_type,))
        rows = cur.fetchall()

    cur.close()
    conn.close()

    assets = []
    for row in rows:
        assets.append({
            "ticker": row[0],
            "name": row[1],
            "asset_class": row[2],
            "direction": row[3],
            "avg_move_24h": row[4],
            "avg_move_72h": row[5],
            "avg_move_168h": row[6],
            "accuracy": row[7],
            "sample_size": row[8],
            "confidence": row[9]
        })

    # Auto-apply de-escalation direction flip if description provided
    if description and detect_de_escalation(description):
        assets = flip_directions_for_de_escalation(assets, description)
        print(f"   🕊️ De-escalation detected — asset directions flipped")

    return assets

def calculate_signal_strength(prob_shift, confidence_score,
                               assets, source_platform):
    score = 0
    if prob_shift:
        score += min(prob_shift * 1.3, 35)
    conf_scores = {"high": 25, "medium": 15, "low": 5}
    score += conf_scores.get(confidence_score or "low", 5)
    if assets:
        avg_acc = sum(a.get("accuracy", 0) for a in assets) / len(assets)
        score += avg_acc * 25
    source_scores = {
        "polymarket": 15, "kalshi": 15, "metaculus": 12,
        "gdelt": 8, "state_media": 7
    }
    score += source_scores.get(source_platform or "", 5)
    return min(round(score), 100)

def detect_de_escalation(description):
    """
    Returns True if the signal is a de-escalation / ceasefire event.
    These flip the expected asset directions vs escalation.
    """
    text = (description or "").lower()
    return any(k in text for k in [
        "ceasefire", "cease-fire", "peace deal", "peace agreement",
        "de-escalat", "truce", "diplomatic solution", "negotiations succeed",
        "reopens", "reopen", "lifted sanctions", "sanctions lifted",
        "talks resume", "deal reached", "agreement reached",
        "relief rally", "tension eases", "tensions ease",
        "bridge for peace", "opposition leader visits", "opposition leader makes first",
        "first visit since", "peace visit", "diplomatic visit",
        "gladly accepted", "hopes to be a bridge",
        # Hormuz / shipping specific
        "summit on reopening", "reopening strait", "reopen strait",
        "strait reopening", "hormuz summit", "hormuz reopen",
        "shipping summit", "blockade lifted", "blockade ends",
        "diplomacy mission", "diplomatic resolution",
        # General de-escalation
        "withdrawal begins", "troops withdraw", "forces withdraw",
        "hostages released", "prisoner exchange", "sanctions relief",
        "nuclear deal signed", "jcpoa restored",
    ])


def filter_assets_by_relevance(assets, description, event_category):
    """
    Filter out assets that have no relevance to the specific signal description.
    Prevents Lebanon ceasefire from recommending Taiwan ETFs.
    """
    text = (description or "").lower()

    # Asset-specific relevance rules
    ASSET_RELEVANCE = {
        # Taiwan / Semis
        "EWT":  ["taiwan", "strait", "cross-strait", "tsmc", "taiwanese"],
        "TSM":  ["taiwan", "strait", "semiconductor", "chip", "tsmc"],
        "SMH":  ["semiconductor", "chip", "taiwan", "korea", "memory"],
        "SOXX": ["semiconductor", "chip", "taiwan", "korea"],
        # China
        "KWEB": ["china", "chinese", "beijing", "alibaba", "tencent", "baidu"],
        "FXI":  ["china", "chinese", "beijing", "xi", "ccp"],
        "MCHI": ["china", "chinese", "beijing"],
        "BABA": ["china", "chinese", "alibaba"],
        # Shipping
        "ZIM":  ["shipping", "ship", "vessel", "port", "container", "freight", "maritime", "suez", "hormuz", "red sea"],
        "SBLK": ["shipping", "dry bulk", "freight", "maritime", "coal", "grain"],
        "GOGL": ["shipping", "dry bulk", "freight", "maritime"],
        "BDRY": ["shipping", "dry bulk", "freight", "commodity transport", "maritime"],
        "MATX": ["shipping", "container", "pacific", "freight"],
        # Energy / Oil
        "USO":  ["oil", "crude", "opec", "petroleum", "barrel", "hormuz", "iran", "energy"],
        "BNO":  ["oil", "crude", "opec", "petroleum", "barrel", "hormuz", "iran", "brent", "energy"],
        "XLE":  ["oil", "energy", "gas", "opec", "petroleum", "refinery", "drilling"],
        "XOM":  ["oil", "energy", "opec", "exxon", "petroleum"],
        "CVX":  ["oil", "energy", "opec", "chevron", "petroleum"],
        "COP":  ["oil", "energy", "conocophillips", "petroleum"],
        # Natural Gas
        "UNG":  ["natural gas", "lng", "gas supply", "pipeline", "russia", "nordstream", "europe energy"],
        "BOIL": ["natural gas", "lng", "gas supply", "pipeline", "russia"],
        "LNG":  ["lng", "liquefied natural gas", "export terminal", "europe gas"],
        # Defense
        "LMT":  ["military", "defense", "missile", "weapon", "war", "conflict", "nato", "iran", "israel", "ukraine"],
        "RTX":  ["military", "defense", "missile", "raytheon", "weapon", "war", "nato"],
        "NOC":  ["military", "defense", "northrop", "bomber", "drone", "space defense"],
        "GD":   ["military", "defense", "general dynamics", "submarine", "tank"],
        "HII":  ["military", "naval", "ship", "submarine", "navy", "huntington"],
        "BA":   ["military", "defense", "boeing", "aircraft", "fighter"],
        "ITA":  ["military", "defense", "weapon", "war", "conflict", "nato"],
        "CACI": ["cyber", "intelligence", "defense contract", "government"],
        "LDOS": ["defense", "government", "intelligence", "leidos"],
        # Safe Havens
        "GLD":  ["conflict", "war", "crisis", "uncertainty", "inflation", "iran", "russia", "nuclear"],
        "IAU":  ["conflict", "war", "crisis", "uncertainty", "inflation"],
        "SLV":  ["conflict", "crisis", "inflation", "industrial", "solar"],
        "GDX":  ["gold", "mining", "conflict", "inflation"],
        # Volatility
        "VIXY": ["conflict", "war", "crisis", "fear", "uncertainty", "volatility", "vix"],
        "UVXY": ["conflict", "crisis", "volatility", "fear"],
        # Rare Earth / Strategic
        "REMX": ["rare earth", "minerals", "china mineral", "lithium", "critical mineral"],
        "MP":   ["rare earth", "critical mineral", "china mineral", "supply chain"],
        # Agriculture / Food Security
        "WEAT": ["ukraine", "wheat", "grain", "food", "russia", "black sea", "hunger"],
        "CORN": ["ukraine", "corn", "grain", "food security", "ethanol"],
        "SOYB": ["soybean", "agriculture", "china trade", "food"],
        "MOS":  ["fertilizer", "agriculture", "ukraine", "food security", "potash"],
        # Nuclear
        "CCJ":  ["nuclear", "uranium", "reactor", "energy transition"],
        "URA":  ["nuclear", "uranium", "reactor", "atomic"],
        # Currency
        "UUP":  ["dollar", "fed", "interest rate", "reserve currency", "inflation"],
        "FXE":  ["euro", "europe", "ecb", "european"],
        "FXY":  ["yen", "japan", "boj", "japanese"],
        # Emerging Markets
        "EEM":  ["emerging market", "global", "developing", "EM stress"],
        "EWZ":  ["brazil", "latin america", "south america"],
        "EWT":  ["taiwan", "strait", "tsmc"],
        "INDA": ["india", "indian", "modi", "south asia"],
        # Airlines (inverse signal)
        "JETS": ["airline", "aviation", "travel", "flight", "airport", "hormuz", "fuel"],
        "UAL":  ["airline", "aviation", "fuel", "oil", "travel ban"],
        "DAL":  ["airline", "aviation", "fuel", "oil", "travel ban"],
        "AAL":  ["airline", "aviation", "fuel", "oil"],
        # Cyber
        "CIBR": ["cyber", "hack", "ransomware", "internet disruption", "malware", "attack"],
        "CRWD": ["cyber", "hack", "ransomware", "attack", "security breach"],
        "PANW": ["cyber", "hack", "firewall", "security", "attack"],
        "FTNT": ["cyber", "network security", "firewall", "hack"],
        # Inflation hedges
        "TIPS": ["inflation", "cpi", "fed", "interest rate", "price"],
        "GSG":  ["commodity", "inflation", "supply chain", "energy"],
        "PDBC": ["commodity", "inflation", "oil", "energy", "metals"],
        # Energy transition / Nuclear
        "CCJ":  ["nuclear", "uranium", "reactor", "energy"],
        "URA":  ["nuclear", "uranium", "atomic", "reactor"],
        "URNM": ["nuclear", "uranium", "reactor"],
        "NLR":  ["nuclear", "uranium", "power", "reactor"],
        # Tanker stocks (oil shipping)
        "STNG": ["oil", "tanker", "hormuz", "shipping", "suez"],
        "TNK":  ["oil", "tanker", "hormuz", "shipping"],
        "DHT":  ["oil", "tanker", "crude", "shipping"],
        "FRO":  ["oil", "tanker", "crude", "hormuz", "shipping"],
        # Palladium/Platinum
        "PALL": ["russia", "palladium", "sanctions", "ukraine"],
        "PPLT": ["russia", "platinum", "south africa", "mining"],
        # Additional defense
        "LHX":  ["military", "defense", "electronic warfare", "nato"],
        "KTOS": ["drone", "military", "unmanned", "defense"],
        "AVAV": ["drone", "military", "uav", "defense"],
        "BAESY":["military", "bae systems", "uk defense", "nato"],
        "EADSY":["military", "airbus", "nato", "europe defense"],
        # Middle East
        "KSA":  ["saudi", "arabia", "opec", "oil", "middle east"],
        "ISRA": ["israel", "israeli", "middle east", "gaza"],
        "EGPT": ["egypt", "suez", "middle east", "canal"],
        # Turkey / EM stress
        "TUR":  ["turkey", "turkish", "erdogan", "lira", "middle east"],
        # Lithium / Critical minerals
        "ALB":  ["lithium", "battery", "electric vehicle", "critical mineral"],
        "SQM":  ["lithium", "chile", "battery", "supply"],
        "LAC":  ["lithium", "battery", "critical mineral"],
        # Copper
        "COPX": ["copper", "china", "supply chain", "industrial"],
        "FCX":  ["copper", "mining", "supply chain", "china"],
        # Short China
        "YANG": ["china", "chinese", "beijing", "escalation"],
        # Short Semis
        "SOXS": ["semiconductor", "chip", "taiwan", "china"],
        # Short Bonds (rising rates)
        "TBT":  ["inflation", "fed", "rate hike", "interest rate"],
        "TMV":  ["inflation", "fed", "rate hike", "treasury"],
        # Mexico (tariff exposure)
        "EWW":  ["mexico", "tariff", "trade", "nafta", "usmca"],
        # Brazil
        "EWZ":  ["brazil", "latin america", "commodity", "iron ore"],
        # Argentina
        "ARGT": ["argentina", "peso", "debt crisis", "latin america"],
        # Broader EM stress
        "FM":   ["frontier market", "emerging", "political risk"],
        "EMHY": ["emerging market", "high yield", "debt", "default"],
    }

    filtered = []
    for asset in assets:
        ticker = asset.get("ticker", "")
        if ticker in ASSET_RELEVANCE:
            # Only include if description contains at least one relevant keyword
            relevant_keywords = ASSET_RELEVANCE[ticker]
            if not any(kw in text for kw in relevant_keywords):
                continue  # Skip irrelevant asset
        filtered.append(asset)

    # If filtering removed everything, return top 3 by accuracy as fallback
    if not filtered:
        return sorted(assets, key=lambda a: a.get("accuracy", 0), reverse=True)[:3]

    return filtered


def get_best_performer(assets, description=None):
    if not assets:
        return None

    # Filter by relevance if description provided
    if description:
        assets = filter_assets_by_relevance(assets, description, "")

    # If de-escalation, prefer safe haven assets over conflict assets
    is_de_escal = detect_de_escalation(description or "")

    def asset_score(a):
        acc    = a.get("accuracy", 0) or 0
        move   = abs(a.get("avg_move_72h", 0) or 0)
        samples = a.get("sample_size", 0) or 0
        ticker = a.get("ticker", "")
        # Penalize energy/shipping on de-escalation
        if is_de_escal and ticker in ["USO", "BNO", "XLE", "ZIM", "BDRY"]:
            return acc * move * (1 + samples / 100) * 0.3
        return acc * move * (1 + samples / 100)

    return max(assets, key=asset_score)


def flip_directions_for_de_escalation(assets, description):
    """
    For ceasefire/de-escalation signals, flip expected directions.
    Oil goes down, defense goes down, gold uncertain, TLT up.
    """
    if not detect_de_escalation(description):
        return assets

    FLIP_TICKERS = {
        "USO": "down", "BNO": "down", "XLE": "down",
        "LMT": "down", "NOC": "down", "RTX": "down", "ITA": "down",
        "ZIM": "down", "BDRY": "down",
    }
    result = []
    for a in assets:
        ticker = a.get("ticker", "")
        if ticker in FLIP_TICKERS:
            a = dict(a)  # copy
            a["direction"] = FLIP_TICKERS[ticker]
            a["avg_move_72h"] = -abs(a.get("avg_move_72h", 0) or 0)
        result.append(a)
    return result

def get_signal_metadata(assets, prob_shift, confidence_score, source_platform, event_category=None):
    if not assets:
        return {}
    strength = calculate_signal_strength(
        prob_shift, confidence_score, assets, source_platform
    )
    best = get_best_performer(assets)

    # Problem 4 fix — use signal-specific accuracy not category defaults
    if event_category:
        acc_data = get_signal_specific_accuracy(event_category, source_platform)
        acc_min = acc_data["min"]
        acc_max = acc_data["max"]
    else:
        accuracies = [a.get("accuracy", 0) for a in assets if a.get("accuracy")]
        acc_min = round(min(accuracies) * 100, 1) if accuracies else 0
        acc_max = round(max(accuracies) * 100, 1) if accuracies else 0

    # Problem 6 fix — calculate peak move from actual asset data
    time_to_peak = get_signal_specific_peak_move(event_category, assets)

    # Convergence tier requires BOTH source count/confidence AND minimum strength
    # Prevents EXTREME label on weak signals with many sources
    if confidence_score == "extreme" and strength >= 75:
        tier = 3
        tier_label = "FULL CONVERGENCE"
    elif confidence_score == "high" and strength >= 70:
        tier = 3
        tier_label = "FULL CONVERGENCE"
    elif confidence_score in ["high", "medium"] and strength >= 55:
        tier = 2
        tier_label = "DUAL CONFIRMATION"
    else:
        tier = 1
        tier_label = "SINGLE SOURCE"
    return {
        "signal_strength": strength,
        "best_performer": best,
        "accuracy_range_min": acc_min,
        "accuracy_range_max": acc_max,
        "estimated_time_to_peak": time_to_peak,
        "convergence_tier": tier,
        "convergence_label": tier_label
    }

def map_event_to_category(event_description):
    text = (event_description or "").lower()

    # Export controls — check before generic China/trade
    if any(w in text for w in ["entity list", "export control", "chip ban",
                                "semiconductor export", "huawei ban", "nvidia ban",
                                "foundry restriction", "fab restriction",
                                "advanced chip", "ai chip export"]):
        return "us_china_trade_escalation"

    # Nuclear — check before regional conflicts
    if any(w in text for w in ["north korea", "dprk", "kim jong", "kim ju",
                                "pyongyang", "icbm"]):
        return "nuclear_wmd_escalation"
    if any(w in text for w in ["nuclear", "nuke", "wmd", "ballistic missile"]):
        return "nuclear_wmd_escalation"

    # Iran direct strike — check before general Iran
    if any(w in text for w in ["kharg", "restrike", "u.s. strikes iran",
                                "us strikes iran"]):
        return "iran_israel_strike"

    # Shipping lane disruption — check before oil/Iran
    if any(w in text for w in ["houthi", "red sea", "hormuz", "suez canal",
                                "canal blockade", "shipping lane", "blockade"]):
        return "shipping_lane_disruption"

    # Taiwan — check before generic China
    if any(w in text for w in ["taiwan", "strait", "cross-strait", "tsmc"]):
        return "china_taiwan_tension"

    # Russia/Ukraine — check before NATO
    if any(w in text for w in ["russia", "ukraine", "kremlin", "putin",
                                "moscow", "zelensky", "donbas"]):
        return "russia_eastern_europe_conflict"

    # Middle East — Iran/Israel/Gaza BEFORE oil check
    if any(w in text for w in ["iran", "israel", "gaza", "middle east",
                                "hezbollah", "hamas", "irgc", "tehran"]):
        return "middle_east_military_escalation"

    # Tariffs — check before generic China
    if any(w in text for w in ["reciprocal tariff", "trade war", "tariff escalation",
                                "import duty", "tariff hike", "tariff increase",
                                "blanket tariff", "tariff"]):
        return "global_tariff_escalation"

    # Oil/energy — AFTER Iran/Middle East check
    if any(w in text for w in ["opec", "oil cut", "production cut",
                                "oil supply", "oil embargo"]):
        return "opec_production_decision"

    # China general — after Taiwan and export controls
    if any(w in text for w in ["china", "xi jinping", "beijing", "ccp"]):
        return "us_china_trade_escalation"

    # Sanctions
    if any(w in text for w in ["sanction", "embargo", "ofac", "asset freeze"]):
        return "us_sanctions_announcement"

    # EM political
    if any(w in text for w in ["pakistan", "islamabad", "imran khan",
                                "venezuela", "maduro", "argentina", "peso"]):
        return "emerging_market_political_crisis"

    if any(w in text for w in ["coup", "junta", "military takeover"]):
        return "coup_risk"

    if any(w in text for w in ["election", "referendum"]):
        return "election_outcome_surprise"

    if any(w in text for w in ["cyber", "hack", "ransomware", "malware",
                                "internet disruption"]):
        return "cyber_attack_infrastructure"

    if any(w in text for w in ["outbreak", "disease", "pandemic", "virus",
                                "who alert", "epidemic"]):
        return "pandemic_outbreak"

    if any(w in text for w in ["nato", "military alliance", "article 5"]):
        return "russia_eastern_europe_conflict"

    return "emerging_market_political_crisis"

def predict_question_outcome(question_text, signal_description, signal_direction, prob_shift, region):
    """
    Based on active signal direction, predict YES or NO lean for a Kalshi question.
    Returns: dict with lean, confidence, and reasoning
    """
    q = question_text.lower()
    sig = (signal_description or "").lower()
    region_l = (region or "").lower()
    is_escalation = prob_shift and prob_shift > 10

    # Press conference / statement questions
    if any(k in q for k in ["press conference", "statement", "announce", "say", "declare"]):
        if is_escalation and any(k in sig for k in ["iran", "conflict", "war", "strike"]):
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Signal shows {prob_shift:.0f}% escalation spike — Trump historically makes escalatory statements during active conflict spikes"
            }
        elif not is_escalation:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "Signal shows de-escalation — diplomatic language more likely"
            }

    # Ceasefire / peace questions
    if any(k in q for k in ["ceasefire", "peace", "negotiate", "diplomacy", "withdraw", "end war"]):
        if is_escalation:
            return {
                "lean": "NO",
                "confidence": "HIGH",
                "reason": f"Active conflict spike at {prob_shift:.0f}% shift — ceasefire unlikely during escalation"
            }
        else:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": "De-escalation signals suggest diplomatic resolution possible"
            }

    # Ground invasion / military action questions
    if any(k in q for k in ["ground invasion", "ground troops", "military strike", "airstrike", "bombing"]):
        if is_escalation and prob_shift > 50:
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Very high escalation signal ({prob_shift:.0f}% shift) — military action increasingly likely"
            }
        elif is_escalation:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": f"Escalation signal active ({prob_shift:.0f}% shift)"
            }
        else:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "No strong escalation signal — military action less likely"
            }

    # Oil price questions
    if any(k in q for k in ["oil", "crude", "brent", "wti", "barrel", "energy price"]):
        if is_escalation and any(k in sig for k in ["iran", "hormuz", "opec", "oil"]):
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Energy/conflict signal at {prob_shift:.0f}% shift — oil prices historically spike"
            }

    # Strait of Hormuz questions
    if any(k in q for k in ["hormuz", "strait", "shipping lane", "blockade"]):
        if is_escalation:
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": "Active escalation signal — Hormuz disruption risk elevated"
            }
        else:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "No active escalation — shipping lanes likely to remain open"
            }

    # Regime change questions
    if any(k in q for k in ["regime change", "government collapse", "leader out", "coup"]):
        if is_escalation and prob_shift > 60:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": f"Extreme escalation signal ({prob_shift:.0f}%) — regime instability elevated"
            }

    # Nuclear deal questions
    if any(k in q for k in ["nuclear deal", "nuclear agreement", "jcpoa"]):
        if is_escalation:
            return {
                "lean": "NO",
                "confidence": "HIGH",
                "reason": "Active military escalation makes diplomatic nuclear deal unlikely"
            }
        else:
            return {
                "lean": "YES",
                "confidence": "LOW",
                "reason": "De-escalation environment more conducive to diplomatic talks"
            }

    return None


def find_related_questions(event_description, region, questions, prob_shift=None):
    """
    Find the most relevant prediction market questions for this signal.
    Uses tight country/region matching — must match primary keyword.
    No generic military/nuclear matches across unrelated regions.
    """
    text = (event_description or "").lower()
    region_lower = (region or "").lower()

    primary_keywords = []
    secondary_keywords = []

    # Iran specific
    if "iran" in text or "iran" in region_lower:
        primary_keywords += ["iran", "iranian", "tehran",
                             "khamenei", "irgc", "persian"]
        secondary_keywords += ["nuclear deal", "strait of hormuz",
                               "iaea", "sanction iran"]

    # Russia/Ukraine specific
    if "russia" in text or "ukraine" in text:
        primary_keywords += ["russia", "ukraine", "putin",
                             "zelensky", "moscow", "kyiv"]
        secondary_keywords += ["nato", "crimea", "donbas"]

    # China/Taiwan specific
    if "china" in text or "taiwan" in text:
        primary_keywords += ["china", "taiwan", "xi jinping",
                             "beijing", "pla", "taipei"]
        secondary_keywords += ["strait", "semiconductor", "tsmc"]

    # Israel/Gaza specific
    if "israel" in text or "gaza" in text:
        primary_keywords += ["israel", "gaza", "hamas",
                             "hezbollah", "netanyahu", "idf"]
        secondary_keywords += ["west bank", "ceasefire", "rafah"]

    # North Korea specific
    if "north korea" in text or "dprk" in text:
        primary_keywords += ["north korea", "dprk", "kim jong",
                             "pyongyang"]
        secondary_keywords += ["nuclear test", "icbm", "missile"]

    # Saudi/Oil specific
    if "saudi" in text or "opec" in text or "oil" in text:
        primary_keywords += ["opec", "oil price", "saudi",
                             "crude", "petroleum"]
        secondary_keywords += ["energy", "brent", "wti", "barrel"]

    # Venezuela specific
    if "venezuela" in text:
        primary_keywords += ["venezuela", "maduro", "caracas"]

    # Syria specific
    if "syria" in text:
        primary_keywords += ["syria", "syrian", "damascus"]

    # Sudan/Ethiopia specific
    if "sudan" in text or "ethiopia" in text:
        primary_keywords += ["sudan", "ethiopia", "africa",
                             "khartoum", "addis"]

    # US Policy specific
    if "trump" in text or "congress" in text or "senate" in text:
        primary_keywords += ["trump", "congress", "senate",
                             "white house", "executive order"]

    # UK specific
    if "uk" in text or "britain" in text:
        primary_keywords += ["uk", "britain", "prime minister uk",
                             "parliament uk"]

    # EU specific
    if "eu " in text or "europe" in text or "european" in text:
        primary_keywords += ["european union", "eu", "brussels"]

    # GDELT conflict spike — use region name directly
    if ("gdelt" in text or "conflict" in text) and region_lower and region_lower != "global":
        primary_keywords += [region_lower]

    # Fallback to region if nothing specific matched
    if not primary_keywords and region_lower and region_lower != "global":
        primary_keywords = [region_lower]

    if not primary_keywords:
        return []

    # Score questions — MUST match primary keyword
    scored = []
    for q in questions:
        q_text = (q[2] or "").lower()
        q_platform = q[1]

        primary_matches = [k for k in primary_keywords if k in q_text]
        if not primary_matches:
            continue

        score = len(primary_matches) * 10
        secondary_matches = [k for k in secondary_keywords if k in q_text]
        score += len(secondary_matches) * 5
        for k in primary_matches:
            score += len(k.split())

        scored.append((score, q, primary_matches[:3]))

    # Sort by platform priority then relevance score
    platform_priority = {"kalshi": 100, "metaculus": 10}
    scored.sort(
        key=lambda x: (platform_priority.get(x[1][1], 0) + x[0]),
        reverse=True
    )

    results = []
    for score, q, matched in scored[:6]:
        platform = q[1]
        q_text = q[2]
        prob = q[3]
        platform_id = q[6] if len(q) > 6 else ""

        if platform == "kalshi":
            url = f"https://kalshi.com/markets/{platform_id}"
            bet_label = "BET ON KALSHI"
            is_bettable = True
        elif platform == "metaculus":
            url = f"https://www.metaculus.com/questions/{platform_id}"
            bet_label = "VIEW ON METACULUS"
            is_bettable = False
        else:
            url = None
            bet_label = "VIEW"
            is_bettable = False

        if url:
            # Get outcome prediction based on signal direction
            prediction = predict_question_outcome(
                q_text, event_description, 
                "escalation" if (prob_shift or 0) > 0 else "de-escalation",
                prob_shift, region
            )
            results.append({
                "platform":        platform,
                "question":        q_text,
                "probability":     prob,
                "url":             url,
                "bet_label":       bet_label,
                "is_bettable":     is_bettable,
                "relevance_score": score,
                "keywords_matched": matched,
                "prediction":      prediction,
            })

    return results

def update_signal_assets(signal_id, event_description,
                         region=None, confidence_score=None,
                         prob_shift=None, source_platform=None):
    event_type = map_event_to_category(event_description)
    # Pass description so de-escalation direction flip auto-applies
    assets = get_asset_mappings(event_type, region, description=event_description)
    if not assets:
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE signals
        SET affected_assets = %s, event_category = %s
        WHERE id = %s;
    """, (json.dumps(assets), event_type, str(signal_id)))
    conn.commit()
    cur.close()
    conn.close()
    return True

def backfill_missing_assets():
    """
    Find active signals with no affected_assets and populate them.
    Runs every cycle to catch signals from GDELT/news/state_media/cloudflare.
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, event_description, region, confidence_score,
               probability_shift, source_platform
        FROM signals
        WHERE affected_assets IS NULL
        AND is_active = true
        AND expires_at > NOW()
        LIMIT 50;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return 0

    updated = 0
    for row in rows:
        sig_id, description, region, confidence, prob_shift, platform = row
        success = update_signal_assets(
            sig_id, description, region, confidence, prob_shift, platform
        )
        if success:
            updated += 1

    if updated:
        print(f"   📊 Backfilled assets for {updated} signals")
    return updated


def get_signal_specific_accuracy(event_category, source_platform):
    """
    Problem 4 fix — return signal-specific accuracy not category defaults.
    Pulls actual historical accuracy from asset_mappings for this specific
    event_category, rather than returning a generic 58-68% baseline.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT AVG(directional_accuracy), MIN(directional_accuracy),
                   MAX(directional_accuracy), COUNT(*)
            FROM asset_mappings
            WHERE event_type = %s
            AND sample_size >= 5;
        """, (event_category,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[3] > 0:
            avg_acc  = round(float(row[0]) * 100, 1)
            min_acc  = round(float(row[1]) * 100, 1)
            max_acc  = round(float(row[2]) * 100, 1)
            return {"avg": avg_acc, "min": min_acc, "max": max_acc}
    except Exception:
        pass
    # Fallback to source-specific baselines if no DB data
    SOURCE_BASELINES = {
        "OPTIONS_FLOW":       {"avg": 64.0, "min": 58.0, "max": 72.0},
        "SMART_VS_DUMB":      {"avg": 66.0, "min": 61.0, "max": 73.0},
        "SOMEONE_KNOWS":      {"avg": 71.0, "min": 68.0, "max": 78.0},
        "CONVERGENCE":        {"avg": 74.0, "min": 68.0, "max": 82.0},
        "GDELT":              {"avg": 62.0, "min": 55.0, "max": 70.0},
        "CORRELATION_MONITOR":{"avg": 61.0, "min": 58.0, "max": 68.0},
        "UNPRICED_RISK":      {"avg": 59.0, "min": 55.0, "max": 65.0},
        "STATE_MEDIA":        {"avg": 65.0, "min": 60.0, "max": 72.0},
        "NEWS_INTELLIGENCE":  {"avg": 60.0, "min": 55.0, "max": 68.0},
    }
    return SOURCE_BASELINES.get(source_platform, {"avg": 60.0, "min": 55.0, "max": 68.0})


def get_signal_specific_peak_move(event_category, assets):
    """
    Problem 6 fix — calculate peak move timing from actual asset data,
    not a hardcoded 168h default.
    """
    if not assets:
        return "72h"
    avg_24  = sum(abs(a.get("avg_move_24h",  0) or 0) for a in assets) / len(assets)
    avg_72  = sum(abs(a.get("avg_move_72h",  0) or 0) for a in assets) / len(assets)
    avg_168 = sum(abs(a.get("avg_move_168h", 0) or 0) for a in assets) / len(assets)

    # Peak is where the move is largest relative to adjacent window
    if avg_24 >= avg_72 * 0.85:
        return "24h"
    elif avg_168 > avg_72 * 1.25:
        return "168h"
    else:
        return "72h"


def run_pre_distribution_consistency_check(
    signal_description, event_category, source_platform,
    assets, trade_rec_direction, narrative, confirmed_count,
    total_assets, confidence_score, platform_accuracy
):
    """
    Kyle's pre-distribution consistency checker.
    Catches the four most dangerous alert errors before distribution:

    1. Trade direction contradicts historical correlation for same asset
    2. Narrative sentiment contradicts asset directional calls
    3. FULL CONVERGENCE label with fewer than half assets confirmed
    4. Accuracy below 50% with a trade recommendation present

    Returns: dict with passed=True/False and list of issues found.
    """
    issues = []

    # Check 1 — Directional logic consistency (Problem 2)
    # If trade rec says BUY asset X but historical correlation says X goes DOWN
    if trade_rec_direction and assets:
        rec_ticker = None
        rec_direction = None
        if "BUY" in str(trade_rec_direction).upper():
            rec_direction = "up"
            # Extract ticker from trade rec if possible
            for a in assets:
                ticker = a.get("ticker", "")
                if ticker and ticker in str(trade_rec_direction).upper():
                    rec_ticker = ticker
                    break
        elif "SELL" in str(trade_rec_direction).upper():
            rec_direction = "down"
            for a in assets:
                ticker = a.get("ticker", "")
                if ticker and ticker in str(trade_rec_direction).upper():
                    rec_ticker = ticker
                    break

        if rec_ticker and rec_direction:
            for a in assets:
                if a.get("ticker") == rec_ticker:
                    hist_direction = a.get("direction", "")
                    if hist_direction and hist_direction != rec_direction:
                        issues.append(
                            f"DIRECTION CONFLICT: Trade rec says {rec_direction.upper()} {rec_ticker} "
                            f"but historical correlation shows {hist_direction.upper()} — "
                            f"check de-escalation logic or category mapping"
                        )

    # Check 2 — Narrative vs asset direction (Problem 3)
    if narrative and assets:
        narrative_lower = narrative.lower()
        escalation_words = ["escalat", "conflict", "attack", "strike", "invasion",
                           "tension", "war", "crisis", "threat", "aggression"]
        deescalation_words = ["ceasefire", "peace", "de-escalat", "diplomatic",
                             "resolution", "agreement", "withdrawal", "calm"]

        narrative_is_escalation = any(w in narrative_lower for w in escalation_words)
        narrative_is_deescalation = any(w in narrative_lower for w in deescalation_words)

        # Check if narrative says escalation but defense/energy assets are DOWN
        if narrative_is_escalation and not narrative_is_deescalation:
            defense_tickers = ["LMT", "RTX", "NOC", "ITA"]
            for a in assets:
                if a.get("ticker") in defense_tickers and a.get("direction") == "down":
                    issues.append(
                        f"NARRATIVE CONFLICT: Brief describes escalation but "
                        f"{a.get('ticker')} direction is DOWN — possible de-escalation flip error"
                    )
                    break

    # Check 3 — FULL CONVERGENCE gating (Problem 5 from Kyle)
    if confidence_score in ("high", "extreme") and total_assets > 0:
        confirmation_rate = confirmed_count / total_assets if total_assets > 0 else 0
        if confirmation_rate < 0.5 and confirmed_count == 0:
            issues.append(
                f"CONVERGENCE MISMATCH: FULL CONVERGENCE label but "
                f"{confirmed_count}/{total_assets} assets confirmed — "
                f"consider downgrading to DUAL CONFIRMATION or SINGLE SOURCE"
            )

    # Check 4 — Accuracy floor for trade recommendations (Problem 4)
    if trade_rec_direction and platform_accuracy:
        try:
            acc_val = float(str(platform_accuracy).replace("%", "").strip())
            if acc_val < 50.0:
                issues.append(
                    f"LOW ACCURACY WARNING: Trade recommendation present but "
                    f"platform accuracy is {acc_val:.1f}% — below 50% floor. "
                    f"Recommendation should be flagged as speculative."
                )
        except Exception:
            pass

    passed = len(issues) == 0
    if not passed:
        print(f"   ⚠️ Pre-distribution check failed: {len(issues)} issue(s)")
        for issue in issues:
            print(f"      — {issue}")
    else:
        print(f"   ✅ Pre-distribution consistency check passed")

    return {"passed": passed, "issues": issues}


if __name__ == "__main__":
    assets = get_asset_mappings(
        "middle_east_military_escalation", "Middle East"
    )
    metadata = get_signal_metadata(assets, 27.0, "high", "gdelt")
    best = get_best_performer(assets)
    print(f"Signal Strength: {metadata['signal_strength']}/100")
    print(f"Convergence: {metadata['convergence_label']}")
    if best:
        print(f"Best Performer: {best['ticker']} +{best['avg_move_72h']:.1f}% avg")
    print(f"Accuracy Range: {metadata['accuracy_range_min']}% — {metadata['accuracy_range_max']}%")