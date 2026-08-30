"""
app/agent/nodes/mcp_tool_node.py
---------------------------------
LangGraph node that calls the structured, deterministic telecom tools directly:
  USER -> AGENT -> STRATEGY DECISION -> TOOL CALL -> VERIFIED CONTEXT -> GENERATION

These are plain Python functions over an in-process product registry, not a
protocol boundary — there used to be a client/server "MCP" indirection wrapping
them, but everything ran in one process with no real IPC, schema validation, or
cross-language boundary to justify it, so it was removed. The "mcp_tool" node
name, "mcp_evidence"/"mcp_tools_called" state fields, and "MCP_*" strategy labels
are kept as-is (internal identifiers, not user-facing) to avoid unrelated churn.

Authoritative source of truth for:
  - Exact package details & specifications
  - Deterministic price & tax calculations
  - Official USSD activation & subscription codes
  - Strict budget-constrained package recommendations
"""
import logging
import re
from typing import Any, Dict, List, Optional, Set

from app.config import settings
from app.tools.get_package_details import get_package_details_tool
from app.tools.get_activation_code import get_activation_code_tool
from app.tools.calculate_price import calculate_price_tool

logger = logging.getLogger("agent.mcp_node")

_TOOL_HANDLERS = {
    "get_package_details": get_package_details_tool,
    "get_activation_code": get_activation_code_tool,
    "calculate_price": calculate_price_tool,
}


