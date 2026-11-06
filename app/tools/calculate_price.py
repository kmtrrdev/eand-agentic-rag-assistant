"""
Tool: calculate_price
Deterministic, hallucination-safe price/tax calculator for e& Egypt packages.
Rates are read from app/data/catalog/tax_rules.yaml — the same file ingestion
renders into a RAG chunk, so a "why is there a 42% tax" question and this
tool's own math can never disagree.
"""
from typing import Any, Dict, Optional

from app.data.catalog import get_tax_rules


def calculate_price_tool(
    base_price: Optional[float] = None,
    pretax_price: Optional[float] = None,
    tax_type: str = "prepaid",
    tax_rate: Optional[float] = None,
    is_tax_inclusive: bool = False,
    discount_pct: float = 0.0,
) -> Dict[str, Any]:
    """
    Args:
        base_price / pretax_price: pre-tax price, or the customer's total budget
            if is_tax_inclusive=True (aliases; base_price wins if both given).
        tax_type: "prepaid", "postpaid", or "emerald" (see tax_rules.yaml).
        tax_rate: optional override (e.g. 0.30); disables the flat monthly fee,
            since an override is assumed to already be a full replacement rate.
        is_tax_inclusive: True to reverse-derive the pre-tax price from a total.
        discount_pct: optional 0-100 discount applied to the pre-tax price.
    """
    price_val = base_price if base_price is not None else pretax_price
    if price_val is None:
        return {"error": "Missing price parameter (base_price or pretax_price required)", "found": False}

    price_val = float(price_val)
    if price_val < 0:
        return {"error": "Price cannot be negative", "found": False}

    rates = get_tax_rules()
    tax_key = (tax_type or "prepaid").lower().strip()
    rule = rates.get(tax_key, rates["prepaid"])
    effective_tax_rate = float(tax_rate) if tax_rate is not None else float(rule["rate"])
    flat_fee = float(rule.get("flat_fee_egp", 0.0)) if tax_rate is None else 0.0

    discount_multiplier = 1.0 - (max(0.0, min(100.0, float(discount_pct))) / 100.0)

    if is_tax_inclusive:
        # Reverse calculation: price_val is the total the customer pays before
        # any discount. Derive pre-tax first, THEN discount, THEN recompute tax
        # and total from the discounted pre-tax price, so the breakdown stays
        # internally consistent whenever discount_pct > 0.
        pretax_before_discount = (price_val - flat_fee) / (1.0 + effective_tax_rate)
        pretax_price_egp = round(pretax_before_discount * discount_multiplier, 2)
    else:
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
        "breakdown": (
            f"Pre-tax: {pretax_price_egp:.2f} EGP + Tax ({round(effective_tax_rate * 100, 2)}%): "
            f"{tax_amount_egp:.2f} EGP{fee_note} = Total: {total_egp:.2f} EGP"
        ),
        "explanation_ar": (
            f"السعر قبل الضريبة: {pretax_price_egp:.2f} جنيه | قيمة الضريبة: {tax_amount_egp:.2f} جنيه"
            f"{fee_note_ar} | الإجمالي المطلوب: {total_egp:.2f} جنيه"
        ),
        "explanation_en": (
            f"Pre-tax price: {pretax_price_egp:.2f} EGP | Tax: {tax_amount_egp:.2f} EGP{fee_note} "
            f"| Total: {total_egp:.2f} EGP"
        ),
    }
