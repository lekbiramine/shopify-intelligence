"""
Capture public/report-screenshot.png from the current HTML email (reporting.html_report).
Run from repo root: python scripts/capture_report_screenshot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright  # noqa: E402

from reporting.html_report import build_html_report  # noqa: E402

# Landing preview payload: realistic EXECUTE/IGNORE/DELTA + one action card (top matches marketing copy).
REPORT_DATA: dict = {
    "store_name": "Northwind Commerce",
    "date": "May 4, 2026",
    "status": "critical",
    "daily_impact": 3498.12,
    "total_value": 48973.65,
    "seven_day_projection": 18643.80,
    "execute_value": 4847.20,
    "ignore_loss": 2183.94,
    "delta": 2663.26,
    "root_cause": "INVENTORY IMBALANCE",
    "actions": [
        {
            "number": "1",
            "type": "PRIMARY REVENUE LEAK",
            "action_type": "dead_inventory",
            "daily_impact": 3498.12,
            "targets": [],
            "metrics": {
                "sku_count": 2,
                "total_units": 75,
                "days_stale": 90,
                "estimated_value": 48973.65,
                "store_aov": 64.50,
            },
            "advice_headline_override": (
                "2 SKUs have been silent for 90 days — that's $48,973.65 earning 0% return"
            ),
            "advice_context_override": (
                "Dead inventory is not a storage problem, it's a cash flow problem. Every day these "
                "75 units sit unsold..."
            ),
        },
    ],
}


def main() -> int:
    out = REPO / "frontend" / "public" / "report-screenshot.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = build_html_report(REPORT_DATA)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 720, "height": 800})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print("Wrote", out, f"({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
