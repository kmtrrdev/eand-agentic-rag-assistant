"""
Tool: recommend_packages
Deterministic, constraint-based package recommendation. Takes the structured
constraints already extracted by the agent's classify step (budget, family,
device type) rather than re-parsing raw customer text itself.
"""
from typing import Any, Dict, Optional

from app.data.catalog import get_catalog
from app.tools.calculate_price import calculate_price_tool

_DEVICE_FAMILIES = {
    "phone": ["aqwa_card", "hekaya_mixat", "hekaya_internet", "emerald"],
    "mobile": ["aqwa_card", "hekaya_mixat", "hekaya_internet", "emerald"],
    "router": ["dataline"],
    "mifi": ["dataline"],
    "modem": ["dataline"],
    "usb": ["dataline"],
}


def _quota_gb(tier: Dict[str, Any]) -> float:
    if "quota_gb" in tier and tier["quota_gb"] is not None:
        return float(tier["quota_gb"])
    if "quota_mb" in tier and tier["quota_mb"] is not None:
        return float(tier["quota_mb"]) / 1024.0
    if "internet_gb" in tier and tier["internet_gb"] is not None:
        return float(tier["internet_gb"])
    return 0.0


def _with_after_tax_total(tier: Dict[str, Any]) -> Dict[str, Any]:
    calc = calculate_price_tool(base_price=tier["price_egp"], tax_type=tier.get("tax_type", "prepaid"))
    tier_copy = dict(tier)
    if calc.get("found"):
        tier_copy["total_egp"] = calc["total_egp"]
        tier_copy["tax_amount_egp"] = calc["tax_amount_egp"]
        tier_copy["flat_fee_egp"] = calc["flat_fee_egp"]
    if "activation_code" not in tier_copy and "ussd_code" in tier_copy:
        tier_copy["activation_code"] = tier_copy["ussd_code"]
    return tier_copy


def _is_addon_tier(tier: Dict[str, Any]) -> bool:
    tier_id = str(tier.get("id", "")).lower()
    fam = str(tier.get("family", "")).lower()
    name = str(tier.get("name_en", "")).lower()
    if fam == "daily_addons":
        return True
    if "extra" in tier_id or "addon" in tier_id or "extra" in name or "add-on" in name:
        return True
    return False


