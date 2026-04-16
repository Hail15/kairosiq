-- KairosIQ Database Schema
-- Run this in Supabase SQL Editor

-- 1. Prediction Questions
-- Stores every geopolitical question from Polymarket, Kalshi, Metaculus
CREATE TABLE IF NOT EXISTS prediction_questions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    platform_id VARCHAR(255) NOT NULL,
    question_text TEXT NOT NULL,
    category VARCHAR(100),
    region VARCHAR(100),
    resolution_date TIMESTAMP,
    current_probability FLOAT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, platform_id)
);

-- 2. Probability Snapshots
-- Time series of probability values pulled every 15 minutes
CREATE TABLE IF NOT EXISTS probability_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question_id UUID REFERENCES prediction_questions(id),
    probability FLOAT NOT NULL,
    volume FLOAT,
    snapshot_time TIMESTAMP DEFAULT NOW()
);

-- 3. Signals
-- Every signal KairosIQ generates
CREATE TABLE IF NOT EXISTS signals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_description TEXT NOT NULL,
    region VARCHAR(100),
    event_category VARCHAR(100),
    probability_before FLOAT,
    probability_after FLOAT,
    probability_shift FLOAT,
    confidence_score VARCHAR(20),
    source_platform VARCHAR(50),
    source_question_id UUID REFERENCES prediction_questions(id),
    affected_assets JSONB,
    signal_time TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    checksum VARCHAR(64),
    wif_version VARCHAR(20) DEFAULT 'WIF-1.0'
);

-- 4. Bets
-- Every prediction market bet placed during proof of concept
CREATE TABLE IF NOT EXISTS bets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID REFERENCES signals(id),
    platform VARCHAR(50) NOT NULL,
    question_text TEXT,
    direction VARCHAR(10),
    stake FLOAT,
    odds FLOAT,
    potential_payout FLOAT,
    bet_time TIMESTAMP DEFAULT NOW(),
    signal_time TIMESTAMP,
    time_gap_minutes FLOAT,
    blockchain_hash VARCHAR(255),
    result VARCHAR(10),
    actual_payout FLOAT,
    resolved_at TIMESTAMP
);

-- 5. Signal Outcomes
-- Asset prices at 24/72/168 hours after every signal
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID REFERENCES signals(id),
    asset_ticker VARCHAR(20),
    price_at_signal FLOAT,
    price_at_24h FLOAT,
    price_at_72h FLOAT,
    price_at_168h FLOAT,
    direction_correct_24h BOOLEAN,
    direction_correct_72h BOOLEAN,
    direction_correct_168h BOOLEAN,
    agent_narrative TEXT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- 7. Signal Briefs
-- Stores AI-generated intelligence briefs per signal
-- Separate table avoids ALTER TABLE timeout on large signals table
CREATE TABLE IF NOT EXISTS signal_briefs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,
    ai_brief TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 8. Signal Alerts Sent
-- Tracks which signals have been emailed — prevents duplicate alerts
CREATE TABLE IF NOT EXISTS signal_alerts_sent (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,
    event_category VARCHAR(100),
    region VARCHAR(100),
    source_platform VARCHAR(50),
    confidence_score VARCHAR(20),
    probability_shift FLOAT,
    alerted_at TIMESTAMP DEFAULT NOW()
);

