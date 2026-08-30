"""
app/tools/calculate_price.py
-------------------------------
Tool: calculate_price
Deterministic, hallucination-safe telecom price and tax calculator for e& Egypt.
"""
from typing import Any, Dict, Optional


# Verified Egyptian Telecom Tax Rates (single source of truth).
# Prepaid / Hekaya / DataLine: 42.857% (1.42857x) recharge tax multiplier — these are
# prepaid recharge-based products; no source PDF states a different figure for them.
# Postpaid / Emerald: NOT the same structure — confirmed directly in Emerald (2).pdf,
# Section 9 ("Emerald Packages Pricing & Taxes Summary"): "An 8% Schedule Tax on the
# base price... A 14% Value Added Tax (VAT) on the base price... A 10 EGP State Resource
# Development fee applied monthly" — both percentages apply to the same base price
# (additive, ~22% combined), PLUS a flat EGP fee that no single percentage rate can
# express. See EMERALD_FLAT_FEE_EGP below.
DEFAULT_TAX_RATES = {
    "prepaid": 0.42857142857,
    "hekaya": 0.42857142857,
    "dataline": 0.42857142857,
    "postpaid": 0.22,  # 8% schedule tax + 14% VAT, additive, on base price
    "emerald": 0.22,
}

# Flat monthly fee added on top of the percentage tax for postpaid/Emerald only
# (Emerald (2).pdf, Section 9: "10 EGP State Resource Development fee").
EMERALD_FLAT_FEE_EGP = 10.0
_FLAT_FEE_TAX_TYPES = {"postpaid", "emerald"}


def calculate_price_tool(
    base_price: Optional[float] = None,
    pretax_price: Optional[float] = None,
    tax_type: str = "prepaid",
    tax_rate: Optional[float] = None,
    is_tax_inclusive: bool = False,
    discount_pct: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate exact tax, base price, and total amount for an e& Egypt package.

    Args:
        base_price: Base price (pre-tax) or total amount (if is_tax_inclusive=True).
        pretax_price: Alias for base_price when is_tax_inclusive=False.
        tax_type: "prepaid", "hekaya", "dataline", "postpaid", or "emerald".
        tax_rate: Optional custom tax rate override (e.g., 0.4286 for 42.86%).
        is_tax_inclusive: If True, base_price is treated as the customer's total budget/recharge,
                          and the pre-tax quota price is calculated.
        discount_pct: Optional percentage discount on base price (0-100).

    Returns:
        Dict with exact pre-tax price, tax amount, total price, breakdown, and explanations.
    """
    # Resolve input price
    price_val = base_price if base_price is not None else pretax_price
    if price_val is None:
        return {
            "error": "Missing price parameter (base_price or pretax_price required)",
            "found": False,
        }

    price_val = float(price_val)
    if price_val < 0:
        return {"error": "Price cannot be negative", "found": False}

    # Resolve tax rate
    tax_key = (tax_type or "prepaid").lower().strip()
    if tax_rate is not None:
        effective_tax_rate = float(tax_rate)
    else:
        effective_tax_rate = DEFAULT_TAX_RATES.get(tax_key, DEFAULT_TAX_RATES["prepaid"])

    # Apply discount if any
    discount_multiplier = 1.0 - (max(0.0, min(100.0, float(discount_pct))) / 100.0)

    # Emerald/postpaid carries an additional flat monthly fee that no percentage
    # rate can express (see EMERALD_FLAT_FEE_EGP above); a custom tax_rate override
    # is assumed to already be a full replacement rate, so the flat fee only applies
    # when the caller didn't override the rate for one of these tax types.
    flat_fee = EMERALD_FLAT_FEE_EGP if (tax_rate is None and tax_key in _FLAT_FEE_TAX_TYPES) else 0.0

    if is_tax_inclusive:
        # Reverse calculation: price_val is total customer pays (before any discount).
        # Derive the pre-tax price first, THEN apply the discount, THEN recompute tax and
        # total from the discounted pre-tax price. (Previously the discount was applied to
        # pretax_price_egp only, while total_egp stayed equal to the original undiscounted
        # input — producing an inconsistent breakdown whenever discount_pct > 0.)
        pretax_before_discount = (price_val - flat_fee) / (1.0 + effective_tax_rate)
        pretax_price_egp = round(pretax_before_discount * discount_multiplier, 2)
        tax_amount_egp = round(pretax_price_egp * effective_tax_rate, 2)
        total_egp = round(pretax_price_egp + tax_amount_egp + flat_fee, 2)
    else:
        # Standard forward calculation: price_val is pre-tax package price
        pretax_price_egp = round(price_val * discount_multiplier, 2)
        tax_amount_egp = round(pretax_price_egp * effective_tax_rate, 2)
        total_egp = round(pretax_price_egp + tax_amount_egp + flat_fee, 2)

    fee_note = f" + {flat_fee:.2f} EGP state fee" if flat_fee else ""
    fee_note_ar = f" + {flat_fee:.2f} جنيه رسوم الدولة" if flat_fee else ""
    return {
        "found": True,
        "pretax_price_egp": pretax_price_egp,
        "tax_type": tax_key,
        "tax_rate_pct": round(effective_tax_rate * 100, 2),
        "tax_amount_egp": tax_amount_egp,
        "flat_fee_egp": flat_fee,
        "total_egp": total_egp,
        "discount_pct": discount_pct,
        "is_tax_inclusive": is_tax_inclusive,
        "breakdown": f"Pre-tax: {pretax_price_egp:.2f} EGP + Tax ({round(effective_tax_rate*100, 2)}%): {tax_amount_egp:.2f} EGP{fee_note} = Total: {total_egp:.2f} EGP",
        "explanation_ar": f"السعر قبل الضريبة: {pretax_price_egp:.2f} جنيه | قيمة الضريبة: {tax_amount_egp:.2f} جنيه{fee_note_ar} | إجمالي الشحن المطلوب: {total_egp:.2f} جنيه",
        "explanation_en": f"Pre-tax price: {pretax_price_egp:.2f} EGP | Tax: {tax_amount_egp:.2f} EGP{fee_note} | Total recharge required: {total_egp:.2f} EGP",
    }
