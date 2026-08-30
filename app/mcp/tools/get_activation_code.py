import re
from typing import Any, Dict, Optional

# Verified USSD codes (single source of truth matching source PDFs)
USSD_REGISTRY = {
    "hekaya": {
        "ussd_code": "*319#",
        "description": "General Hekaya bundle activation menu (*319#) or direct tier code",
        "service": "Hekaya",
    },
    "hekaya mixat": {
        "ussd_code": "*319#",
        "description": "Hekaya Mixat monthly bundles (*319*45# for 52, *319*69# for 69, *319*80# for 92, *319*105# for 120, *319*155# for 180, *319*235# for 270)",
        "service": "Hekaya Mixat",
    },
    "hekaya internet": {
        "ussd_code": "*319#",
        "description": "Hekaya Internet bundles (*319# or *566#)",
        "service": "Hekaya Internet",
    },
    "mini hekaya": {
        "ussd_code": "*811#",
        "description": "Mini Hekaya recharge tiers (19, 22.5, 30 via *811#)",
        "service": "Hekaya Mini",
    },
    "hekaya mini": {
        "ussd_code": "*811#",
        "description": "Hekaya Mini recharge tiers (19, 22.5, 30 via *811#)",
        "service": "Hekaya Mini",
    },
    "extra": {
        "ussd_code": "*626#",
        "description": "Hekaya Mixat Extra add-ons (*626# for Extra 4.5, Extra 7.5, Extra 15)",
        "service": "Hekaya Extra",
    },
    "aqwa card": {
        "ussd_code": "*811#",
        "description": "Aqwa Card recharge and units allocation menu (*811#)",
        "service": "Aqwa Card",
    },
    "super connect": {
        "ussd_code": "*566#",
        "description": "Super Connect mobile internet add-ons menu (*566#)",
        "service": "Super Connect",
    },
    "dataline": {
        "ussd_code": "*130#",
        "description": "DataLine data-only SIM and MiFi renewal menu (*130#)",
        "service": "DataLine",
    },
    "data line": {
        "ussd_code": "*130#",
        "description": "DataLine data-only SIM and MiFi renewal menu (*130#)",
        "service": "DataLine",
    },
    "emerald": {
        "ussd_code": "Call 111 or visit e& store",
        "description": "Emerald postpaid line subscription via customer service 111 or official stores",
        "service": "Emerald Postpaid",
    },
    "daily": {
        "ussd_code": "*972#",
        "description": "Daily Bundle 55 Mixes (*972#) and Daily Bundle 120 Mixes (*973#)",
        "service": "Daily Plans",
    },
    "menu el geneh": {
        "ussd_code": "*101#",
        "description": "Menu El Geneh micro-bundles subscription (*101#)",
        "service": "Menu El Geneh",
    },
    "ahlan": {
        "ussd_code": "*339#",
        "description": "Ahlan Pay As You Go migration and services (*339#)",
        "service": "Ahlan",
    },
}

HEKAYA_MIXAT_TIER_CODES = {
    "52": "*319*45#",
    "69": "*319*69#",
    "92": "*319*80#",
    "120": "*319*105#",
    "180": "*319*155#",
    "270": "*319*235#",
}

DAILY_TIER_CODES = {
    "55": "*972#",
    "120": "*973#",
}


