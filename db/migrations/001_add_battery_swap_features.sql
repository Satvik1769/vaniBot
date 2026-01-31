-- Migration: Add Battery Swap Features
-- Date: 2025-01-31
-- Description: Adds new tables and columns for swap history, invoices, subscriptions, payments, and call recording

-- ============================================
-- MODIFY EXISTING TABLES
-- ============================================

-- Add vehicle_number to drivers table
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle_number VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_drivers_vehicle ON drivers(vehicle_number);

-- Add is_dsk and google_map_url to stations table
ALTER TABLE stations ADD COLUMN IF NOT EXISTS is_dsk BOOLEAN DEFAULT false;
ALTER TABLE stations ADD COLUMN IF NOT EXISTS google_map_url TEXT;

-- Add battery tracking fields to driver_subscriptions
ALTER TABLE driver_subscriptions ADD COLUMN IF NOT EXISTS battery_id VARCHAR(50);
ALTER TABLE driver_subscriptions ADD COLUMN IF NOT EXISTS is_misplaced BOOLEAN DEFAULT false;
ALTER TABLE driver_subscriptions ADD COLUMN IF NOT EXISTS battery_returned BOOLEAN DEFAULT false;
ALTER TABLE driver_subscriptions ADD COLUMN IF NOT EXISTS battery_returned_date TIMESTAMP WITH TIME ZONE;

-- Add charge dates to swaps table
ALTER TABLE swaps ADD COLUMN IF NOT EXISTS charge_start_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE swaps ADD COLUMN IF NOT EXISTS charge_end_date TIMESTAMP WITH TIME ZONE;

-- ============================================
-- NEW TABLES
-- ============================================

-- Battery details table
CREATE TABLE IF NOT EXISTS battery_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battery_name VARCHAR(50) UNIQUE NOT NULL,
    battery_percentage INT DEFAULT 0 CHECK (battery_percentage >= 0 AND battery_percentage <= 100),
    current_user_id UUID REFERENCES drivers(id),
    status VARCHAR(20) DEFAULT 'available', -- available, in_use, charging, maintenance, retired
    station_id UUID REFERENCES stations(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_battery_name ON battery_details(battery_name);
CREATE INDEX IF NOT EXISTS idx_battery_user ON battery_details(current_user_id);
CREATE INDEX IF NOT EXISTS idx_battery_station ON battery_details(station_id);
CREATE INDEX IF NOT EXISTS idx_battery_status ON battery_details(status);

-- Transaction history (payments)
CREATE TABLE IF NOT EXISTS transaction_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES drivers(id),
    plan_id UUID REFERENCES subscription_plans(id),
    order_id VARCHAR(100) UNIQUE,
    payment_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'pending', -- pending, completed, failed, refunded
    invoice_url TEXT,
    amount DECIMAL(10, 2) NOT NULL,
    tax_amount DECIMAL(10, 2) DEFAULT 0,
    total_amount DECIMAL(10, 2),
    payment_method VARCHAR(50), -- upi, card, wallet, netbanking
    payment_gateway VARCHAR(50) DEFAULT 'juspay',
    gateway_transaction_id VARCHAR(100),
    gateway_response JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_txn_user ON transaction_history(user_id);
CREATE INDEX IF NOT EXISTS idx_txn_order ON transaction_history(order_id);
CREATE INDEX IF NOT EXISTS idx_txn_status ON transaction_history(status);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transaction_history(payment_date DESC);

-- Call recording table
CREATE TABLE IF NOT EXISTS call_recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES drivers(id),
    phone_number VARCHAR(15) NOT NULL,
    issue_type VARCHAR(50), -- swap_history, invoice, station_finder, subscription, leave, dsk, other
    recording_url TEXT,
    call_sid VARCHAR(100), -- Twilio/Exotel call ID
    duration_seconds INT,
    direction VARCHAR(10) DEFAULT 'inbound', -- inbound, outbound
    status VARCHAR(20) DEFAULT 'completed', -- ringing, in_progress, completed, failed, no_answer
    caller_latitude DECIMAL(10, 8),
    caller_longitude DECIMAL(11, 8),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_user ON call_recordings(user_id);
CREATE INDEX IF NOT EXISTS idx_call_phone ON call_recordings(phone_number);
CREATE INDEX IF NOT EXISTS idx_call_timestamp ON call_recordings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_call_issue ON call_recordings(issue_type);

-- Subscription plans - add additional fields if not exists
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS gst_percentage DECIMAL(5, 2) DEFAULT 18.00;
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS swaps_per_day INT DEFAULT -1; -- -1 for unlimited

-- Leave balance tracking (4 leaves per month)
CREATE TABLE IF NOT EXISTS leave_balance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    month_year VARCHAR(7) NOT NULL, -- Format: YYYY-MM
    total_leaves INT DEFAULT 4,
    used_leaves INT DEFAULT 0,
    remaining_leaves INT GENERATED ALWAYS AS (total_leaves - used_leaves) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(driver_id, month_year)
);

