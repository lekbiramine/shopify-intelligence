from decimal import Decimal, ROUND_HALF_UP


def apply_referral_discount(amount: float | int | Decimal, discount_percent: float | int | Decimal) -> dict:
    """
    Applies percentage discount and returns a structured result.
    """
    base_amount = Decimal(str(amount))
    percent = Decimal(str(discount_percent))
    if base_amount < 0:
        raise ValueError("amount must be >= 0")
    if percent < 0 or percent > 100:
        raise ValueError("discount_percent must be between 0 and 100")

    discount_amount = (base_amount * percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_amount = (base_amount - discount_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "original_amount": float(base_amount),
        "discount_percent": float(percent),
        "discount_amount": float(discount_amount),
        "final_amount": float(final_amount),
    }


def apply_discount_if_referral_valid(
    amount: float | int | Decimal,
    referral_code: str | None,
    referral_record: dict | None,
    default_percent: float = 20.0,
) -> dict:
    """
    Applies discount only when a valid active referral code record is provided.
    """
    if referral_code and referral_record and bool(referral_record.get("is_active", True)):
        percent = referral_record.get("discount_percent", default_percent)
        return apply_referral_discount(amount, percent)
    return apply_referral_discount(amount, 0)