def get_activation_code_tool(
    service: str,
    package: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the verified USSD activation code for an e& Egypt service.

    Args:
        service: Service name (e.g. "Hekaya", "Aqwa Card", "DataLine", "Super Connect").
        package: Optional specific tier (e.g. "52", "180" or "92" for Hekaya).

    Returns:
        Dict with package, service, activation_code, source, verification_status, instructions.
    """
    raw_service = str(service or "").strip()
    key = raw_service.lower()

    # Normalization
    key = re.sub(r"أقوى\s*كارت|اقوى\s*كارت|اقوي\s*كارت|كارت", "aqwa card", key)
    key = re.sub(r"حكاية\s*مكسات|حكاية\s*ميكسات|مكسات", "hekaya mixat", key)
    key = re.sub(r"حكاية\s*إنترنت|حكاية\s*انترنت|باقة\s*نت", "hekaya internet", key)
    key = re.sub(r"ميني\s*حكاية|حكاية\s*ميني|ميني", "hekaya mini", key)
    key = re.sub(r"سوبر\s*كونكت|سوبركونكت", "super connect", key)
    key = re.sub(r"داتا\s*لاين|داتالاين", "dataline", key)
    key = re.sub(r"إمرالد|امرالد", "emerald", key)
    key = re.sub(r"اكسترا|إكسترا|extra", "extra", key)
    key = re.sub(r"يومي|يومية|daily", "daily", key)

    tier_to_check = str(package or raw_service)
    nums = re.findall(r"\d+(?:\.\d+)?", tier_to_check)

    # 1. Direct Hekaya Mixat tier resolution
    if "mixat" in key or "مكسات" in raw_service.lower() or (nums and nums[0] in HEKAYA_MIXAT_TIER_CODES):
        if nums and nums[0] in HEKAYA_MIXAT_TIER_CODES:
            t_code = HEKAYA_MIXAT_TIER_CODES[nums[0]]
            return {
                "found": True,
                "verification_status": "verified",
                "service": f"Hekaya Mixat {nums[0]}",
                "package": f"Hekaya Mixat {nums[0]}",
                "activation_code": t_code,
                "ussd_code": t_code,
                "description": f"Hekaya Mixat {nums[0]} subscription code ({t_code})",
                "source": "e& Egypt Official USSD Registry",
                "instructions": f"اطلب الكود {t_code} للتفعيل المباشر لباقة حكاية مكسات {nums[0]}.",
            }

    # 2. Extra add-ons
    if "extra" in key or "اكسترا" in raw_service.lower():
        return {
            "found": True,
            "verification_status": "verified",
            "service": "Hekaya Extra",
            "package": "Hekaya Extra Add-ons",
            "activation_code": "*626#",
            "ussd_code": "*626#",
            "description": "Hekaya Mixat Extra add-ons subscription (*626#)",
            "source": "e& Egypt Official USSD Registry",
            "instructions": "اطلب الكود *626# للاشتراك في باقات إكسترا الإضافية (Extra 4.5, Extra 7.5, Extra 15).",
        }

    # 3. Daily plans
    if "daily" in key or "يومي" in raw_service.lower():
        if nums and nums[0] in DAILY_TIER_CODES:
            d_code = DAILY_TIER_CODES[nums[0]]
            return {
                "found": True,
                "verification_status": "verified",
                "service": f"Daily Bundle {nums[0]} Mixes",
                "package": f"Daily {nums[0]}",
                "activation_code": d_code,
                "ussd_code": d_code,
                "description": f"Daily Bundle {nums[0]} subscription ({d_code})",
                "source": "e& Egypt Official USSD Registry",
                "instructions": f"اطلب الكود {d_code} للاشتراك في الباقة اليومية {nums[0]} مكس.",
            }

    # 4. Standard Registry Lookup
    matched_entry = None
    for svc_key, entry in USSD_REGISTRY.items():
        if svc_key in key or key in svc_key:
            matched_entry = entry
            break

    if matched_entry is None:
        if "hekaya" in key:
            matched_entry = USSD_REGISTRY["hekaya"]
        else:
            return {
                "found": False,
                "verification_status": "not_found",
                "service": raw_service,
                "package": package or "",
                "activation_code": None,
                "source": "knowledge_base",
                "instructions": f"No official USSD code found for '{raw_service}'. Please dial 111 for assistance.",
            }

    ussd = matched_entry["ussd_code"]
    svc_name = matched_entry["service"]

    instructions = (
        f"اطلب الكود {ussd} من خط اتصالات للتفعيل مباشرة."
        if not str(ussd).startswith("Call")
        else f"لتفعيل باقات إمرالد يرجى الاتصال بـ 111 أو زيارة أقرب فرع اتصالات."
    )

    return {
        "found": True,
        "verification_status": "verified",
        "service": svc_name,
        "package": package or svc_name,
        "activation_code": ussd,
        "ussd_code": ussd,
        "description": matched_entry["description"],
        "source": "e& Egypt Official USSD Registry",
        "instructions": instructions,
    }


