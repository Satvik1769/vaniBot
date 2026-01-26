-- Battery Smart Voicebot - Seed Data for Testing
-- Realistic data for Delhi NCR region

-- ============================================
-- SUBSCRIPTION PLANS
-- ============================================
INSERT INTO subscription_plans (code, name, name_hi, price, validity_days, swaps_included, extra_swap_price, description_en, description_hi) VALUES
('DAILY', 'Daily Plan', 'डेली प्लान', 49.00, 1, 4, 35.00,
 '4 swaps per day. Extra swaps at Rs.35 each.',
 'रोज़ाना 4 स्वैप। अतिरिक्त स्वैप ₹35 प्रति स्वैप।'),
('WEEKLY', 'Weekly Unlimited', 'वीकली अनलिमिटेड', 299.00, 7, -1, 0.00,
 'Unlimited swaps for 7 days.',
 '7 दिन के लिए अनलिमिटेड स्वैप।'),
('MONTHLY', 'Monthly Unlimited', 'मंथली अनलिमिटेड', 999.00, 30, -1, 0.00,
 'Unlimited swaps for 30 days. Best value!',
 '30 दिन के लिए अनलिमिटेड स्वैप। सबसे अच्छी वैल्यू!'),
('YEARLY', 'Annual Plan', 'वार्षिक प्लान', 9999.00, 365, -1, 0.00,
 'Unlimited swaps for entire year. Maximum savings!',
 'पूरे साल के लिए अनलिमिटेड स्वैप। अधिकतम बचत!');

-- ============================================
-- STATIONS (Delhi NCR)
-- ============================================
INSERT INTO stations (code, name, address, landmark, latitude, longitude, city, pincode, operating_hours, contact_phone) VALUES
-- Delhi Stations
('DLH-LXN-001', 'Laxmi Nagar Station', 'Shop 23, Main Market, Laxmi Nagar', 'Near Laxmi Nagar Metro Station', 28.6304, 77.2773, 'Delhi', '110092', '06:00-22:00', '9876543210'),
('DLH-MYV-001', 'Mayur Vihar Station', 'Plot 45, Phase 1, Mayur Vihar', 'Near Mayur Vihar Metro Station', 28.6088, 77.2936, 'Delhi', '110091', '06:00-22:00', '9876543211'),
('DLH-DWR-001', 'Dwarka Mor Station', 'Sector 6, Dwarka Mor', 'Near Dwarka Mor Metro', 28.6194, 77.0311, 'Delhi', '110059', '06:00-22:00', '9876543212'),
('DLH-DWR-002', 'Dwarka Sector 14 Market', 'Market Complex, Sector 14', 'Near Dwarka Sector 14 Metro', 28.5921, 77.0460, 'Delhi', '110078', '06:00-22:00', '9876543213'),
('DLH-PLM-001', 'Palam Station', 'Main Road, Palam Village', 'Near Palam Flyover', 28.5810, 77.0870, 'Delhi', '110045', '06:00-23:00', '9876543214'),
('DLH-RKP-001', 'Rohini Sector 3 Station', 'Main Market, Sector 3', 'Near Rohini West Metro', 28.7041, 77.1025, 'Delhi', '110085', '06:00-22:00', '9876543215'),
('DLH-OKH-001', 'Okhla Industrial Station', 'Phase 2, Okhla Industrial Area', 'Near Govindpuri Metro', 28.5321, 77.2711, 'Delhi', '110020', '24x7', '9876543216'),
('DLH-SNP-001', 'Sarita Vihar Station', 'Main Road, Sarita Vihar', 'Near Apollo Hospital', 28.5282, 77.2893, 'Delhi', '110076', '06:00-22:00', '9876543217'),

-- Noida Stations
('NOI-S62-001', 'Noida Sector 62 Station', 'Block A, Sector 62', 'Near Sector 62 Metro', 28.6247, 77.3634, 'Noida', '201301', '06:00-22:00', '9876543218'),
('NOI-S18-001', 'Noida Sector 18 Station', 'Atta Market, Sector 18', 'Near Great India Place Mall', 28.5706, 77.3218, 'Noida', '201301', '06:00-23:00', '9876543219'),

