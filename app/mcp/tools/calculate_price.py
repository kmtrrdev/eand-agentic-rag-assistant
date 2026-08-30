"""
app/mcp/tools/calculate_price.py
---------------------------------
MCP tool: calculate_price / calculate_total_price
Deterministic, hallucination-safe telecom price and tax calculator for e& Egypt.
"""
from typing import Any, Dict, Optional


# Verified Egyptian Telecom Tax Multipliers (single source of truth)
# Prepaid / Hekaya: 42.857% tax (Multiply pre-tax by 1.42857 to get total recharge amount)
# Postpaid / Emerald: ~22% effective tax (or standard invoice VAT)
DEFAULT_TAX_RATES = {
    "prepaid": 0.42857142857,
    "hekaya": 0.42857142857,
    "dataline": 0.42857142857,
    "postpaid": 0.42857142857,  # Prompt protocol specifies consistent pricing table
    "emerald": 0.42857142857,
}


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

    if is_tax_inclusive:
        # Reverse calculation: price_val is total customer pays (before any discount).
        # Derive the pre-tax price first, THEN apply the discount, THEN recompute tax and
        # total from the discounted pre-tax price. (Previously the discount was applied to
        # pretax_price_egp only, while total_egp stayed equal to the original undiscounted
        # input — producing an inconsistent breakdown whenever discount_pct > 0.)
        pretax_before_discount = price_val / (1.0 + effective_tax_rate)
        pretax_price_egp = round(pretax_before_discount * discount_multiplier, 2)
        tax_amount_egp = round(pretax_price_egp * effective_tax_rate, 2)
        total_egp = round(pretax_price_egp + tax_amount_egp, 2)
    else:
        # Standard forward calculation: price_val is pre-tax package price
        pretax_price_egp = round(price_val * discount_multiplier, 2)
        tax_amount_egp = round(pretax_price_egp * effective_tax_rate, 2)
        total_egp = round(pretax_price_egp + tax_amount_egp, 2)

    return {
        "found": True,
        "pretax_price_egp": pretax_price_egp,
        "tax_type": tax_key,
        "tax_rate_pct": round(effective_tax_rate * 100, 2),
        "tax_amount_egp": tax_amount_egp,
        "total_egp": total_egp,
        "discount_pct": discount_pct,
        "is_tax_inclusive": is_tax_inclusive,
        "breakdown": f"Pre-tax: {pretax_price_egp:.2f} EGP + Tax ({round(effective_tax_rate*100, 2)}%): {tax_amount_egp:.2f} EGP = Total: {total_egp:.2f} EGP",
        "explanation_ar": f"السعر قبل الضريبة: {pretax_price_egp:.2f} جنيه | قيمة الضريبة: {tax_amount_egp:.2f} جنيه | إجمالي الشحن المطلوب: {total_egp:.2f} جنيه",
        "explanation_en": f"Pre-tax price: {pretax_price_egp:.2f} EGP | Tax: {tax_amount_egp:.2f} EGP | Total recharge required: {total_egp:.2f} EGP",
    }


def calculate_total_price_tool(
    pretax_price: float,
    tax_type: str = "prepaid",
    **kwargs,
) -> Dict[str, Any]:
    """Compatibility alias for calculate_price_tool."""
    return calculate_price_tool(
        pretax_price=pretax_price,
        tax_type=tax_type,
        **kwargs,
    )