def mcp_tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide and execute relevant MCP tools based on user intent, entities, and strategy.
    Injects deterministic, verified facts into context to prevent hallucinations.
    Uses per-request call deduplication to avoid redundant tool executions.
    """
    if not settings.MCP_ENABLED:
        return {
            "mcp_tools_called": [],
            "mcp_tool_results": [],
            "mcp_evidence": [],
        }

    question = state.get("question", "")
    q_lower = question.lower()
    strategy = state.get("strategy", "")
    service = state.get("service", "")
    sub_track = state.get("sub_track", "")
    budget_egp = state.get("budget_egp")
    line_type = state.get("line_type", "mobile_phone")
    entities = state.get("entities", [])
    history = state.get("history", [])

    tools_called: List[str] = list(state.get("mcp_tools_called", []))
    tool_results: List[Dict[str, Any]] = list(state.get("mcp_tool_results", []))
    mcp_evidence: List[Dict[str, Any]] = list(state.get("mcp_evidence", []))
    verified_context_blocks: List[str] = []
    
    allowed_tools: List[str] = state.get("allowed_tools", [
        "get_package_details", "get_activation_code", "calculate_price", "recommend_package"
    ])
    executed_call_keys: Set[str] = set()

    def call_cached(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # Strategy-based tool permission check (Section 17)
        if allowed_tools and tool_name not in allowed_tools:
            logger.warning(f"Tool {tool_name} is not permitted under strategy {strategy} (allowed: {allowed_tools})")
            return {"found": False, "error": f"Tool '{tool_name}' not permitted for strategy '{strategy}'"}

        # Argument validation and normalization (Section 18)
        clean_args = dict(args)
        if "package_name" in clean_args:
            clean_args["package_name"] = str(clean_args["package_name"]).strip()[:100]
        if "budget_egp" in clean_args:
            try:
                clean_args["budget_egp"] = max(0.0, min(100000.0, float(clean_args["budget_egp"])))
            except Exception:
                clean_args["budget_egp"] = 150.0

        key = f"{tool_name}:{sorted(clean_args.items())}"
        if key in executed_call_keys:
            # Find existing result from cache
            for item in tool_results:
                if item.get("tool") == tool_name and item.get("args") == clean_args:
                    return item.get("result", {})
        executed_call_keys.add(key)

        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            res = {"error": f"Tool '{tool_name}' not found.", "found": False}
        else:
            try:
                res = handler(**clean_args)
            except TypeError as te:
                logger.error(f"Invalid arguments for tool '{tool_name}': {te}")
                res = {"error": f"Invalid arguments for tool '{tool_name}': {te}", "found": False}
            except Exception as exc:
                logger.error(f"Exception executing tool '{tool_name}': {exc}", exc_info=True)
                res = {"error": f"Exception executing tool '{tool_name}': {exc}", "found": False}

        if tool_name not in tools_called:
            tools_called.append(tool_name)
        tool_results.append({"tool": tool_name, "args": clean_args, "result": res})
        return res

    needs_clarification = False
    clarification_hint = None

    # ── 1. Category / System Overview Enumeration ────────────────────────────
    cat_keywords = ["الخمسة", "الخمس", "فئات", "أنظمة", "انظمة", "كل الأنظمة", "جميع الأنظمة", "5 categories", "five categories", "all categories"]
    if any(k in question for k in cat_keywords) or any(k in q_lower for k in cat_keywords):
        block = (
            "[MCP Verified e& Egypt Plan Categories Overview]:\n"
            "e& Egypt offers 5 core consumer telecom plan systems:\n"
            "1. Hekaya Mixat (باقات حكاية مكسات): Prepaid monthly bundles using unified 'Mix' units (52, 69, 92, 120, 180, 270) for calls & data, with free family lines and rollover on renewal via *319#.\n"
            "2. Hekaya Internet (باقات حكاية إنترنت): Prepaid mobile internet bundles (46 up to 600 EGP) offering high-speed data from 1,250 MB to 50,000 MB with free streaming perks via *319#.\n"
            "3. Emerald Postpaid (باقات إمرالد الشهرية): Premium postpaid billing plans (Emerald 430, 780, 1120, 1725, 3450) featuring high data quotas, family minutes sharing, roaming passport, and VIP Concierge.\n"
            "4. Simple Prepaid Plans (أنظمة الكارت المدفوع مقدماً): Recharge-based systems including Aqwa Card (8 recharge tiers from 5 to 75 EGP via *811#), Ahlan Pay As You Go per-minute plans (*339#), Daily bundles, and Menu El Geneh (*101#).\n"
            "5. DataLine (باقات داتا لاين): Dedicated data-only SIM packages (1.8 GB to 72 GB, 50 GB, 100 GB) designed exclusively for MiFi routers and 4G USB modems via *130# (does not work on smartphones)."
        )
        verified_context_blocks.append(block)
        mcp_evidence.append({
            "source_type": "mcp",
            "authority": "highest",
            "topic": "categories_overview",
            "data": block
        })

    # ── 2. Exact Package Details & Comparison (Process only actual package entities)
    candidates_to_check: List[str] = list(entities)
    # Extract distinct package names from question
    extracted_pkgs = re.findall(
        r"(?:أقوى\s*كارت|اقوى\s*كارت|aqwa\s*card|حكاية\s*مكسات|hekaya\s*mixat|حكاية\s*إنترنت|حكاية\s*انترنت|hekaya\s*internet|إمرالد|امرالد|emerald|داتا\s*لاين|dataline|سوبر\s*كونكت|super\s*connect)\s*\d+(?:\.\d+)?",
        question,
        re.IGNORECASE,
    )
    for p in extracted_pkgs:
        if p not in candidates_to_check:
            candidates_to_check.append(p)
    
    # Check whole question ONLY if strategy is MCP_EXACT or explicit package inquiry (never for general recommendations)
    if not candidates_to_check and strategy == "MCP_EXACT":
        candidates_to_check.append(question)

    found_packages = []
    for entity in candidates_to_check:
        res = call_cached("get_package_details", {"package_name": entity})
        if res.get("found"):
            pkg_name = res.get("package_name") or entity
            if pkg_name not in found_packages:
                found_packages.append(pkg_name)
                mini_info = f" | Embedded Hekaya Mini: {res.get('has_hekaya_mini')}" if "has_hekaya_mini" in res else ""
                vid_info = f" | Video/Social Minutes: {res.get('video_minutes')} min" if "video_minutes" in res else ""
                valid_info = f" | Validity: {res.get('validity_days')} days" if "validity_days" in res else ""
                
                block = (
                    f"[MCP Verified Package Specs]: {res.get('package_name')} | Pre-tax Price: {res.get('pretax_price_egp')} EGP | "
                    f"Total Recharge: {res.get('total_price_egp')} EGP | Quota/Mixes: {res.get('quota')} | "
                    f"USSD Activation Code: {res.get('activation_code')}{valid_info}{vid_info}{mini_info} | "
                    f"Perks: {res.get('perks')} | Description: {res.get('description')}"
                )
                verified_context_blocks.append(block)
                mcp_evidence.append({
                    "source_type": "mcp",
                    "authority": "highest",
                    "package_name": pkg_name,
                    "pretax_price_egp": res.get("pretax_price_egp"),
                    "total_price_egp": res.get("total_price_egp"),
                    "activation_code": res.get("activation_code"),
                    "quota": res.get("quota"),
                    "details": res,
                })
        else:
            # Check if closest match exists for non-existent package clarification flow (ONLY on exact package queries)
            closest = res.get("closest_match")
            if closest and not found_packages and strategy == "MCP_EXACT":
                needs_clarification = True
                is_ar = any('\u0600' <= c <= '\u06FF' for c in question)
                clarification_hint = (
                    f"مش لاقي {entity}. هل تقصد {closest}؟"
                    if is_ar
                    else f"I could not find {entity}. Did you mean {closest}?"
                )

    # ── 3. USSD Activation Code Lookup ───────────────────────────────────────
    activation_keywords = ["كود", "تفعيل", "اشتراك", "اشترك", "شحن", "تجديد", "ussd", "code", "activate", "activation", "subscribe", "dial"]
    if any(k in q_lower for k in activation_keywords) or strategy == "MCP_ACTIVATION":
        svc_target = service or "Hekaya"
        tier_match = re.findall(r"\d+", question)
        pkg_tier = tier_match[0] if tier_match else None

        res = call_cached("get_activation_code", {"service": svc_target, "package": pkg_tier})
        if res.get("found"):
            block = (
                f"[MCP Verified USSD Code]: Service: {res.get('service')} | Code: {res.get('activation_code')} | "
                f"Instructions: {res.get('instructions')}"
            )
            verified_context_blocks.append(block)
            mcp_evidence.append({
                "source_type": "mcp",
                "authority": "highest",
                "activation_code": res.get("activation_code"),
                "service": res.get("service"),
                "details": res,
            })

    # ── 4. Price & Tax Calculation ───────────────────────────────────────────
    calc_keywords = ["احسب", "حساب", "ضريبة", "شامل الضريبة", "شامل الضريبه", "قبل الضريبة", "المبلغ الاجمالي", "tax", "calculate", "pretax", "inclusive", "recharge amount", "total cost"]
    price_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", question)
    if (any(k in q_lower for k in calc_keywords) or strategy == "MCP_CALCULATION") and price_numbers and not found_packages:
        val = float(price_numbers[0])
        is_tax_inc = any(k in q_lower for k in ["شامل", "شاملة", "inclusive", "معايا", "total"])
        res = call_cached("calculate_price", {"base_price": val, "is_tax_inclusive": is_tax_inc, "tax_type": "prepaid"})
        if res.get("found"):
            block = f"[MCP Verified Price Calculation]: {res.get('breakdown')} | Ar: {res.get('explanation_ar')}"
            verified_context_blocks.append(block)
            mcp_evidence.append({
                "source_type": "mcp",
                "authority": "highest",
                "type": "price_calculation",
                "base_price": val,
                "is_tax_inclusive": is_tax_inc,
                "breakdown": res.get("breakdown"),
                "details": res,
            })

    # ── 5. Package Recommendation (Strict Constraint Filtering & Ranking) ─────
    selected_pkg = None
    rec_validation = None
    if (budget_egp is not None and budget_egp > 0 and not found_packages) or strategy == "MCP_RECOMMENDATION":
        needs_clarification = False
        clarification_hint = None
        from app.tools.recommendation_engine import (
            extract_recommendation_constraints,
            filter_and_rank_candidates,
            validate_candidate_package
        )
        rec_constraints = state.get("recommendation_constraints") or extract_recommendation_constraints(question, state.get("history", []))
        tools_called.append("recommend_package")

        valid_candidates, rejected_candidates = filter_and_rank_candidates(rec_constraints)

        if valid_candidates:
            selected_pkg = valid_candidates[0]
            rec_validation = selected_pkg.get("validation", {})
            tool_results.append({
                "tool": "recommend_package",
                "args": {
                    "budget": rec_constraints.get("budget"),
                    "budget_egp": rec_constraints.get("budget"),
                    "service_type": rec_constraints.get("service_type"),
                    "includes_tax": rec_constraints.get("tax_included", True),
                },
                "result": {"primary_recommendation": selected_pkg, "found": True}
            })
            reason_str = (
                f"Top recommended {rec_constraints.get('service_type', 'telecom')} package matching budget of {rec_constraints.get('budget') or selected_pkg.get('total_price_egp')} EGP "
                f"({selected_pkg.get('quota')}, Total: {selected_pkg.get('total_price_egp')} EGP شامل الضريبة)."
            )
            block = (
                f"[MCP Recommended Package (Constraint Ground Truth)]: {selected_pkg.get('type')} | Pre-tax: {selected_pkg.get('pretax_price_egp')} EGP | "
                f"Total Recharge: {selected_pkg.get('total_price_egp')} EGP | Quota: {selected_pkg.get('quota')} | "
                f"USSD: {selected_pkg.get('activation_code')} | Service Type: {selected_pkg.get('service')} | Reason: {reason_str}"
            )
            verified_context_blocks.append(block)
            mcp_evidence.append({
                "source_type": "mcp",
                "authority": "highest",
                "recommendation": selected_pkg,
                "constraints": rec_constraints,
                "validation": rec_validation,
            })
        else:
            # No valid candidate strictly meeting all constraints
            st = rec_constraints.get("service_type", "telecom")
            b_val = rec_constraints.get("budget", 200)
            service_label = "دقايق ومكالمات" if st == "VOICE" else ("إنترنت" if st == "INTERNET" else "مناسبة")
            block = (
                f"[MCP Recommendation Constraints Report]: No {st} package strictly found under budget {b_val} EGP. "
                f"Rule: Do NOT silently substitute an invalid service type (e.g. never substitute an internet-only package for a voice request). "
                f"Explain clearly that no {service_label} package is available within {b_val} EGP."
            )
            verified_context_blocks.append(block)
            mcp_evidence.append({
                "source_type": "mcp",
                "authority": "highest",
                "topic": "no_matching_candidate",
                "constraints": rec_constraints,
            })

    # ── 6. Context Assembly with MCP Priority Header ─────────────────────────
    existing_context = state.get("context", "")
    if verified_context_blocks:
        mcp_context_header = (
            "=== VERIFIED MCP GROUND TRUTH (HIGHEST AUTHORITY) ===\n"
            "RULE: All facts below are 100% verified ground truth from the official telecom registry.\n"
            "You MUST use these exact numbers, codes, and names. Never contradict or override them.\n\n"
            + "\n\n".join(verified_context_blocks)
            + "\n=== END MCP GROUND TRUTH ===\n\n"
        )
        updated_context = mcp_context_header + existing_context
    else:
        updated_context = existing_context

    trace_step = {
        "node": "mcp_tool",
        "title_ar": "استدعاء أدوات بروتوكول سياق النموذج (MCP)",
        "title_en": "Model Context Protocol (MCP) Tool Invocation",
        "status": "completed",
        "badge": f"🛠️ {len(tools_called)} أدوات منفذة" if tools_called else "🛠️ جاهز",
        "description_ar": (
            f"تم تنفيذ أدوات MCP ({', '.join(tools_called)}) بنجاح وحقن الحقائق المؤكدة والحسابات الدقيقة في سياق الإجابة."
            if tools_called
            else "تم تقييم أدوات MCP واجتياز الفحص المباشر للاسترجاع الهجين."
        ),
        "description_en": (
            f"Executed MCP tools ({', '.join(tools_called)}) and injected deterministic telecom facts into answer context."
            if tools_called
            else "MCP tools evaluated; proceeded with retrieval pipeline."
        ),
        "details": {
            "tools_called": tools_called,
            "tool_results_count": len(tool_results),
            "mcp_enabled": settings.MCP_ENABLED,
            "needs_clarification": needs_clarification,
            "clarification_hint": clarification_hint,
        },
    }

    out = {
        "mcp_tools_called": tools_called,
        "mcp_tool_results": tool_results,
        "mcp_evidence": mcp_evidence,
        "context": updated_context,
        "workflow_trace": [trace_step],
    }
    if needs_clarification:
        out["needs_clarification"] = True
        out["clarification_hint"] = clarification_hint
    return out

