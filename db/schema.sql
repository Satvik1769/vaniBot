-- Battery Smart Voicebot Database Schema
-- PostgreSQL 15+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- CORE TABLES
-- ============================================

-- Drivers (customers who use battery swap service)
CREATE TABLE drivers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(15) UNIQUE NOT NULL,
    name VARCHAR(100),
    email VARCHAR(100),
    preferred_language VARCHAR(10) DEFAULT 'hi-en',  -- hi, en, hi-en (Hinglish)
    city VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_drivers_phone ON drivers(phone_number);
CREATE INDEX idx_drivers_city ON drivers(city);

-- Stations (battery swap stations)
CREATE TABLE stations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,  -- Station code like 'DLH-LXN-001'
    name VARCHAR(100) NOT NULL,
    address TEXT,
    landmark VARCHAR(200),
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    city VARCHAR(50) NOT NULL,
    pincode VARCHAR(10),
    operating_hours VARCHAR(50) DEFAULT '06:00-22:00',
    contact_phone VARCHAR(15),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_stations_city ON stations(city);
CREATE INDEX idx_stations_location ON stations(latitude, longitude);
CREATE INDEX idx_stations_code ON stations(code);

-- Station inventory (real-time battery availability)
CREATE TABLE station_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    station_id UUID NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    available_batteries INT DEFAULT 0,
    charging_batteries INT DEFAULT 0,
    total_slots INT DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(station_id)
);

CREATE INDEX idx_inventory_station ON station_inventory(station_id);

-- ============================================
-- SUBSCRIPTION TABLES
-- ============================================

-- Subscription plans
CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,  -- 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'
    name VARCHAR(50) NOT NULL,
    name_hi VARCHAR(100),  -- Hindi name
    price DECIMAL(10, 2) NOT NULL,
    validity_days INT NOT NULL,
    swaps_included INT NOT NULL,  -- -1 for unlimited
    extra_swap_price DECIMAL(10, 2) DEFAULT 35.00,
    description_en TEXT,
    description_hi TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Driver subscriptions
CREATE TABLE driver_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES subscription_plans(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- active, expired, cancelled, suspended
    swaps_used INT DEFAULT 0,
    auto_renew BOOLEAN DEFAULT false,
    payment_method VARCHAR(50),  -- upi, card, wallet
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_driver ON driver_subscriptions(driver_id);
CREATE INDEX idx_subscriptions_status ON driver_subscriptions(status);
CREATE INDEX idx_subscriptions_end_date ON driver_subscriptions(end_date);

-- ============================================
-- SWAP & INVOICE TABLES
-- ============================================

-- Battery swaps
CREATE TABLE swaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    station_id UUID NOT NULL REFERENCES stations(id),
    subscription_id UUID REFERENCES driver_subscriptions(id),
    old_battery_id VARCHAR(50),
    new_battery_id VARCHAR(50),
    old_battery_charge_level INT,  -- Percentage
    new_battery_charge_level INT,  -- Percentage
    swap_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_subscription_swap BOOLEAN DEFAULT true,
    charge_amount DECIMAL(10, 2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'completed'  -- completed, failed, refunded
);

CREATE INDEX idx_swaps_driver ON swaps(driver_id);
CREATE INDEX idx_swaps_station ON swaps(station_id);
CREATE INDEX idx_swaps_time ON swaps(swap_time DESC);
CREATE INDEX idx_swaps_driver_time ON swaps(driver_id, swap_time DESC);

-- Invoices
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(20) UNIQUE NOT NULL,  -- INV-YYYYMM-XXXXXX
    driver_id UUID NOT NULL REFERENCES drivers(id),
    swap_id UUID REFERENCES swaps(id),
    subscription_id UUID REFERENCES driver_subscriptions(id),
    invoice_type VARCHAR(20) NOT NULL,  -- 'swap', 'subscription', 'extra_swap'
    amount DECIMAL(10, 2) NOT NULL,
    tax_amount DECIMAL(10, 2) DEFAULT 0,
    total_amount DECIMAL(10, 2) NOT NULL,
    description TEXT,
    description_hi TEXT,
    payment_status VARCHAR(20) DEFAULT 'paid',  -- paid, pending, failed
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_invoices_driver ON invoices(driver_id);
CREATE INDEX idx_invoices_number ON invoices(invoice_number);
CREATE INDEX idx_invoices_swap ON invoices(swap_id);

-- ============================================
-- DSK (Dealer Service Kiosk) TABLES
-- ============================================

-- DSK locations
CREATE TABLE dsk_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    address TEXT,
    landmark VARCHAR(200),
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    city VARCHAR(50) NOT NULL,
    pincode VARCHAR(10),
    phone VARCHAR(15),
    operating_hours VARCHAR(50) DEFAULT '09:00-18:00',
    services TEXT[],  -- ['activation', 'repair', 'support', 'battery_replacement']
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_dsk_city ON dsk_locations(city);
CREATE INDEX idx_dsk_location ON dsk_locations(latitude, longitude);

-- Driver leave requests
CREATE TABLE driver_leaves (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason VARCHAR(200),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    processed_by VARCHAR(100)
);

CREATE INDEX idx_leaves_driver ON driver_leaves(driver_id);
CREATE INDEX idx_leaves_dates ON driver_leaves(start_date, end_date);

-- ============================================
-- CONVERSATION & ANALYTICS TABLES
-- ============================================

-- Conversation logs
CREATE TABLE conversation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    driver_id UUID REFERENCES drivers(id),
    phone_number VARCHAR(15),
    channel VARCHAR(20) DEFAULT 'voice',  -- voice, chat, sms
    language_detected VARCHAR(10),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INT,
    turns_count INT DEFAULT 0,
    handoff_occurred BOOLEAN DEFAULT false,
    handoff_reason VARCHAR(100),
    final_confidence_score DECIMAL(3, 2),
    final_sentiment_score DECIMAL(3, 2),
    resolution_status VARCHAR(20),  -- resolved, escalated, abandoned
    intents_detected TEXT[],
    summary TEXT
);

