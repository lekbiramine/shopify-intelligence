-- Stores table for multi-store onboarding
CREATE TABLE IF NOT EXISTS stores (
    id BIGSERIAL PRIMARY KEY,
    shop_domain VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    access_token_expires_at TIMESTAMPTZ,
    scope TEXT,
    contact_email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_report_sent_at TIMESTAMPTZ,
    report_schedule_time VARCHAR(5),
    report_schedule_active BOOLEAN DEFAULT FALSE,
    report_timezone VARCHAR(64),
    connected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Backfill / migration for older DBs
ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS last_report_sent_at TIMESTAMPTZ;

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS report_schedule_time VARCHAR(5);

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS report_schedule_active BOOLEAN DEFAULT FALSE;

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS report_timezone VARCHAR(64);

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS refresh_token TEXT;

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS access_token_expires_at TIMESTAMPTZ;

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS referral_code_used VARCHAR(64);

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS referral_code_id BIGINT;

-- Affiliate/referral codes managed by internal team
CREATE TABLE IF NOT EXISTS referral_codes (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(64) UNIQUE NOT NULL,
    partner_name VARCHAR(255) NOT NULL,
    discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 20.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE stores
    DROP CONSTRAINT IF EXISTS stores_referral_code_id_fkey;

ALTER TABLE stores
    ADD CONSTRAINT stores_referral_code_id_fkey
    FOREIGN KEY (referral_code_id) REFERENCES referral_codes(id) ON DELETE SET NULL;

-- Attribution history linking installs to referral codes
CREATE TABLE IF NOT EXISTS store_referrals (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    referral_code_id BIGINT NOT NULL REFERENCES referral_codes(id) ON DELETE RESTRICT,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(32) NOT NULL DEFAULT 'oauth_install',
    UNIQUE (store_id)
);

-- One-time OAuth state tracking to prevent callback replay
CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash CHAR(64) PRIMARY KEY,
    shop_domain VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    vendor VARCHAR(255),
    product_type VARCHAR(255),
    status VARCHAR(50),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE products
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE products
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE products
    DROP CONSTRAINT IF EXISTS products_pkey;

ALTER TABLE products
    ADD PRIMARY KEY (store_id, id);

-- Variants table
CREATE TABLE IF NOT EXISTS variants (
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    product_id BIGINT,
    title VARCHAR(255),
    sku VARCHAR(255),
    price NUMERIC(10, 2),
    inventory_quantity INTEGER,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE variants
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE variants
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE variants
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE variants
    DROP CONSTRAINT IF EXISTS variants_pkey;

ALTER TABLE variants
    ADD PRIMARY KEY (store_id, id);

ALTER TABLE variants
    ADD CONSTRAINT variants_product_fk
    FOREIGN KEY (store_id, product_id) REFERENCES products(store_id, id) ON DELETE CASCADE;

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    email VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    orders_count INTEGER DEFAULT 0,
    total_spent NUMERIC(10, 2) DEFAULT 0.00,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE customers
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE customers
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE customers
    DROP CONSTRAINT IF EXISTS customers_pkey;

ALTER TABLE customers
    ADD PRIMARY KEY (store_id, id);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    customer_id BIGINT,
    email VARCHAR(255),
    total_price NUMERIC(10, 2),
    subtotal_price NUMERIC(10, 2),
    total_discounts NUMERIC(10, 2),
    financial_status VARCHAR(50),
    fulfillment_status VARCHAR(50),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE orders
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE orders
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_pkey;

ALTER TABLE orders
    ADD PRIMARY KEY (store_id, id);

ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_customer_id_fkey;

ALTER TABLE orders
    ADD CONSTRAINT orders_customer_fk
    FOREIGN KEY (store_id, customer_id) REFERENCES customers(store_id, id) ON DELETE SET NULL;

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    order_id BIGINT,
    product_id BIGINT,
    variant_id BIGINT,
    title VARCHAR(255),
    quantity INTEGER,
    price NUMERIC(10, 2),
    total_discount NUMERIC(10, 2),
    vendor VARCHAR(255)
);

ALTER TABLE order_items
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE order_items
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE order_items
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_pkey;

ALTER TABLE order_items
    ADD PRIMARY KEY (store_id, id);

ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_order_id_fkey;

ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_product_id_fkey;

ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_variant_id_fkey;

ALTER TABLE order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (store_id, order_id) REFERENCES orders(store_id, id) ON DELETE CASCADE;

ALTER TABLE order_items
    ADD CONSTRAINT order_items_product_fk
    FOREIGN KEY (store_id, product_id) REFERENCES products(store_id, id) ON DELETE SET NULL;

ALTER TABLE order_items
    ADD CONSTRAINT order_items_variant_fk
    FOREIGN KEY (store_id, variant_id) REFERENCES variants(store_id, id) ON DELETE SET NULL;

-- Inventory table
CREATE TABLE IF NOT EXISTS inventory (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT REFERENCES stores(id) ON DELETE CASCADE,
    variant_id BIGINT,
    inventory_item_id BIGINT,
    location_id BIGINT,
    available INTEGER,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (store_id, variant_id, location_id)
);

ALTER TABLE inventory
    ADD COLUMN IF NOT EXISTS store_id BIGINT;

UPDATE inventory
SET store_id = COALESCE(store_id, (SELECT id FROM stores ORDER BY id LIMIT 1))
WHERE store_id IS NULL;

ALTER TABLE inventory
    ALTER COLUMN store_id SET NOT NULL;

ALTER TABLE inventory
    DROP CONSTRAINT IF EXISTS inventory_variant_id_fkey;

ALTER TABLE inventory
    ADD CONSTRAINT inventory_variant_fk
    FOREIGN KEY (store_id, variant_id) REFERENCES variants(store_id, id) ON DELETE CASCADE;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_variants_product_id ON variants(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_variant_id ON inventory(variant_id);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email); 

CREATE INDEX IF NOT EXISTS idx_products_store_id ON products(store_id);
CREATE INDEX IF NOT EXISTS idx_variants_store_id ON variants(store_id);
CREATE INDEX IF NOT EXISTS idx_customers_store_id ON customers(store_id);
CREATE INDEX IF NOT EXISTS idx_orders_store_id ON orders(store_id);
CREATE INDEX IF NOT EXISTS idx_order_items_store_id ON order_items(store_id);
CREATE INDEX IF NOT EXISTS idx_inventory_store_id ON inventory(store_id);
CREATE INDEX IF NOT EXISTS idx_referral_codes_active ON referral_codes(is_active);
CREATE INDEX IF NOT EXISTS idx_referral_codes_partner ON referral_codes(partner_name);
CREATE INDEX IF NOT EXISTS idx_store_referrals_referral_code_id ON store_referrals(referral_code_id);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expires_at ON oauth_states(expires_at);

-- Abandoned carts (optional; used by abandoned_checkout_spike insight)
CREATE TABLE IF NOT EXISTS abandoned_checkouts (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_abandoned_checkouts_store_created
    ON abandoned_checkouts (store_id, created_at DESC);

-- Job monitoring table (basic operational visibility)
CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    shop_domain VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
    report_path TEXT,
    recipient_email VARCHAR(255),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_store_id_started_at ON job_runs(store_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_status_started_at ON job_runs(status, started_at DESC);

ALTER TABLE job_runs
    ADD COLUMN IF NOT EXISTS report_path TEXT;
ALTER TABLE job_runs
    ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255);

-- Report delivery tracking per store
CREATE TABLE IF NOT EXISTS reports (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    report_path TEXT NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_store_id_created_at ON reports(store_id, created_at DESC);

-- Action-driven task tracking
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    type VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    priority VARCHAR(16) NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_status_change_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reminded_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expected_impact NUMERIC(14, 2) NOT NULL DEFAULT 0,
    actual_impact NUMERIC(14, 2),
    baseline_metric NUMERIC(14, 4),
    fingerprint CHAR(64) NOT NULL,
    primary_entity_id VARCHAR(128),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (status IN ('pending', 'in_progress', 'completed', 'ignored')),
    CHECK (priority IN ('high', 'medium', 'low')),
    UNIQUE (store_id, fingerprint)
);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS store_id BIGINT;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS type VARCHAR(64);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'pending';
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS priority VARCHAR(16) DEFAULT 'medium';
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS last_status_change_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS last_reminded_at TIMESTAMPTZ;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS expected_impact NUMERIC(14, 2) DEFAULT 0;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS actual_impact NUMERIC(14, 2);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS baseline_metric NUMERIC(14, 4);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS fingerprint CHAR(64);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS primary_entity_id VARCHAR(128);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS metadata_json JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_tasks_store_status_priority ON tasks(store_id, status, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_last_reminded_at ON tasks(last_reminded_at);