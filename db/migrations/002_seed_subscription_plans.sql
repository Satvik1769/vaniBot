-- Seed data for subscription plans
-- Two main plans as requested

-- Clear existing plans (if needed for fresh start)
-- DELETE FROM subscription_plans;

-- Insert the two main subscription plans
INSERT INTO subscription_plans (code, name, name_hi, price, validity_days, swaps_included, gst_percentage, extra_swap_price, swaps_per_day, description_en, description_hi, is_active)
VALUES
-- Plan 1: Monthly Plan
(
    'MONTHLY',
    'Monthly Plan',
    'Monthly Plan',
    999.00,
    30,
    60,  -- 2 swaps per day for 30 days
    18.00,
    35.00,
    2,
    'Best value plan! Get 60 swaps for 30 days. 2 swaps per day included. Extra swaps at Rs.35 each.',
    'Sabse achhi deal! 30 din ke liye 60 swaps milenge. Rozana 2 swaps included hain. Extra swap Rs.35 mein.'
    true
),
-- Plan 2: Weekly Plan
(
    'WEEKLY',
    'Weekly Plan',
    'Weekly Plan',
    299.00,
    7,
    14,  -- 2 swaps per day for 7 days
    18.00,
    35.00,
    2,
    'Perfect for short term! Get 14 swaps for 7 days. 2 swaps per day included. Extra swaps at Rs.35 each.',
    'Short term ke liye perfect! 7 din ke liye 14 swaps. Rozana 2 swaps included. Extra swap Rs.35 mein.'
    true
)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    name_hi = EXCLUDED.name_hi,
    price = EXCLUDED.price,
    validity_days = EXCLUDED.validity_days,
    swaps_included = EXCLUDED.swaps_included,
    gst_percentage = EXCLUDED.gst_percentage,
    extra_swap_price = EXCLUDED.extra_swap_price,
    swaps_per_day = EXCLUDED.swaps_per_day,
    description_en = EXCLUDED.description_en,
    description_hi = EXCLUDED.description_hi,
    is_active = EXCLUDED.is_active;

-- Optional: Add Daily and Yearly plans for flexibility
INSERT INTO subscription_plans (code, name, name_hi, price, validity_days, swaps_included, gst_percentage, extra_swap_price, swaps_per_day, description_en, description_hi, is_active)
VALUES
(
    'DAILY',
    'Daily Plan',
    'Daily Plan',
    49.00,
    1,
    2,
    18.00,
    35.00,
    2,
    'Quick daily plan. 2 swaps for today.',
    'Quick daily plan. Aaj ke liye 2 swaps.'
    true
),
(
    'YEARLY',
    'Yearly Plan',
    'Yearly Plan',
    9999.00,
    365,
    -1,  -- Unlimited
    18.00,
    0.00,
    -1,  -- Unlimited per day
    'Ultimate value! Unlimited swaps for 1 year.',
    'Sabse bada saving! 1 saal ke liye unlimited swaps.'
    true
)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    name_hi = EXCLUDED.name_hi,
    price = EXCLUDED.price,
    validity_days = EXCLUDED.validity_days,
    swaps_included = EXCLUDED.swaps_included,
    gst_percentage = EXCLUDED.gst_percentage,
    extra_swap_price = EXCLUDED.extra_swap_price,
    swaps_per_day = EXCLUDED.swaps_per_day,
    description_en = EXCLUDED.description_en,
    description_hi = EXCLUDED.description_hi,
    is_active = EXCLUDED.is_active;

-- Verify the plans
SELECT code, name, price, validity_days, swaps_included, gst_percentage FROM subscription_plans WHERE is_active = true ORDER BY price;