"""
Tool: get_activation_code
Deterministic USSD/activation-code lookup. Tier-specific codes come straight
from the catalog; a handful of service-level codes not tied to one tier
(e.g. the generic Hekaya menu) live in app/data/catalog/ussd_codes.yaml.
"""
from typing import Any, Dict, Optional

from app.data.catalog import get_catalog, get_ussd_services
from app.tools.normalize import guess_family, normalize


def _instructions(code: Optional[str]) -> str:
    if not code or str(code).lower().startswith("call"):
        return "لتفعيل هذه الخدمة يرجى الاتصال بـ 111 أو زيارة أقرب فرع اتصالات."
    return f"اطلب الكود {code} من خط اتصالات للتفعيل المباشر."


def get_activation_code_tool(service: str, package: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the verified USSD activation code for an e& Egypt service/package.

    Args:
        service: Service or family name (e.g. "Hekaya", "Aqwa Card", "DataLine").
        package: Optional specific tier (e.g. "52", "Hekaya Mixat 180").
    """
    raw_service = str(service or "").strip()
    query = f"{raw_service} {package or ''}".strip()
    normalized = normalize(query)
    catalog = get_catalog()

    # 1. Most specific: an exact/substring tier match (e.g. "Hekaya Mixat 92").
    for tier in catalog.all_tiers():
        tier_norm = normalize(tier["name_en"])
        if tier_norm == normalized or (tier_norm and tier_norm in normalized):
            return {
                "found": True,
                "verification_status": "verified",
                "service": tier["name_en"],
                "package": tier["name_en"],
                "activation_code": tier["ussd_code"],
                "ussd_code": tier["ussd_code"],
                "description": tier.get("description_en", ""),
                "source": "e& Egypt Official USSD Registry",
                "instructions": _instructions(tier["ussd_code"]),
            }

    # 2. Family-level default code (e.g. just "Aqwa Card", no tier given).
    family_id = guess_family(normalized)
    if family_id:
        family = catalog.family(family_id)
        if family:
            code = family.get("default_ussd")
            return {
                "found": True,
                "verification_status": "verified",
                "service": family["family_name_en"],
                "package": package or family["family_name_en"],
                "activation_code": code,
                "ussd_code": code,
                "description": family.get("family_description_en", ""),
                "source": "e& Egypt Official USSD Registry",
                "instructions": _instructions(code),
            }

    # 3. Standalone service registry (menu codes, aliases not modeled as tiers).
    for entry in get_ussd_services():
        key_norm = entry["key"].replace("_", " ")
        if key_norm in normalized or normalized in key_norm:
            return {
                "found": True,
                "verification_status": "verified",
                "service": entry["name_en"],
                "package": package or entry["name_en"],
                "activation_code": entry["ussd_code"],
                "ussd_code": entry["ussd_code"],
                "description": entry.get("description_en", ""),
                "source": "e& Egypt Official USSD Registry",
                "instructions": _instructions(entry["ussd_code"]),
            }

    return {
        "found": False,
        "verification_status": "not_found",
        "service": raw_service,
        "package": package or "",
        "activation_code": None,
        "source": "catalog",
        "instructions": f"No official USSD code found for '{raw_service}'. Please dial 111 for assistance.",
    }
