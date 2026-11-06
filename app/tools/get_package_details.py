"""
Tool: get_package_details / get_family_packages
Structured, deterministic lookup against app/data/catalog — the single source
of truth also used by ingestion and calculate_price/get_activation_code.
"""
import re
from typing import Any, Dict, List

from app.data.catalog import get_catalog
from app.tools.normalize import guess_family, normalize


def _format(tier: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(tier)
    result["found"] = True
    result["package_name"] = tier.get("name_en")
    return result


def _nearest_tiers(candidates: List[Dict[str, Any]], target_price: float, n: int = 2) -> List[str]:
    ranked = sorted(candidates, key=lambda t: abs(float(t["price_egp"]) - target_price))
    return [t["name_en"] for t in ranked[:n]]


def _bounded_contains(needle: str, haystack: str) -> bool:
    """Substring match that respects token boundaries, so a bare price like
    "80" doesn't wrongly match inside an unrelated tier's price like "180"."""
    if not needle:
        return False
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


def get_package_details_tool(package_name: str) -> Dict[str, Any]:
    """
    Return structured details for a named e& Egypt package tier, e.g.
    "Aqwa Card 19", "Hekaya Mixat 52", "Emerald 430".
    """
    raw = str(package_name or "").strip()
    normalized = normalize(raw)
    catalog = get_catalog()

    # 1. Exact name match
    for tier in catalog.all_tiers():
        if normalize(tier["name_en"]) == normalized:
            return _format(tier)

    # 2. Family + exact price match (handles "aqwa 19", "امرالد 430", etc.)
    numbers = re.findall(r"\d+(?:\.\d+)?", normalized)
    family_id = guess_family(normalized)
    if numbers and family_id:
        target = float(numbers[0])
        for tier in catalog.tiers_for_family(family_id):
            if float(tier["price_egp"]) == target:
                return _format(tier)

    # 3. Substring match against tier names
    if normalized:
        for tier in catalog.all_tiers():
            tier_norm = normalize(tier["name_en"])
            if _bounded_contains(normalized, tier_norm) or _bounded_contains(tier_norm, normalized):
                return _format(tier)

    # 4. Not found — suggest the closest real tier so the assistant can offer
    # a "did you mean" clarification instead of inventing an answer.
    closest_matches: List[str] = []
    if numbers:
        target = float(numbers[0])
        pool = catalog.tiers_for_family(family_id) if family_id else catalog.all_tiers()
        if pool:
            closest_matches = _nearest_tiers(pool, target)

    return {
        "found": False,
        "package_name": raw,
        "closest_match": closest_matches[0] if closest_matches else None,
        "closest_matches": closest_matches,
        "message": f"Package '{raw}' was not found in the catalog.",
    }


def get_family_packages_tool(family_name: str) -> Dict[str, Any]:
    """Return every tier for a product family, sorted by price ascending."""
    normalized = normalize(family_name)
    family_id = guess_family(normalized)
    catalog = get_catalog()
    family = catalog.family(family_id) if family_id else None
    if not family:
        return {"found": False, "message": f"Unknown product family '{family_name}'."}

    tiers = sorted(family["tiers"], key=lambda t: float(t["price_egp"]))
    return {
        "found": True,
        "family": family["family_name_en"],
        "family_ar": family["family_name_ar"],
        "tier_count": len(tiers),
        "tiers": tiers,
    }