CREATE INDEX idx_conversations_session ON conversation_logs(session_id);
CREATE INDEX idx_conversations_driver ON conversation_logs(driver_id);
CREATE INDEX idx_conversations_phone ON conversation_logs(phone_number);
CREATE INDEX idx_conversations_started ON conversation_logs(started_at DESC);

-- Conversation turns (individual messages)
CREATE TABLE conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversation_logs(id) ON DELETE CASCADE,
    turn_number INT NOT NULL,
    role VARCHAR(10) NOT NULL,  -- 'user', 'bot'
    message TEXT NOT NULL,
    message_hindi TEXT,  -- Transliterated/translated version
    intent VARCHAR(50),
    intent_confidence DECIMAL(3, 2),
    entities JSONB,
    sentiment_score DECIMAL(3, 2),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_turns_conversation ON conversation_turns(conversation_id);
CREATE INDEX idx_turns_timestamp ON conversation_turns(timestamp);

-- ============================================
-- UTILITY FUNCTIONS
-- ============================================

-- Function to generate invoice number
CREATE OR REPLACE FUNCTION generate_invoice_number()
RETURNS TEXT AS $$
DECLARE
    seq_num INT;
    invoice_num TEXT;
BEGIN
    SELECT COALESCE(MAX(CAST(SUBSTRING(invoice_number FROM 12) AS INT)), 0) + 1
    INTO seq_num
    FROM invoices
    WHERE invoice_number LIKE 'INV-' || TO_CHAR(NOW(), 'YYYYMM') || '-%';

    invoice_num := 'INV-' || TO_CHAR(NOW(), 'YYYYMM') || '-' || LPAD(seq_num::TEXT, 6, '0');
    RETURN invoice_num;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate distance between two points (Haversine formula)
CREATE OR REPLACE FUNCTION calculate_distance(
    lat1 DECIMAL, lon1 DECIMAL,
    lat2 DECIMAL, lon2 DECIMAL
)
RETURNS DECIMAL AS $$
DECLARE
    R DECIMAL := 6371;  -- Earth's radius in km
    dlat DECIMAL;
    dlon DECIMAL;
    a DECIMAL;
    c DECIMAL;
BEGIN
    dlat := RADIANS(lat2 - lat1);
    dlon := RADIANS(lon2 - lon1);
    a := SIN(dlat/2) * SIN(dlat/2) + COS(RADIANS(lat1)) * COS(RADIANS(lat2)) * SIN(dlon/2) * SIN(dlon/2);
    c := 2 * ATAN2(SQRT(a), SQRT(1-a));
    RETURN R * c;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_drivers_updated_at
    BEFORE UPDATE ON drivers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscriptions_updated_at
    BEFORE UPDATE ON driver_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- View: Active driver subscriptions with plan details
CREATE VIEW v_active_subscriptions AS
SELECT
    ds.id AS subscription_id,
    d.id AS driver_id,
    d.phone_number,
    d.name AS driver_name,
    d.preferred_language,
    sp.code AS plan_code,
    sp.name AS plan_name,
    sp.name_hi AS plan_name_hi,
    sp.price AS plan_price,
    sp.swaps_included,
    ds.swaps_used,
    CASE
        WHEN sp.swaps_included = -1 THEN -1
        ELSE sp.swaps_included - ds.swaps_used
    END AS swaps_remaining,
    ds.start_date,
    ds.end_date,
    ds.end_date - CURRENT_DATE AS days_remaining,
    ds.auto_renew,
    ds.status
FROM driver_subscriptions ds
JOIN drivers d ON ds.driver_id = d.id
JOIN subscription_plans sp ON ds.plan_id = sp.id
WHERE ds.status = 'active' AND ds.end_date >= CURRENT_DATE;

-- View: Station availability with details
CREATE VIEW v_station_availability AS
SELECT
    s.id AS station_id,
    s.code AS station_code,
    s.name AS station_name,
    s.address,
    s.landmark,
    s.latitude,
    s.longitude,
    s.city,
    s.operating_hours,
    s.contact_phone,
    si.available_batteries,
    si.charging_batteries,
    si.total_slots,
    si.last_updated,
    s.is_active
FROM stations s
LEFT JOIN station_inventory si ON s.id = si.station_id
WHERE s.is_active = true;

-- View: Recent swaps with details
CREATE VIEW v_recent_swaps AS
SELECT
    sw.id AS swap_id,
    sw.driver_id,
    d.phone_number,
    d.name AS driver_name,
    s.name AS station_name,
    s.code AS station_code,
    sw.old_battery_id,
    sw.new_battery_id,
    sw.swap_time,
    sw.is_subscription_swap,
    sw.charge_amount,
    sw.status,
    i.invoice_number,
    i.total_amount AS invoice_amount
FROM swaps sw
JOIN drivers d ON sw.driver_id = d.id
JOIN stations s ON sw.station_id = s.id
LEFT JOIN invoices i ON sw.id = i.swap_id
ORDER BY sw.swap_time DESC;