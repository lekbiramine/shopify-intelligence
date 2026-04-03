-- Products table
CREATE TABLE IF NOT EXISTS products (
    id BIGINT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    vendor VARCHAR(255),
    product_type VARCHAR(255),
    status VARCHAR(50),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Variants table
CREATE TABLE IF NOT EXISTS variants (
    id BIGINT PRIMARY KEY,
    product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
    title VARCHAR(255),
    sku VARCHAR(255),
    price NUMERIC(10, 2),
    inventory_quantity INTEGER,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    orders_count INTEGER DEFAULT 0,
    total_spent NUMERIC(10, 2) DEFAULT 0.00,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
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

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(id) ON DELETE SET NULL,
    variant_id BIGINT REFERENCES variants(id) ON DELETE SET NULL,
    title VARCHAR(255),
    quantity INTEGER,
    price NUMERIC(10, 2),
    total_discount NUMERIC(10, 2),
    vendor VARCHAR(255)
);

-- Inventory table
CREATE TABLE IF NOT EXISTS inventory (
    id BIGSERIAL PRIMARY KEY,
    variant_id BIGINT REFERENCES variants(id) ON DELETE CASCADE,
    inventory_item_id BIGINT,
    location_id BIGINT,
    available INTEGER,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (variant_id, location_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_variants_product_id ON variants(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_variant_id ON inventory(variant_id);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email); 