-- 9. Second Order Effects
-- Chain reaction effects generated for each signal
CREATE TABLE IF NOT EXISTS second_order_effects (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL,
    order_level INTEGER NOT NULL,
    transmission_channel VARCHAR(100),
    effect_description TEXT NOT NULL,
    affected_assets JSONB,
    time_horizon VARCHAR(20),
    probability_score FLOAT,
    historical_accuracy FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 10. Agent Enrichment
-- Stores all agent outputs per signal so dashboard can display them
CREATE TABLE IF NOT EXISTS agent_enrichment (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,
    brief TEXT,
    portfolio_assessment TEXT,
    trade_ticker VARCHAR(20),
    trade_action VARCHAR(10),
    trade_conviction VARCHAR(10),
    trade_reason TEXT,
    trade_sizing TEXT,
    trade_already_held BOOLEAN DEFAULT false,
    stop_loss VARCHAR(20),
    take_profit VARCHAR(20),
    exit_rationale TEXT,
    entry_timing VARCHAR(10),
    entry_guidance TEXT,
    entry_rsi FLOAT,
    entry_day_change FLOAT,
    convergence_sources INTEGER,
    convergence_guidance TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 11. Agent Feedback
-- Stores operator feedback on signals to improve triage
CREATE TABLE IF NOT EXISTS agent_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL UNIQUE,
    feedback_type VARCHAR(20) NOT NULL, -- noise / correct / wrong
    region VARCHAR(100),
    event_category VARCHAR(100),
    source_platform VARCHAR(50),
    description_snippet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 12. Agent Suppression Rules
-- Temporary keyword suppression rules set by operator
CREATE TABLE IF NOT EXISTS agent_suppression_rules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 13. GPI Daily Snapshots
-- Historical GPI scores for trend charting and publishing
-- 14. Signal Sources
-- Stores raw source evidence for every signal for frontend verification
CREATE TABLE IF NOT EXISTS signal_sources (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id UUID NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    title TEXT,
    url TEXT,
    source_name VARCHAR(200),
    published_at TIMESTAMP,
    relevance_score FLOAT,
    snippet TEXT,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_signal_sources_signal_id ON signal_sources(signal_id);

CREATE TABLE IF NOT EXISTS gpi_daily_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    gpi_score INTEGER NOT NULL,
    vix_value FLOAT,
    gap_points FLOAT,
    armed_conflict FLOAT,
    energy_resource FLOAT,
    political_diplomatic FLOAT,
    cyber_information FLOAT,
    economic_financial FLOAT,
    maritime_trade FLOAT,
    nuclear_wmd FLOAT,
    active_signal_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Maps event types and regions to historically correlated assets
CREATE TABLE IF NOT EXISTS asset_mappings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    region VARCHAR(100) NOT NULL,
    asset_ticker VARCHAR(20) NOT NULL,
    asset_name VARCHAR(255),
    asset_class VARCHAR(50),
    historical_direction VARCHAR(10),
    avg_move_24h FLOAT,
    avg_move_72h FLOAT,
    avg_move_168h FLOAT,
    directional_accuracy FLOAT,
    sample_size INTEGER,
    confidence_rating VARCHAR(20),
    -- Concept drift fields
    accuracy_7d FLOAT,
    accuracy_30d FLOAT,
    accuracy_90d FLOAT,
    drift_score FLOAT DEFAULT 0,       -- 0=stable, 1=drifting, 2=severe
    last_decay_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- GDELT dynamic baselines — rolling 30-day article counts per country
CREATE TABLE IF NOT EXISTS gdelt_baselines (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    country VARCHAR(50) NOT NULL UNIQUE,
    baseline_30d FLOAT NOT NULL,       -- rolling avg articles per cycle
    baseline_7d FLOAT,                 -- recent 7-day avg
    sample_cycles INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Accuracy windows — rolling 7/30/90 day signal accuracy per category
CREATE TABLE IF NOT EXISTS accuracy_windows (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_category VARCHAR(100),
    asset_ticker VARCHAR(20),
    window_days INTEGER NOT NULL,      -- 7, 30, or 90
    accuracy_pct FLOAT,
    correct_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    drift_alert BOOLEAN DEFAULT false, -- true if 7d << 30d significantly
    computed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(event_category, asset_ticker, window_days)
);

-- Framework versions — every signal stamped with WIF version
CREATE TABLE IF NOT EXISTS framework_versions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    version VARCHAR(20) NOT NULL UNIQUE,  -- e.g. 'WIF-1.0', 'WIF-1.1'
    description TEXT,
    changes TEXT,
    activated_at TIMESTAMP DEFAULT NOW(),
    is_current BOOLEAN DEFAULT false
);

-- Insert initial version
INSERT INTO framework_versions (version, description, changes, is_current)
VALUES ('WIF-1.0', 'Worsley Intelligence Framework — Initial Release',
        'Base asset mappings, GDELT anomaly detection, prediction market signals',
        true)
ON CONFLICT (version) DO NOTHING;