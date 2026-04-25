from pathlib import Path
import argparse
import secrets
import string
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.queries import (
    create_referral_code,
    deactivate_referral_code,
    get_referral_code_details,
    list_referral_codes_with_stats,
)
from utils.referrals import apply_referral_discount

logger = get_logger(__name__)


def _normalize_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise ValueError("Code cannot be empty.")
    allowed = set(string.ascii_uppercase + string.digits + "-_")
    if any(ch not in allowed for ch in code):
        raise ValueError("Code can only contain A-Z, 0-9, '-' and '_'.")
    return code


def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage affiliate/referral codes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="Create a referral code")
    create_cmd.add_argument("--partner", required=True, help="Partner/creator name")
    create_cmd.add_argument("--code", default="", help="Optional custom referral code")
    create_cmd.add_argument("--discount", type=float, default=20.0, help="Discount percent (default: 20)")

    subparsers.add_parser("list", help="List all referral codes with stats")

    show_cmd = subparsers.add_parser("show", help="Show details for one referral code")
    show_cmd.add_argument("--code", required=True, help="Referral code")

    deactivate_cmd = subparsers.add_parser("deactivate", help="Deactivate a referral code")
    deactivate_cmd.add_argument("--code", required=True, help="Referral code")

    discount_cmd = subparsers.add_parser("discount", help="Preview discount calculation for a code")
    discount_cmd.add_argument("--amount", type=float, required=True, help="Base amount")
    discount_cmd.add_argument("--percent", type=float, default=20.0, help="Discount percent")

    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    if args.command == "create":
        partner_name = (args.partner or "").strip()
        if not partner_name:
            raise ValueError("partner is required")
        discount_percent = float(args.discount)
        if discount_percent < 0 or discount_percent > 100:
            raise ValueError("discount must be between 0 and 100")

        if args.code:
            code = _normalize_code(args.code)
            created = create_referral_code(
                code=code,
                partner_name=partner_name,
                discount_percent=discount_percent,
            )
        else:
            created = None
            last_error = None
            for _ in range(5):
                code = _generate_code()
                try:
                    created = create_referral_code(
                        code=code,
                        partner_name=partner_name,
                        discount_percent=discount_percent,
                    )
                    break
                except Exception as exc:
                    last_error = exc
            if not created:
                raise RuntimeError(f"Unable to generate unique code: {last_error}")
        print(f"Created code {created['code']} for {created['partner_name']} ({created['discount_percent']}% off)")
        return

    if args.command == "list":
        rows = list_referral_codes_with_stats()
        if not rows:
            print("No referral codes found.")
            return
        for row in rows:
            print(
                f"{row['code']} | partner={row['partner_name']} | discount={row['discount_percent']}% "
                f"| active={row['is_active']} | stores={row['store_count']} | created={row['created_at']}"
            )
        return

    if args.command == "show":
        code = _normalize_code(args.code)
        details = get_referral_code_details(code)
        if not details:
            print(f"Referral code not found: {code}")
            return
        print(
            f"Code={details['code']} | partner={details['partner_name']} | discount={details['discount_percent']}% "
            f"| active={details['is_active']} | stores={details['store_count']}"
        )
        if details["stores"]:
            print("Stores:")
            for store in details["stores"]:
                print(f" - {store['shop_domain']} (installed_at={store['installed_at']})")
        return

    if args.command == "deactivate":
        code = _normalize_code(args.code)
        updated = deactivate_referral_code(code)
        if not updated:
            print(f"Referral code not found: {code}")
            return
        print(f"Deactivated referral code: {code}")
        return

    if args.command == "discount":
        result = apply_referral_discount(args.amount, args.percent)
        print(
            f"Original={result['original_amount']:.2f} | "
            f"Discount={result['discount_percent']:.2f}% ({result['discount_amount']:.2f}) | "
            f"Final={result['final_amount']:.2f}"
        )
        return


if __name__ == "__main__":
    main()