-- Gurgaon Stations
('GGN-S29-001', 'Gurgaon Sector 29 Station', 'Near Leisure Valley Park', 'Sector 29 Market', 28.4595, 77.0266, 'Gurgaon', '122001', '06:00-22:00', '9876543220'),
('GGN-MGL-001', 'MG Road Station', 'Near IFFCO Chowk', 'Opposite MGF Mall', 28.4814, 77.0810, 'Gurgaon', '122002', '24x7', '9876543221');

-- Station Inventory
INSERT INTO station_inventory (station_id, available_batteries, charging_batteries, total_slots)
SELECT id,
    (RANDOM() * 15 + 5)::INT,  -- 5-20 available
    (RANDOM() * 5 + 2)::INT,   -- 2-7 charging
    20
FROM stations;

-- ============================================
-- DSK LOCATIONS
-- ============================================
INSERT INTO dsk_locations (code, name, address, landmark, latitude, longitude, city, pincode, phone, operating_hours, services) VALUES
('DSK-DLH-001', 'Battery Smart Service Center - Laxmi Nagar', 'B-12, Vikas Marg, Laxmi Nagar', 'Near Nirman Vihar Metro', 28.6334, 77.2753, 'Delhi', '110092', '1800-123-4567', '09:00-18:00', ARRAY['activation', 'repair', 'support', 'battery_replacement']),
('DSK-DLH-002', 'Battery Smart Hub - Dwarka', 'Sector 11, Dwarka', 'Near Dwarka Sector 11 Metro', 28.5931, 77.0301, 'Delhi', '110075', '1800-123-4568', '09:00-18:00', ARRAY['activation', 'support', 'repair']),
('DSK-DLH-003', 'Battery Smart Point - Rohini', 'Sector 7, Rohini', 'Near Rohini East Metro', 28.7125, 77.1156, 'Delhi', '110085', '1800-123-4569', '09:00-18:00', ARRAY['activation', 'support']),
('DSK-NOI-001', 'Battery Smart Service - Noida', 'Sector 63, Noida', 'Near Electronic City Metro', 28.6265, 77.3791, 'Noida', '201301', '1800-123-4570', '09:00-18:00', ARRAY['activation', 'repair', 'support', 'battery_replacement']),
('DSK-GGN-001', 'Battery Smart Hub - Gurgaon', 'Udyog Vihar Phase 4', 'Near IFFCO Chowk', 28.4952, 77.0892, 'Gurgaon', '122015', '1800-123-4571', '09:00-18:00', ARRAY['activation', 'repair', 'support', 'battery_replacement']);

-- ============================================
-- TEST DRIVERS
-- ============================================
INSERT INTO drivers (phone_number, name, email, preferred_language, city) VALUES
('9811234567', 'Ramesh Kumar', 'ramesh.kumar@email.com', 'hi-en', 'Delhi'),
('9822345678', 'Suresh Singh', 'suresh.singh@email.com', 'hi', 'Delhi'),
('9833456789', 'Amit Sharma', 'amit.sharma@email.com', 'en', 'Noida'),
('9844567890', 'Priya Verma', 'priya.verma@email.com', 'hi-en', 'Gurgaon'),
('9855678901', 'Deepak Yadav', 'deepak.yadav@email.com', 'hi', 'Delhi'),
('9866789012', 'Anjali Gupta', 'anjali.gupta@email.com', 'hi-en', 'Delhi'),
('9877890123', 'Rajesh Tiwari', 'rajesh.tiwari@email.com', 'hi', 'Noida'),
('9888901234', 'Pooja Pandey', 'pooja.pandey@email.com', 'hi-en', 'Gurgaon');

-- ============================================
-- DRIVER SUBSCRIPTIONS
-- ============================================

