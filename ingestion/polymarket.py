# ingestion/polymarket.py
# Polymarket blocks US users — accepting_orders is False for all markets
# when accessed from a US IP address.
# KairosIQ uses Kalshi (US-licensed) and Metaculus as primary sources.

def run_polymarket_ingestion():
    print("\n🔄 Starting Polymarket ingestion...")
    print("   ⚠️  Polymarket is not available to US users.")
    print("   ✅  Using Kalshi (US-licensed) + Metaculus instead.")
    print("✅ Polymarket skipped.")

if __name__ == "__main__":
    run_polymarket_ingestion()