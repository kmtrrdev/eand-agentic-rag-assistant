"""
Deterministic tool execution (the graph's "ground truth" step — trace id
kept as "mcp_tool" for continuity with the existing frontend visualization,
even though there's no separate MCP client/server process here, just plain
in-process function calls into app/tools).
"""
from typing import Any, Dict, List, Optional

from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.data.catalog import get_catalog
from app.tools import (
    calculate_price_tool,
    get_activation_code_tool,
    get_family_packages_tool,
    get_package_details_tool,
    recommend_packages_tool,
)


def _tax_type_for(category: str, line_type: str) -> str:
    catalog = get_catalog()
    family = catalog.family(category) if category else None
    if family:
        return family.get("tax_type", "prepaid")
    return "postpaid" if line_type == "postpaid" else "prepaid"


def _enrich_with_after_tax_total(tiers: List[Dict[str, Any]], budget_egp: Optional[float]) -> List[Dict[str, Any]]:
    """Attach the after-tax total (and, if a budget is known, whether it fits)
    to each tier — a recommendation is only actually comparable to a
    customer's budget once tax is included, not the bare listed price."""
    enriched = []
    for tier in tiers:
        calc = calculate_price_tool(base_price=tier["price_egp"], tax_type=tier.get("tax_type", "prepaid"))
        tier_copy = dict(tier)
        if calc.get("found"):
            tier_copy["total_egp"] = calc["total_egp"]
            tier_copy["tax_amount_egp"] = calc["tax_amount_egp"]
            tier_copy["flat_fee_egp"] = calc["flat_fee_egp"]
            if budget_egp is not None:
                tier_copy["fits_after_tax_budget"] = calc["total_egp"] <= budget_egp
        enriched.append(tier_copy)
    return enriched