CREATE INDEX IF NOT EXISTS idx_leave_balance_driver ON leave_balance(driver_id);
CREATE INDEX IF NOT EXISTS idx_leave_balance_month ON leave_balance(month_year);

-- ============================================
-- PENALTY TRACKING
-- ============================================

-- Penalty records for unreturned batteries
CREATE TABLE IF NOT EXISTS penalty_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    subscription_id UUID REFERENCES driver_subscriptions(id),
    reason VARCHAR(50) NOT NULL, -- battery_not_returned, late_return, damage
    days_overdue INT DEFAULT 0,
    daily_rate DECIMAL(10, 2) DEFAULT 80.00, -- Rs 80 per day
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- pending, paid, waived
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_penalty_driver ON penalty_records(driver_id);
CREATE INDEX IF NOT EXISTS idx_penalty_status ON penalty_records(status);

-- ============================================
-- SMS LOG TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS sms_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES drivers(id),
    phone_number VARCHAR(15) NOT NULL,
    message_type VARCHAR(50) NOT NULL, -- swap_history, payment_link, invoice, subscription_reminder
    message_content TEXT,
    twilio_sid VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending', -- pending, sent, delivered, failed
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    delivered_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sms_user ON sms_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_sms_phone ON sms_logs(phone_number);
CREATE INDEX IF NOT EXISTS idx_sms_status ON sms_logs(status);

-- ============================================
-- UPDATE TRIGGERS
-- ============================================

CREATE TRIGGER IF NOT EXISTS update_battery_updated_at
    BEFORE UPDATE ON battery_details
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER IF NOT EXISTS update_leave_balance_updated_at
    BEFORE UPDATE ON leave_balance
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- UPDATED VIEWS
-- ============================================

-- Drop and recreate views to include new fields
DROP VIEW IF EXISTS v_active_subscriptions CASCADE;

CREATE VIEW v_active_subscriptions AS
SELECT
    ds.id AS subscription_id,
    d.id AS driver_id,
    d.phone_number,
    d.name AS driver_name,
    d.vehicle_number,
    d.preferred_language,
    sp.id AS plan_id,
    sp.code AS plan_code,
    sp.name AS plan_name,
    sp.name_hi AS plan_name_hi,
    sp.price AS plan_price,
    sp.gst_percentage,
    sp.swaps_included,
    ds.swaps_used,
    CASE
        WHEN sp.swaps_included = -1 THEN -1
        ELSE sp.swaps_included - ds.swaps_used
    END AS swaps_remaining,
    ds.start_date,
    ds.end_date,
    ds.end_date - CURRENT_DATE AS days_remaining,
    ds.battery_id,
    ds.is_misplaced,
    ds.battery_returned,
    ds.battery_returned_date,
    ds.auto_renew,
    ds.status,
    -- Check if penalty applies (battery not returned 4+ days after end_date)
    CASE
        WHEN ds.battery_returned = false
             AND ds.end_date < CURRENT_DATE - INTERVAL '4 days'
        THEN true
        ELSE false
    END AS has_penalty,
    CASE
        WHEN ds.battery_returned = false
             AND ds.end_date < CURRENT_DATE - INTERVAL '4 days'
        THEN (CURRENT_DATE - ds.end_date - 4) * 80
        ELSE 0
    END AS penalty_amount
FROM driver_subscriptions ds
JOIN drivers d ON ds.driver_id = d.id
JOIN subscription_plans sp ON ds.plan_id = sp.id
WHERE ds.status = 'active' AND ds.end_date >= CURRENT_DATE;

