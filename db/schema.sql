-- Stores table for multi-store onboarding
CREATE TABLE IF NOT EXISTS stores (
    id BIGSERIAL PRIMARY KEY,
    shop_domain VARCHAR(255) UNIQUE NOT NULL,
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

-- Drop legacy FKs that depended on products(id) PK, before replacing PK
ALTER TABLE variants
    DROP CONSTRAINT IF EXISTS variants_product_id_fkey;

ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_product_id_fkey;

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

-- Drop legacy FKs that depended on variants(id) PK, before replacing PK
ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_variant_id_fkey;

ALTER TABLE inventory
    DROP CONSTRAINT IF EXISTS inventory_variant_id_fkey;

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

-- Drop legacy FK that depended on customers(id) PK, before replacing PK
ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_customer_id_fkey;

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

-- Drop legacy FK that depended on orders(id) PK, before replacing PK
ALTER TABLE order_items
    DROP CONSTRAINT IF EXISTS order_items_order_id_fkey;

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

-- Job monitoring table (basic operational visibility)
CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    shop_domain VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_store_id_started_at ON job_runs(store_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_status_started_at ON job_runs(status, started_at DESC);