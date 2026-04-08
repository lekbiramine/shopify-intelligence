## Shopify Automation Pipeline

This project pulls data from Shopify (products, customers, orders, inventory), loads it into a PostgreSQL database, computes analytics, and emails a daily store intelligence report as a PDF attachment.

## What it does

- Extracts Shopify data via the Admin REST API
- Transforms the raw API responses into database-ready records
- Loads/upserts records into PostgreSQL
- Builds an analytics summary (inventory alerts, customer insights, revenue summary, anomalies, and a short “action required” insights block)
- Generates a PDF report and sends it by email (SMTP SSL)

**Inventory alert bands** (mutually exclusive, see `config/constants.py`): out of stock = 0; critical = 1 through `CRITICAL_STOCK_THRESHOLD`; low = one above critical through `LOW_STOCK_THRESHOLD`.

## Requirements

- Python 3.10+ (recommended)
- A PostgreSQL database and connection settings:
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Shopify Admin API access:
  - `SHOPIFY_STORE_URL`
  - `SHOPIFY_ACCESS_TOKEN`
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

## Logs

Logs are written to `logs/`:

- `logs/app.log` (all logs)
- `logs/errors.log` (errors only)

## Tests

Run the test suite with:

```bash
pytest
```