-- View: Station availability with DSK flag
DROP VIEW IF EXISTS v_station_availability CASCADE;

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
    s.is_dsk,
    s.google_map_url,
    si.available_batteries,
    si.charging_batteries,
    si.total_slots,
    si.last_updated,
    s.is_active
FROM stations s
LEFT JOIN station_inventory si ON s.id = si.station_id
WHERE s.is_active = true;

-- View: Swap history with battery details
CREATE OR REPLACE VIEW v_swap_history AS
SELECT
    sw.id AS swap_id,
    sw.driver_id,
    d.phone_number,
    d.name AS driver_name,
    s.id AS station_id,
    s.name AS station_name,
    s.code AS station_code,
    s.address AS station_address,
    sw.old_battery_id AS prev_battery_id,
    sw.new_battery_id AS battery_id,
    sw.old_battery_charge_level,
    sw.new_battery_charge_level,
    sw.swap_time AS created_at,
    sw.charge_start_date,
    sw.charge_end_date,
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

-- View: Driver leave summary
CREATE OR REPLACE VIEW v_driver_leave_summary AS
SELECT
    d.id AS driver_id,
    d.phone_number,
    d.name AS driver_name,
    lb.month_year,
    lb.total_leaves,
    lb.used_leaves,
    lb.remaining_leaves,
    (SELECT COUNT(*) FROM driver_leaves dl
     WHERE dl.driver_id = d.id AND dl.status = 'pending') AS pending_requests,
    (SELECT COUNT(*) FROM driver_leaves dl
     WHERE dl.driver_id = d.id AND dl.status = 'approved'
     AND dl.end_date >= CURRENT_DATE) AS upcoming_leaves
FROM drivers d
LEFT JOIN leave_balance lb ON d.id = lb.driver_id
    AND lb.month_year = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
WHERE d.is_active = true;

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to get or create leave balance for current month
CREATE OR REPLACE FUNCTION get_or_create_leave_balance(p_driver_id UUID)
RETURNS TABLE(
    id UUID,
    driver_id UUID,
    month_year VARCHAR,
    total_leaves INT,
    used_leaves INT,
    remaining_leaves INT
) AS $$
DECLARE
    current_month VARCHAR(7);
    balance_record RECORD;
BEGIN
    current_month := TO_CHAR(CURRENT_DATE, 'YYYY-MM');

    -- Try to get existing balance
    SELECT * INTO balance_record
    FROM leave_balance lb
    WHERE lb.driver_id = p_driver_id AND lb.month_year = current_month;

    -- Create if not exists
    IF NOT FOUND THEN
        INSERT INTO leave_balance (driver_id, month_year, total_leaves, used_leaves)
        VALUES (p_driver_id, current_month, 4, 0)
        RETURNING * INTO balance_record;
    END IF;

    RETURN QUERY SELECT
        balance_record.id,
        balance_record.driver_id,
        balance_record.month_year,
        balance_record.total_leaves,
        balance_record.used_leaves,
        balance_record.total_leaves - balance_record.used_leaves;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate penalty for unreturned battery
CREATE OR REPLACE FUNCTION calculate_battery_penalty(p_subscription_id UUID)
RETURNS TABLE(
    has_penalty BOOLEAN,
    days_overdue INT,
    daily_rate DECIMAL,
    total_penalty DECIMAL
) AS $$
DECLARE
    sub_record RECORD;
    overdue_days INT;
BEGIN
    SELECT * INTO sub_record
    FROM driver_subscriptions
    WHERE id = p_subscription_id;

    IF NOT FOUND OR sub_record.battery_returned = true THEN
        RETURN QUERY SELECT false, 0, 80.00::DECIMAL, 0.00::DECIMAL;
        RETURN;
    END IF;

    -- Calculate days overdue (penalty starts after 4 days past end_date)
    overdue_days := GREATEST(0, (CURRENT_DATE - sub_record.end_date) - 4);

    IF overdue_days > 0 THEN
        RETURN QUERY SELECT true, overdue_days, 80.00::DECIMAL, (overdue_days * 80.00)::DECIMAL;
    ELSE
        RETURN QUERY SELECT false, 0, 80.00::DECIMAL, 0.00::DECIMAL;
    END IF;
END;
$$ LANGUAGE plpgsql;