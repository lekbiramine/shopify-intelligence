## Shopify Automation Pipeline

This project pulls data from Shopify (products, customers, orders, inventory), loads it into a PostgreSQL database, computes analytics, and emails a daily store intelligence report as a PDF attachment.
The current deployment model uses a private Shopify app install flow (OAuth) for selected clients. No public listing, client portal, or onboarding UI is required.

## What it does

- Extracts Shopify data via the Admin REST API
- Transforms the raw API responses into database-ready records
- Loads/upserts records into PostgreSQL
- Builds an analytics summary (inventory alerts, customer insights, revenue summary, anomalies, and a short “action required” insights block)
- Generates a PDF report and sends it by email (SMTP SSL)
- Supports private app OAuth onboarding (`install -> callback -> token storage`)

**Inventory alert bands** (mutually exclusive, see `config/constants.py`): out of stock = 0; critical = 1 through `CRITICAL_STOCK_THRESHOLD`; low = one above critical through `LOW_STOCK_THRESHOLD`.

## Requirements

- Python 3.10+ (recommended)
- A PostgreSQL database and connection settings:
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Shopify Admin API access:
  - `SHOPIFY_STORE_URL`
  - `SHOPIFY_ACCESS_TOKEN`
- Optional (future use only) Shopify OAuth app settings:
  - `SHOPIFY_API_KEY`
  - `SHOPIFY_API_SECRET`
  - `SHOPIFY_APP_BASE_URL`
  - `SHOPIFY_SCOPES`
  - `ENABLE_PUBLIC_ONBOARDING=false` keeps all public onboarding endpoints disabled
- SMTP credentials for sending email:
  - `SMTP_HOST`, `SMTP_PORT`
  - `EMAIL_SENDER`, `EMAIL_PASSWORD`
  - `EMAIL_RECIPIENT`

## Setup

1. Create a virtual environment and install dependencies
   ```bash
   python -m venv venv
   # Windows (PowerShell):
   .\\venv\\Scripts\\Activate.ps1
   pip install -r requirements.txt
   ```

2. Configure environment variables
   - Copy `.env.example` to `.env`
   - Fill in the values for the required settings (Shopify, DB, email)

3. Initialize the database schema
   ```bash
   python scripts\\init_db.py
   ```

Optional (development only):

- Seed example data:
  ```bash
  python scripts\\seed_data.py
  ```

## Usage

### Run the full ETL + reporting pipeline

```bash
python scheduler\\run_pipeline.py
```

### Run via the CLI entrypoint

`main.py` supports selecting which part to run:

```bash
python main.py --task full
python main.py --task etl
python main.py --task report
```

Tasks are implemented in `scheduler\\tasks.py` (ETL only, reporting only, or full pipeline).

### Private install onboarding (OAuth)

```bash
uvicorn onboarding.app:app --host 0.0.0.0 --port 8000
```

Send selected clients a direct install link:

```bash
https://<YOUR_BASE_URL>/install?shop=your-store.myshopify.com&email=owner@yourstore.com&ref=CREATORCODE
```

What onboarding validates:
- OAuth callback HMAC + state signature
- Token exchange using app credentials
- Granted scopes are read-only and include:
  - `read_products`
  - `read_orders`
  - `read_inventory`
  - `read_customers`

Notes on Shopify customer/order access:
- Even with `read_customers` and `read_orders`, Shopify can still block access with `403` / `ACCESS_DENIED` if your app is not approved for Protected Customer Data in the Partner Dashboard.
- ETL now tries REST first, then automatically falls back to GraphQL for both customers and orders when REST is denied.
- Run diagnostics:
  ```bash
  python scripts\diagnose_shopify_access.py --shop-domain your-store.myshopify.com
  ```
  This prints token validity, stored/live scopes, REST endpoint status, and GraphQL error details.

If `ref` is provided in the install URL, the system stores that code during install and links it to the store after OAuth completes.

### Referral code CLI (creator/affiliate tracking)

Create a code:

```bash
python scripts\referrals.py create --partner "Creator Name"
python scripts\referrals.py create --partner "Creator Name" --code CREATOR20 --discount 20
```

List codes with stats:

```bash
python scripts\referrals.py list
```

Show one code with linked stores:

```bash
python scripts\referrals.py show --code CREATOR20
```

Deactivate a code:

```bash
python scripts\referrals.py deactivate --code CREATOR20
```

Preview discount math:

```bash
python scripts\referrals.py discount --amount 100 --percent 20
```

### Run manual CSV service workflow (no OAuth)

This temporary workflow keeps FastAPI/OAuth code in place for long-term automation, but removes onboarding friction for early users.
Clients export store data as CSV files, and you process/report locally using the same analytics and PDF/email reporting pipeline.

Expected CSV files in one folder:

- `products.csv`
- `variants.csv`
- `customers.csv`
- `orders.csv`
- `order_items.csv`
- `inventory.csv`

Run:

```bash
python scheduler\\run_manual_csv_reports.py --shop-domain client-a.myshopify.com --recipient-email owner@client.com --data-dir data\\manual_export
```

### Run one managed store job (internal trigger)

```bash
python scripts\run_store_job.py --shop-domain your-store.myshopify.com
```

Or use the same per-client env file:

```bash
python scripts\run_store_job.py --env-file "D:\client-envs\client-a.env"
```

This runs ETL + report delivery for a previously onboarded store using stored per-shop OAuth credentials.

### Basic monitoring (job failures + email send status)

Initialize monitoring schema once:

```bash
python scripts\init_monitoring.py
```

Check recent runs:

```bash
python scripts\job_status.py --limit 20
```

Show only failures:

```bash
python scripts\job_status.py --only-failed
```

### Task workflow CLI (action tracking)

List tasks for one store:

```bash
python scripts\tasks_cli.py list --shop-domain your-store.myshopify.com
```

Mark a task in progress or completed:

```bash
python scripts\tasks_cli.py mark --task-id 123 --status in_progress
python scripts\tasks_cli.py mark --task-id 123 --status completed
```

Show task details and measured impact:

```bash
python scripts\tasks_cli.py show --task-id 123
```

## Logs

Logs are written to `logs/`:

- `logs/app.log` (all logs)
- `logs/errors.log` (errors only)

## Tests

Run the test suite with:

```bash
pytest
```