def tools_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    strategy = state.get("strategy", "")
    category = state.get("category") or ""
    package_name_raw = state.get("package_name_raw") or ""
    tier_price = state.get("tier_price_egp")

    tools_called: List[str] = []
    evidence: List[Dict[str, Any]] = []
    needs_clarification = False
    closest_matches: List[str] = []

    query_name = package_name_raw or (f"{category} {tier_price}" if category and tier_price else category)

    if strategy == "TOOL_EXACT":
        result = get_package_details_tool(query_name)
        tools_called.append("get_package_details")
        evidence.append(result)
        if not result.get("found"):
            needs_clarification = True
            budget_egp = state.get("budget_egp")
            if category and budget_egp is not None:
                # The classifier occasionally names a "tier" that's actually
                # just the family plus the customer's own budget number (e.g.
                # treating "200" as if it were a tier price) — when that
                # lookup fails but we do know a real family + budget, recover
                # with a budget-constrained recommendation instead of a dead
                # end clarification.
                rec_result = recommend_packages_tool(budget_egp=budget_egp, family=category)
                tools_called.append("recommend_packages")
                evidence.append(rec_result)
                if rec_result.get("found"):
                    needs_clarification = False
                else:
                    family_result = get_family_packages_tool(category)
                    tools_called.append("get_family_packages")
                    if family_result.get("found"):
                        family_result["tiers"] = _enrich_with_after_tax_total(family_result["tiers"], budget_egp)
                    evidence.append(family_result)
            else:
                closest_matches = result.get("closest_matches", [])
                # Fetch full details for each suggested match too, so
                # generate_node can actually describe them instead of just
                # naming them.
                for match_name in closest_matches:
                    match_result = get_package_details_tool(match_name)
                    if match_result.get("found"):
                        evidence.append(match_result)

    elif strategy == "TOOL_CALCULATION":
        price = tier_price if tier_price is not None else state.get("budget_egp")
        tax_type = _tax_type_for(category, state.get("line_type", ""))
        if price is None:
            # No specific price given — the customer is asking about the tax
            # RATE/structure itself ("what's the tax rate on prepaid?"), not a
            # total for one price. That's still fully answerable from
            # tax_rules.yaml without inventing anything.
            from app.data.catalog import get_tax_rules
            rule = get_tax_rules().get(tax_type, get_tax_rules()["prepaid"])
            tools_called.append("get_tax_rules")
            evidence.append({
                "found": True,
                "rate_only": True,
                "tax_type": tax_type,
                "tax_rate_pct": round(rule["rate"] * 100, 2),
                "flat_fee_egp": rule.get("flat_fee_egp", 0.0),
                "description_en": rule.get("description_en", ""),
                "description_ar": rule.get("description_ar", ""),
            })
        else:
            result = calculate_price_tool(base_price=price, tax_type=tax_type)
            tools_called.append("calculate_price")
            evidence.append(result)

    elif strategy == "TOOL_ACTIVATION":
        result = get_activation_code_tool(service=category or package_name_raw, package=package_name_raw)
        tools_called.append("get_activation_code")
        evidence.append(result)
        needs_clarification = not result.get("found")

    elif strategy == "TOOL_RECOMMENDATION":
        budget_egp = state.get("budget_egp")
        result = recommend_packages_tool(
            budget_egp=budget_egp,
            family=category or None,
            device_type=state.get("device_type"),
            usage_focus=state.get("usage_focus"),
            min_price_egp=state.get("min_price_egp"),
        )
        tools_called.append("recommend_packages")
        evidence.append(result)
        # Nothing in this family fits the stated budget — name the cheapest
        # real tier instead of leaving generate_node with no concrete answer
        # (same "always offer something real" principle as the not-found path).
        if not result.get("found") and category:
            family_result = get_family_packages_tool(category)
            tools_called.append("get_family_packages")
            if family_result.get("found"):
                family_result["tiers"] = _enrich_with_after_tax_total(family_result["tiers"], budget_egp)
            evidence.append(family_result)

    elif strategy == "TOOL_PLUS_RAG" or state.get("intent") == "comparison":
        entities = list(state.get("entities") or [])
        if package_name_raw and package_name_raw not in entities:
            entities.append(package_name_raw)

        exact_packages_found = 0
        seen_pkg_names = set()
        for ent in entities:
            res = get_package_details_tool(ent)
            if res.get("found"):
                pkg_id = res.get("package_name") or res.get("id")
                if pkg_id not in seen_pkg_names:
                    seen_pkg_names.add(pkg_id)
                    tools_called.append(f"get_package_details({pkg_id})")
                    evidence.append(res)
                    exact_packages_found += 1

        # Only fetch full family tiers if no exact packages were identified
        # or if only a single family was requested without a specific tier.
        if exact_packages_found < 2:
            detected_families = set()
            if category:
                if category == "hekaya":
                    detected_families.add("hekaya_mixat")
                    detected_families.add("hekaya_internet")
                else:
                    detected_families.add(category)
            q_lower = (state.get("question") or "").lower()
            catalog = get_catalog()
            for fid, fam in catalog.families.items():
                if (
                    fam["family_name_en"].lower() in q_lower
                    or fam["family_name_ar"] in q_lower
                    or fid.replace("_", " ") in q_lower
                    or fid in q_lower
                ):
                    detected_families.add(fid)

            # If general Hekaya is asked about without specifying mixat vs internet, include both
            if any(k in q_lower for k in ("hekaya", "حكاية", "حكايه")):
                has_mix = any(k in q_lower for k in ("mix", "مكس", "مكسات"))
                has_net = any(k in q_lower for k in ("internet", "نت", "انترنت", "إنترنت"))
                if not has_mix and not has_net:
                    detected_families.add("hekaya_mixat")
                    detected_families.add("hekaya_internet")

            # If entities had family names:
            for ent in entities:
                from app.tools.normalize import guess_family
                fam_guess = guess_family(ent)
                if fam_guess:
                    detected_families.add(fam_guess)

            if exact_packages_found == 0 or state.get("intent") != "comparison":
                for fid in detected_families:
                    fam_res = get_family_packages_tool(fid)
                    if fam_res.get("found"):
                        tools_called.append(f"get_family_packages({fid})")
                        evidence.append(fam_res)

    return {
        "mcp_tools_called": tools_called,
        "tool_evidence": evidence,
        "needs_clarification": needs_clarification,
        "closest_matches": closest_matches,
        "workflow_trace": [step(
            "mcp_tool", "5. Deterministic Tools", "٥. الحقيقة المؤكدة",
            description_en=f"Called: {', '.join(tools_called) or 'none'}.",
            badge="Done" if tools_called else "Skipped", status="completed",
            details={"candidate_count": len(evidence)},
            latency_ms=elapsed_ms(start),
        )],
    }