def recommend_packages_tool(
    budget_egp: Optional[float] = None,
    family: Optional[str] = None,
    device_type: Optional[str] = None,
    min_data_gb: Optional[float] = None,
    usage_focus: Optional[str] = None,
    include_addons: bool = False,
    max_results: int = 3,
    min_price_egp: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Args:
        budget_egp: the customer's total available cash — compared against the
            AFTER-TAX total, not the bare listed price, since that's what they
            actually have to pay.
        family: a specific catalog family id (e.g. "hekaya_mixat"); overrides device_type.
        device_type: "phone" or "router"/"mifi" — used to pick candidate families
            when no specific family is named.
        min_data_gb: minimum data quota required, if the customer cares about data.
        usage_focus: "minutes"/"calls" or "data"/"internet" — prioritizes plans matching
            the customer's usage pattern.
        include_addons: whether to include add-on top-ups (default False: customer wants a real plan).
        max_results: how many recommendations to return.
        min_price_egp: minimum BASE price — filters out plans at or below this price.
            Used for "show me higher tiers" follow-ups (typically no budget cap).
    """
    catalog = get_catalog()

    focus = (usage_focus or "").lower()
    if device_type and device_type.lower() in ("router", "mifi", "modem", "usb"):
        family = "dataline"
    elif focus in ("minutes", "calls", "voice", "دقايق", "مكالمات"):
        if not family or family in ("hekaya_internet", "hekaya", "super_connect", "dataline"):
            family = "hekaya_mixat"
    elif focus in ("data", "internet", "نت", "انترنت"):
        if not family or family in ("hekaya_mixat", "hekaya"):
            if not device_type or device_type.lower() not in ("router", "mifi", "modem", "usb"):
                family = "hekaya_internet"

    if family and catalog.family(family):
        pool = catalog.tiers_for_family(family)
    elif device_type and device_type.lower() in _DEVICE_FAMILIES:
        pool = [t for f in _DEVICE_FAMILIES[device_type.lower()] for t in catalog.tiers_for_family(f)]
    else:
        pool = [t for f in _DEVICE_FAMILIES["phone"] for t in catalog.tiers_for_family(f)]

    # Attach family to each tier if missing
    for t in pool:
        if "family" not in t:
            # Infer family from tier id
            for f in catalog.families:
                if t["id"].startswith(f):
                    t["family"] = f
                    break

    # Exclude add-ons / top-ups unless customer specifically asked for add-ons
    if not include_addons:
        pool = [t for t in pool if not _is_addon_tier(t)]

    candidates = [_with_after_tax_total(t) for t in pool]
    if min_data_gb is not None:
        candidates = [t for t in candidates if _quota_gb(t) >= float(min_data_gb)]

    # ── "Higher tiers" mode: min_price_egp set, no budget cap ───────────────
    # Return plans ABOVE the price floor, sorted ascending by price.
    if min_price_egp is not None and budget_egp is None:
        min_val = float(min_price_egp)
        higher = [t for t in candidates if float(t["price_egp"]) > min_val]
        higher.sort(key=lambda t: float(t["price_egp"]))
        top = higher[:max_results]
        for t in top:
            t["recommendation_role"] = "higher_tier"
        return {
            "found": bool(top),
            "count": len(top),
            "recommendations": top,
            "constraints_applied": {
                "budget_egp": budget_egp,
                "family": family,
                "device_type": device_type,
                "min_data_gb": min_data_gb,
                "usage_focus": usage_focus,
                "min_price_egp": min_price_egp,
            },
        }

    if focus in ("minutes", "calls", "voice", "دقايق", "مكالمات"):
        # Prioritize voice/mix plans (Hekaya Mixat, Aqwa Card, Emerald) over pure internet plans
        def _sort_key(t: Dict[str, Any]):
            t_fam = t.get("family", "")
            mins = t.get("local_minutes") or t.get("quota_units") or 0
            is_voice_plan = 1 if t_fam in ("hekaya_mixat", "aqwa_card", "emerald") or mins > 300 else 0
            return (is_voice_plan, float(t["price_egp"]))
    elif focus in ("data", "internet", "نت", "انترنت"):
        def _sort_key(t: Dict[str, Any]):
            t_fam = t.get("family", "")
            is_data_plan = 1 if t_fam in ("hekaya_internet", "super_connect", "dataline", "emerald") else 0
            return (is_data_plan, _quota_gb(t), float(t["price_egp"]))
    else:
        # Best value first: highest price tier
        def _sort_key(t: Dict[str, Any]):
            return float(t["price_egp"])

    if budget_egp is not None:
        b_val = float(budget_egp)
        candidates_within = [t for t in candidates if float(t.get("total_egp", t["price_egp"])) <= b_val]
        candidates_above = [t for t in candidates if float(t.get("total_egp", t["price_egp"])) > b_val]

        # If the requested family reached its ceiling, offer the next tier up from Emerald
        if not candidates_above:
            emerald_pool = [_with_after_tax_total(t) for t in catalog.tiers_for_family("emerald")]
            emerald_above = [t for t in emerald_pool if float(t.get("total_egp", t["price_egp"])) > b_val]
            if emerald_above:
                candidates_above = emerald_above

        # Sort within-budget candidates: best matching value first
        candidates_within.sort(key=_sort_key, reverse=True)

        top = []
        best_within = None
        if candidates_within:
            best_within = dict(candidates_within[0])
            best_within["recommendation_role"] = "within_budget"
            best_within["fits_after_tax_budget"] = True
            best_within["remaining_budget_egp"] = round(
                b_val - float(best_within.get("total_egp", best_within["price_egp"])), 2
            )
            top.append(best_within)

        # For the slightly-above-budget option (upsell / next tier up):
        # Prefer a package from the same family as best_within (or matching focus),
        # sorted by total_egp ASCENDING so it is the closest tier above budget.
        if candidates_above:
            target_family = best_within.get("family") if best_within else None
            same_family_above = (
                [t for t in candidates_above if t.get("family") == target_family]
                if target_family
                else []
            )

            above_pool = same_family_above if same_family_above else candidates_above
            # Sort by total cost ascending to pick the immediate next step up
            above_pool.sort(key=lambda t: float(t.get("total_egp", t["price_egp"])))

            best_above = dict(above_pool[0])
            best_above["recommendation_role"] = "slightly_above_budget_upgrade"
            best_above["fits_after_tax_budget"] = False
            best_above["extra_cost_over_budget_egp"] = round(
                float(best_above.get("total_egp", best_above["price_egp"])) - b_val, 2
            )
            if best_within:
                diff_cost = float(best_above.get("total_egp", best_above["price_egp"])) - float(
                    best_within.get("total_egp", best_within["price_egp"])
                )
                best_above["extra_cost_over_within_plan_egp"] = round(diff_cost, 2)

                # Persuasive comparison highlights for the prompt
                pitch_reasons = []
                u_above = best_above.get("quota_units") or best_above.get("quota_mb") or 0
                u_within = best_within.get("quota_units") or best_within.get("quota_mb") or 0
                if u_above and u_within and u_above > u_within:
                    pitch_reasons.append(f"وحدات ومكسات أكتر: {u_above:,} مقابل {u_within:,}")
                fam_above = best_above.get("family_lines") or best_above.get("family_members_limit") or 0
                fam_within = best_within.get("family_lines") or best_within.get("family_members_limit") or 0
                if fam_above > fam_within:
                    pitch_reasons.append(f"خطوط عيلة إضافية: {fam_above} خط بدل {fam_within}")

                best_above["upsell_pitch_points"] = pitch_reasons

            top.append(best_above)
    else:
        candidates.sort(key=_sort_key, reverse=True)
        top = candidates[:max_results]
        for t in top:
            t["recommendation_role"] = "general_recommendation"

    return {
        "found": bool(top),
        "count": len(top),
        "recommendations": top,
        "constraints_applied": {
            "budget_egp": budget_egp,
            "family": family,
            "device_type": device_type,
            "min_data_gb": min_data_gb,
            "usage_focus": usage_focus,
            "min_price_egp": min_price_egp,
        },
    }

