"""
app/mcp/tools/recommend_package.py
----------------------------------
MCP tool: recommend_package
Deterministic, rule-grounded package recommendation engine for e& Egypt.
"""
from typing import Any, Dict, List, Optional
from app.mcp.tools.get_package_details import PACKAGE_REGISTRY
from app.mcp.tools.calculate_price import calculate_price_tool


def recommend_package_tool(
    budget_egp: Optional[float] = None,
    includes_tax: bool = True,
    service: Optional[str] = None,
    service_type: Optional[str] = None,
    usage_type: Optional[str] = None,
    data_gb_needed: Optional[float] = None,
    minutes_needed: Optional[int] = None,
    line_type: Optional[str] = "mobile_phone",
    top_n: int = 3,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Recommend the optimal e& Egypt telecom packages deterministically matching customer constraints.

    Args:
        budget_egp: Maximum budget in EGP.
        includes_tax: If True, budget is total tax-inclusive recharge amount. If False, budget is pre-tax.
        service: Optional track filter: "Hekaya Mixat", "Hekaya Internet", "Emerald", "DataLine".
        service_type: "VOICE", "INTERNET", "MIXED", "UNKNOWN".
        usage_type: "data_heavy", "calls_heavy", "balanced", "mifi", "family".
        data_gb_needed: Minimum data in GB required.
        minutes_needed: Minimum local minutes required.
        line_type: "mobile_phone", "mifi_router", "home_adsl".
        top_n: Number of candidate recommendations to return.
        constraints: Optional full structured recommendation constraints dictionary.

    Returns:
        Dict with recommended packages, primary recommendation, and budget fit analysis.
    """
    svc_filter = (service or "").lower().strip()
    st_filter = (service_type or "").upper().strip()
    usage = (usage_type or "").lower().strip()
    line = (line_type or "mobile_phone").lower().strip()

    if constraints:
        if not st_filter and constraints.get("service_type"):
            st_filter = constraints["service_type"].upper().strip()
        if budget_egp is None and constraints.get("budget"):
            budget_egp = constraints["budget"]
        if constraints.get("tax_included") is not None:
            includes_tax = constraints["tax_included"]
        if not svc_filter and constraints.get("package_category"):
            svc_filter = constraints["package_category"].lower().strip()
        if minutes_needed is None and constraints.get("min_minutes"):
            minutes_needed = constraints["min_minutes"]
        if data_gb_needed is None and constraints.get("min_data"):
            data_gb_needed = constraints["min_data"]

    # If line_type is MiFi/router, force DataLine
    if "mifi" in line or "router" in line or "usb" in line:
        svc_filter = "dataline"
        st_filter = "INTERNET"

    candidates = []
    rejected = []

    for pkg_key, pkg in PACKAGE_REGISTRY.items():
        pkg_svc = pkg.get("service", "").lower()
        is_internet_only = ("internet" in pkg_svc or "dataline" in pkg_svc or "super connect" in pkg_svc)
        is_voice_capable = ("mix" in pkg_svc or "aqwa" in pkg_svc or "emerald" in pkg_svc or "ahlan" in pkg_svc)

        # 1. Service Type Constraint (STRICT: VOICE vs INTERNET vs MIXED)
        if st_filter == "VOICE" or usage == "calls_heavy" or usage == "voice":
            if is_internet_only:
                rejected.append((pkg, "SERVICE_TYPE_MISMATCH (Internet-only package for voice request)"))
                continue
        elif st_filter == "INTERNET" or usage == "data_heavy":
            if not is_internet_only and "mix" not in pkg_svc:
                rejected.append((pkg, "SERVICE_TYPE_MISMATCH (Voice-only package for internet request)"))
                continue
        elif st_filter == "MIXED" or usage == "balanced":
            if is_internet_only:
                rejected.append((pkg, "SERVICE_TYPE_MISMATCH (Internet-only package for mixed request)"))
                continue

        # 2. Service Track Filter (e.g. Hekaya Mixat, Emerald)
        if svc_filter and svc_filter != "general":
            if "mix" in svc_filter and "mix" not in pkg_svc:
                continue
            if ("net" in svc_filter or "internet" in svc_filter) and "internet" not in pkg_svc:
                continue
            if "emerald" in svc_filter and "emerald" not in pkg_svc:
                continue
            if "dataline" in svc_filter and "dataline" not in pkg_svc:
                continue

        # 3. Line Type Filtering
        if line == "mifi_router" and "dataline" not in pkg_svc:
            continue
        if line == "mobile_phone" and "dataline" in pkg_svc:
            continue

        # 4. Budget Filtering (Tax-Aware)
        if budget_egp is not None and budget_egp > 0:
            price_to_check = pkg.get("total_price_egp", pkg.get("pretax_price_egp", 0.0)) if includes_tax else pkg.get("pretax_price_egp", 0.0)
            if price_to_check > (budget_egp * 1.02):
                rejected.append((pkg, f"BUDGET_EXCEEDED ({price_to_check} > {budget_egp})"))
                continue

        # 5. Minimum Minutes Requirement
        # NOTE: only packages with an explicit "minutes" field (currently Emerald
        # postpaid plans) carry a literal, dedicated local-minutes allowance. Mix-based
        # prepaid bundles ("mixes") are a shared pool for calls+SMS+data and are NOT a
        # reliable proxy for a hard minutes requirement, so we no longer silently fall
        # back to "mixes" (that previously rejected every Emerald plan with 0 < needed,
        # since Emerald entries have no "mixes" key at all).
        if minutes_needed is not None and minutes_needed > 0:
            if "minutes" in pkg:
                cand_mins = pkg.get("minutes", 0)
                if cand_mins < minutes_needed:
                    rejected.append((pkg, f"INSUFFICIENT_MINUTES ({cand_mins} < {minutes_needed})"))
                    continue
            elif "mixes" not in pkg:
                # No usable minutes/mixes data at all for this package family — skip the
                # check rather than wrongly rejecting it on a phantom value of 0.
                pass

        candidates.append(pkg)

    # Sort candidates by pre-tax price descending (highest value fitting budget)
    candidates.sort(key=lambda x: x["pretax_price_egp"], reverse=True)

    if not candidates:
        # Fallback entry package for the requested track/service type
        fallback_list = [p for p in PACKAGE_REGISTRY.values()]
        if st_filter == "VOICE":
            fallback_list = [p for p in fallback_list if "internet" not in p.get("service", "").lower()]
        elif st_filter == "INTERNET":
            fallback_list = [p for p in fallback_list if "internet" in p.get("service", "").lower() or "dataline" in p.get("service", "").lower()]
        elif svc_filter and svc_filter != "general":
            fallback_list = [p for p in fallback_list if svc_filter in p.get("service", "").lower()] or fallback_list

        fallback_list.sort(key=lambda x: x["pretax_price_egp"])
        entry_pkg = fallback_list[0] if fallback_list else None

        service_label = "دقايق ومكالمات" if st_filter == "VOICE" else ("إنترنت" if st_filter == "INTERNET" else (service or "مناسبة"))
        return {
            "found": False,
            "budget_egp": budget_egp,
            "includes_tax": includes_tax,
            "service_type": st_filter,
            "service_filter": service,
            "message": (
                f"مش لاقي باقة {service_label} تحقق شرط الـ {budget_egp} جنيه بالضبط. "
                f"أقرب باقة متاحة هي {entry_pkg.get('type', '')} بسعر {entry_pkg.get('pretax_price_egp', '')} جنيه قبل الضريبة "
                f"({entry_pkg.get('total_price_egp', '')} جنيه شامل الضريبة)."
                if entry_pkg else "لم يتم العثور على باقة مطابقة للشروط المحددة."
            ),
            "closest_entry_package": entry_pkg,
            "recommendations": [],
        }

    recommendations = candidates[:top_n]
    primary = recommendations[0]

    return {
        "found": True,
        "count": len(recommendations),
        "budget_egp": budget_egp,
        "includes_tax": includes_tax,
        "primary_recommendation": {
            "name": primary.get("package_name") or primary.get("type"),
            "service": primary.get("service"),
            "pretax_price_egp": primary.get("pretax_price_egp"),
            "total_price_egp": primary.get("total_price_egp"),
            "quota": primary.get("quota"),
            "activation_code": primary.get("activation_code") or primary.get("ussd"),
            "perks": primary.get("perks"),
            "description": primary.get("description"),
            "reason": (
                f"Highest value package fitting your budget of {budget_egp} EGP "
                f"({primary.get('quota')}, Total: {primary.get('total_price_egp')} EGP شامل الضريبة)."
                if budget_egp else f"Top recommended {primary.get('service')} package."
            ),
        },
        "all_recommendations": [
            {
                "name": p.get("package_name") or p.get("type"),
                "service": p.get("service"),
                "pretax_price_egp": p.get("pretax_price_egp"),
                "total_price_egp": p.get("total_price_egp"),
                "quota": p.get("quota"),
                "activation_code": p.get("activation_code") or p.get("ussd"),
                "perks": p.get("perks"),
            }
            for p in recommendations
        ],
    }
