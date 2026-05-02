from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.connection import get_cursor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Onboard a client contact email.")
    parser.add_argument("--shop", required=True, help="Shop domain, e.g. their-store.myshopify.com")
    parser.add_argument("--email", required=True, help="Client contact email")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE stores
            SET contact_email = %s,
                updated_at = NOW()
            WHERE shop_domain = %s;
            """,
            (args.email, args.shop),
        )
        updated = cursor.rowcount

    if updated == 0:
        print("✗ Store not found. Ask client to install the app first.")
        raise SystemExit(1)

    print(f"✓ Client onboarded: {args.shop} → {args.email}")


if __name__ == "__main__":
    main()