-- Ramesh Kumar - Monthly plan expiring in 2 days
INSERT INTO driver_subscriptions (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
SELECT d.id, p.id, CURRENT_DATE - 28, CURRENT_DATE + 2, 'active', 45, true
FROM drivers d, subscription_plans p
WHERE d.phone_number = '9811234567' AND p.code = 'MONTHLY';

-- Suresh Singh - Daily plan, used 3 of 4 swaps today
INSERT INTO driver_subscriptions (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
SELECT d.id, p.id, CURRENT_DATE, CURRENT_DATE, 'active', 3, true
FROM drivers d, subscription_plans p
WHERE d.phone_number = '9822345678' AND p.code = 'DAILY';

-- Amit Sharma - Weekly plan mid-way
INSERT INTO driver_subscriptions (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
SELECT d.id, p.id, CURRENT_DATE - 3, CURRENT_DATE + 4, 'active', 12, false
FROM drivers d, subscription_plans p
WHERE d.phone_number = '9833456789' AND p.code = 'WEEKLY';

-- Priya Verma - Expired subscription
INSERT INTO driver_subscriptions (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
SELECT d.id, p.id, CURRENT_DATE - 35, CURRENT_DATE - 5, 'expired', 30, false
FROM drivers d, subscription_plans p
WHERE d.phone_number = '9844567890' AND p.code = 'MONTHLY';

-- Deepak Yadav - Annual plan
INSERT INTO driver_subscriptions (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
SELECT d.id, p.id, CURRENT_DATE - 100, CURRENT_DATE + 265, 'active', 450, true
FROM drivers d, subscription_plans p
WHERE d.phone_number = '9855678901' AND p.code = 'YEARLY';

-- ============================================
-- SWAPS (Last 7 days for test drivers)
-- ============================================

-- Helper function to insert swaps
DO $$
DECLARE
    driver_rec RECORD;
    station_rec RECORD;
    swap_count INT;
    i INT;
    swap_time TIMESTAMP;
    charge DECIMAL;
    sub_id UUID;
BEGIN
    -- Ramesh Kumar - Multiple swaps
    SELECT id INTO sub_id FROM driver_subscriptions ds
    JOIN drivers d ON ds.driver_id = d.id
    WHERE d.phone_number = '9811234567' AND ds.status = 'active';

    FOR i IN 1..8 LOOP
        SELECT id INTO station_rec FROM stations ORDER BY RANDOM() LIMIT 1;
        swap_time := NOW() - (RANDOM() * INTERVAL '7 days');

        INSERT INTO swaps (driver_id, station_id, subscription_id, old_battery_id, new_battery_id,
                          old_battery_charge_level, new_battery_charge_level, swap_time,
                          is_subscription_swap, charge_amount)
        SELECT d.id, station_rec.id, sub_id,
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               (RANDOM() * 20)::INT,  -- Low charge
               (RANDOM() * 20 + 80)::INT,  -- High charge
               swap_time,
               true, 0
        FROM drivers d WHERE d.phone_number = '9811234567';
    END LOOP;

    -- Suresh Singh - 5 swaps today (exceeding daily limit)
    SELECT id INTO sub_id FROM driver_subscriptions ds
    JOIN drivers d ON ds.driver_id = d.id
    WHERE d.phone_number = '9822345678' AND ds.status = 'active';

    FOR i IN 1..5 LOOP
        SELECT id INTO station_rec FROM stations WHERE city = 'Delhi' ORDER BY RANDOM() LIMIT 1;
        swap_time := CURRENT_DATE + (i * INTERVAL '2 hours');

        -- First 4 are free (subscription), 5th is charged
        IF i <= 4 THEN
            charge := 0;
        ELSE
            charge := 35;
        END IF;

        INSERT INTO swaps (driver_id, station_id, subscription_id, old_battery_id, new_battery_id,
                          old_battery_charge_level, new_battery_charge_level, swap_time,
                          is_subscription_swap, charge_amount)
        SELECT d.id, station_rec.id, sub_id,
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               (RANDOM() * 15)::INT,
               (RANDOM() * 15 + 85)::INT,
               swap_time,
               i <= 4, charge
        FROM drivers d WHERE d.phone_number = '9822345678';
    END LOOP;

    -- Amit Sharma - Noida swaps
    SELECT id INTO sub_id FROM driver_subscriptions ds
    JOIN drivers d ON ds.driver_id = d.id
    WHERE d.phone_number = '9833456789' AND ds.status = 'active';

    FOR i IN 1..12 LOOP
        SELECT id INTO station_rec FROM stations WHERE city = 'Noida' ORDER BY RANDOM() LIMIT 1;
        swap_time := NOW() - (RANDOM() * INTERVAL '3 days');

        INSERT INTO swaps (driver_id, station_id, subscription_id, old_battery_id, new_battery_id,
                          old_battery_charge_level, new_battery_charge_level, swap_time,
                          is_subscription_swap, charge_amount)
        SELECT d.id, station_rec.id, sub_id,
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               'BAT-' || LPAD((RANDOM() * 99999)::INT::TEXT, 5, '0'),
               (RANDOM() * 20)::INT,
               (RANDOM() * 15 + 85)::INT,
               swap_time,
               true, 0
        FROM drivers d WHERE d.phone_number = '9833456789';
    END LOOP;
END $$;

-- ============================================
-- INVOICES
-- ============================================

-- Generate invoices for charged swaps
INSERT INTO invoices (invoice_number, driver_id, swap_id, invoice_type, amount, tax_amount, total_amount, description, description_hi, payment_status)
SELECT
    generate_invoice_number(),
    s.driver_id,
    s.id,
    'extra_swap',
    s.charge_amount,
    ROUND(s.charge_amount * 0.18, 2),
    ROUND(s.charge_amount * 1.18, 2),
    'Extra swap charge - Daily plan limit exceeded',
    'अतिरिक्त स्वैप चार्ज - डेली प्लान लिमिट से ज़्यादा',
    'paid'
FROM swaps s
WHERE s.charge_amount > 0;

-- Generate subscription invoices
INSERT INTO invoices (invoice_number, driver_id, subscription_id, invoice_type, amount, tax_amount, total_amount, description, description_hi, payment_status)
SELECT
    generate_invoice_number(),
    ds.driver_id,
    ds.id,
    'subscription',
    sp.price,
    ROUND(sp.price * 0.18, 2),
    ROUND(sp.price * 1.18, 2),
    'Subscription: ' || sp.name,
    'सब्सक्रिप्शन: ' || sp.name_hi,
    'paid'
FROM driver_subscriptions ds
JOIN subscription_plans sp ON ds.plan_id = sp.id
WHERE ds.status = 'active';

-- ============================================
-- DRIVER LEAVES (Sample)
-- ============================================
INSERT INTO driver_leaves (driver_id, start_date, end_date, reason, status)
SELECT d.id, CURRENT_DATE + 5, CURRENT_DATE + 7, 'Family function', 'approved'
FROM drivers d WHERE d.phone_number = '9811234567';

INSERT INTO driver_leaves (driver_id, start_date, end_date, reason, status)
SELECT d.id, CURRENT_DATE + 2, CURRENT_DATE + 2, 'Personal work', 'pending'
FROM drivers d WHERE d.phone_number = '9822345678';

-- ============================================
-- SAMPLE CONVERSATION LOG
-- ============================================
INSERT INTO conversation_logs (session_id, driver_id, phone_number, channel, language_detected,
                               started_at, ended_at, duration_seconds, turns_count,
                               handoff_occurred, resolution_status, intents_detected, summary)
SELECT
    'sess-' || gen_random_uuid()::TEXT,
    d.id,
    d.phone_number,
    'voice',
    'hi-en',
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '2 hours' + INTERVAL '3 minutes',
    180,
    6,
    false,
    'resolved',
    ARRAY['greeting', 'check_swap_history', 'explain_invoice', 'goodbye'],
    'Driver inquired about today''s swap history and asked for clarification on extra swap charge. Issue resolved - explained daily plan limit.'
FROM drivers d WHERE d.phone_number = '9822345678';

-- Verify data
SELECT 'Subscription Plans' as table_name, COUNT(*) as count FROM subscription_plans
UNION ALL
SELECT 'Stations', COUNT(*) FROM stations
UNION ALL
SELECT 'Station Inventory', COUNT(*) FROM station_inventory
UNION ALL
SELECT 'DSK Locations', COUNT(*) FROM dsk_locations
UNION ALL
SELECT 'Drivers', COUNT(*) FROM drivers
UNION ALL
SELECT 'Driver Subscriptions', COUNT(*) FROM driver_subscriptions
UNION ALL
SELECT 'Swaps', COUNT(*) FROM swaps
UNION ALL
SELECT 'Invoices', COUNT(*) FROM invoices
UNION ALL
SELECT 'Driver Leaves', COUNT(*) FROM driver_leaves
UNION ALL
SELECT 'Conversation Logs', COUNT(*) FROM conversation_logs;