"""
app/tools/recommendation_engine.py
-----------------------------------
Structured recommendation constraint extraction, candidate filtering, ranking,
and post-selection validation for e& Egypt Agentic RAG assistant.

Principle:
A recommendation is correct ONLY if it satisfies the user's explicit constraints:
REAL + RELEVANT TO REQUEST + WITHIN BUDGET + EVIDENCE-BACKED + VALIDATED.
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from app.tools.get_package_details import PACKAGE_REGISTRY
from app.guardrails.security_utils import is_arabic_text


def extract_recommendation_constraints(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Extract structured recommendation constraints from the user question and conversation history.
    Does NOT invent constraints that the user did not specify.
    """
    q = str(question or "").strip()
    q_lower = q.lower()

    # ── 1. Split Primary Request from Explicit Fallback Clauses ───────────────
    fallback_parts = re.split(r"ولو\s*مفيش|لو\s*مفيش|if\s*no\s+voice|if\s*no\s+internet", q, flags=re.IGNORECASE)
    primary_q = fallback_parts[0]
    fallback_q = fallback_parts[1] if len(fallback_parts) > 1 else ""

    # Voice / Minutes keywords
    voice_patterns = [
        r"دقايق", r"دقيقة", r"دقائق", r"مكالمات", r"مكالمة", r"اتصال", r"اتصالات",
        r"voice", r"minute", r"minutes", r"call", r"calls", r"local minutes",
        r"voice package", r"minutes package", r"calls package"
    ]
    # Internet / Data keywords
    net_patterns = [
        r"نت", r"إنترنت", r"انترنت", r"ميجا", r"ميجابايت", r"جيجا", r"جيجابايت",
        r"data", r"internet", r"megabyte", r"gigabyte", r"gb", r"mb",
        r"data package", r"internet package", r"gb package", r"أكبر كمية داتا", r"اكبر كمية داتا", r"اكبر باقة نت", r"أكبر باقة نت"
    ]
    # Mixed keywords
    mixed_patterns = [
        r"دقايق\s*و\s*نت", r"مكالمات\s*و\s*نت", r"نت\s*و\s*دقايق", r"نت\s*و\s*مكالمات",
        r"مكسات", r"ميكسات", r"mixat", r"mixes", r"تجمع\s*الاتنين", r"الاتنين\s*مع\s*بعض",
        r"voice\s*and\s*data", r"calls\s*and\s*internet", r"mixed package"
    ]

    # Voice negation patterns (e.g. "مش فارق معايا المكالمات", "مش عايز دقايق", "no calls")
    neg_voice_patterns = [
        r"مش\s*فارق\s*(?:معايا)?\s*(?:ال)?مكالمات",
        r"مش\s*فارق\s*(?:معايا)?\s*(?:ال)?دقايق",
        r"مش\s*عايز\s*(?:ال)?مكالمات",
        r"مش\s*عايز\s*(?:ال)?دقايق",
        r"مش\s*محتاج\s*(?:ال)?مكالمات",
        r"مش\s*محتاج\s*(?:ال)?دقايق",
        r"بدون\s*(?:ال)?مكالمات",
        r"بدون\s*(?:ال)?دقايق",
        r"من\s*غير\s*(?:ال)?مكالمات",
        r"من\s*غير\s*(?:ال)?دقايق",
        r"no\s+calls?",
        r"no\s+voice",
        r"without\s+calls?",
        r"without\s+voice",
        r"don't\s+need\s+calls?",
        r"don't\s+care\s+about\s+calls?",
    ]
    is_voice_negated = any(re.search(p, primary_q, re.IGNORECASE) for p in neg_voice_patterns)

    # Net negation patterns
    neg_net_patterns = [
        r"مش\s*فارق\s*(?:معايا)?\s*(?:ال)?نت",
        r"مش\s*فارق\s*(?:معايا)?\s*(?:ال)?انترنت",
        r"مش\s*عايز\s*(?:ال)?نت",
        r"مش\s*عايز\s*(?:ال)?انترنت",
        r"مش\s*محتاج\s*(?:ال)?نت",
        r"مش\s*محتاج\s*(?:ال)?انترنت",
        r"بدون\s*(?:ال)?نت",
        r"بدون\s*(?:ال)?انترنت",
        r"من\s*غير\s*(?:ال)?نت",
        r"من\s*غير\s*(?:ال)?انترنت",
        r"no\s+data",
        r"no\s+internet",
        r"without\s+data",
        r"without\s+internet",
        r"don't\s+need\s+internet",
    ]
    is_net_negated = any(re.search(p, primary_q, re.IGNORECASE) for p in neg_net_patterns)

    # Device & MiFi / Router detection
    is_mifi = any(k in q_lower for k in ["mifi", "ماي فاي", "مايفاي", "راوتر", "مودم", "router", "modem", "dataline", "data line", "usb"])
    line_type = "mifi_router" if is_mifi else "mobile_phone"

    is_mixed = any(re.search(p, primary_q, re.IGNORECASE) for p in mixed_patterns)
    has_voice = any(re.search(p, primary_q, re.IGNORECASE) for p in voice_patterns)
    has_net = any(re.search(p, primary_q, re.IGNORECASE) for p in net_patterns)

    if is_mifi:
        service_type = "INTERNET"
    elif is_voice_negated:
        service_type = "INTERNET"
    elif is_net_negated:
        service_type = "VOICE"
    elif is_mixed or (has_voice and has_net):
        service_type = "MIXED"
    elif has_voice:
        service_type = "VOICE"
    elif has_net:
        service_type = "INTERNET"
    else:
        # Check history if turn is a continuation
        hist_service = None
        if history:
            for turn in reversed(history[-4:]):
                t_content = turn.get("content", "")
                if any(re.search(p, t_content, re.IGNORECASE) for p in mixed_patterns):
                    hist_service = "MIXED"
                    break
                elif any(re.search(p, t_content, re.IGNORECASE) for p in voice_patterns):
                    hist_service = "VOICE"
                    break
                elif any(re.search(p, t_content, re.IGNORECASE) for p in net_patterns):
                    hist_service = "INTERNET"
                    break
        service_type = hist_service if hist_service else "UNKNOWN"

    # ── 4. Explicit Fallback Permissions ─────────────────────────────────────
    # NOTE: this used to be computed TWICE — once here using fallback_q (the text
    # after "ولو مفيش"/"لو مفيش"), and then a second, simpler block further down
    # unconditionally overwrote it using only `q` and only ever checking for
    # internet keywords. That silently discarded the VOICE-fallback detection
    # (e.g. "عايز نت، ولو مفيش هات مكالمات" never resolved fallback_categories to
    # ["VOICE"]) every single time. Merged into one correct pass below.
    fallback_allowed = False
    fallback_categories: List[str] = []
    fallback_search_text = fallback_q or q
    if fallback_q or any(k in q for k in ["ولو مفيش", "لو مفيش", "ممكن إنترنت", "ممكن انترنت", "internet is ok", "internet is fine", "ممكن نت"]):
        fallback_allowed = True
        if any(re.search(p, fallback_search_text, re.IGNORECASE) for p in net_patterns):
            fallback_categories.append("INTERNET")
        if any(re.search(p, fallback_search_text, re.IGNORECASE) for p in voice_patterns):
            fallback_categories.append("VOICE")

    # ── 2. Budget and Tax Semantics Extraction ────────────────────────────────
    # A number is a USSD/short-code reference (not a budget) if it is structurally
    # part of one in the text — adjacent to '*'/'#' (e.g. "*130#"), or immediately
    # followed by "code"/"كود" — rather than merely matching a blacklist of specific
    # values. A blacklist silently drops real budgets that happen to equal a known
    # code (e.g. a genuine 130 EGP budget was previously always discarded because
    # *130# is also a real USSD code).
    def _extract_budget(text: str) -> Optional[float]:
        for m in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
            start, end = m.span()
            window = text[max(0, start - 6):min(len(text), end + 6)].lower()
            if "*" in window or "#" in window or "code" in window or "كود" in window:
                continue
            return float(m.group(0))
        return None

    budget: Optional[float] = _extract_budget(q)

    # Inherit budget from history if not present in current question
    if budget is None and history:
        for turn in reversed(history[-4:]):
            budget = _extract_budget(turn.get("content", ""))
            if budget is not None:
                break

    # Budget Type
    if any(k in q for k in ["حد أقصى", "بحد أقصى", "أقل من", "اقل من", "تحت", "max", "maximum", "under", "less than", "up to", "مش أكتر من"]):
        budget_type = "MAX"
    elif any(k in q for k in ["في حدود", "حوالي", "تقريباً", "تقريبا", "around", "about", "approx"]):
        budget_type = "APPROXIMATE"
    elif budget is not None:
        budget_type = "EXACT_OR_STANDARD"
    else:
        budget_type = "UNKNOWN"

    # Tax Semantics
    if any(k in q_lower for k in ["شامل الضريبة", "شامل الضريبه", "شاملة الضريبة", "بعد الضريبة", "including tax", "tax included", "with tax", "total", "معايا"]):
        tax_included = True
    elif any(k in q_lower for k in ["قبل الضريبة", "قبل الضريبه", "بدون ضريبة", "pre-tax", "pretax", "excluding tax", "before tax"]):
        tax_included = False
    else:
        # Standard consumer expectation: prepaid recharges are evaluated against total cash budget
        tax_included = True

    # ── 3. Feature & Quota Minimum Requirements ──────────────────────────────
    min_minutes: Optional[int] = None
    min_match = re.search(r"(\d+)\s*(?:دقيقة|دقايق|دقائق|minute|minutes|min)", q, re.IGNORECASE)
    if min_match:
        min_minutes = int(min_match.group(1))

    min_data: Optional[float] = None
    data_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:جيجا|جيجابايت|gb|giga)", q, re.IGNORECASE)
    if data_match:
        min_data = float(data_match.group(1))

    # (Fallback permissions already computed above — see NOTE.)

    # ── 5. Specific Package Category / Sub-track preference ───────────────────
    package_category = None
    if is_mifi or any(k in q for k in ["داتا لاين", "داتالاين", "dataline"]):
        package_category = "DataLine"
    elif any(k in q for k in ["إمرالد", "امرالد", "اميرالد", "emerald"]):
        package_category = "Emerald"
    elif any(k in q for k in ["حكاية مكسات", "حكاية ميكسات", "mixat"]):
        package_category = "Hekaya Mixat"
    elif any(k in q for k in ["حكاية إنترنت", "حكاية انترنت", "نت حكاية"]):
        package_category = "Hekaya Internet"
    elif any(k in q for k in ["أقوى كارت", "اقوى كارت", "aqwa card"]):
        package_category = "Aqwa Card"

    return {
        "service_type": service_type,
        "line_type": line_type,
        "is_voice_negated": is_voice_negated,
        "budget": budget,
        "budget_type": budget_type,
        "tax_included": tax_included,
        "min_data": min_data,
        "min_minutes": min_minutes,
        "package_category": package_category,
        "fallback_allowed": fallback_allowed,
        "fallback_categories": fallback_categories,
        "explicit_exclusions": [],
    }


def validate_candidate_package(
    candidate: Dict[str, Any],
    constraints: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministically validate a package candidate against user recommendation constraints.
    Returns:
        {
            "valid": bool,
            "violations": List[str],
            "score": float,
            "reason": str
        }
    """
    violations = []
    score = 100.0

    service_type = constraints.get("service_type", "UNKNOWN")
    line_type = constraints.get("line_type", "mobile_phone")
    is_voice_negated = constraints.get("is_voice_negated", False)
    budget = constraints.get("budget")
    budget_type = constraints.get("budget_type", "UNKNOWN")
    tax_included = constraints.get("tax_included", True)
    min_minutes = constraints.get("min_minutes")
    min_data = constraints.get("min_data")
    fallback_allowed = constraints.get("fallback_allowed", False)
    fallback_categories = constraints.get("fallback_categories", [])
    package_category = constraints.get("package_category")

    pkg_svc = candidate.get("service", "").lower()
    pkg_type = candidate.get("type", candidate.get("package_name", ""))
    is_internet_only = ("internet" in pkg_svc or "dataline" in pkg_svc or "super connect" in pkg_svc)
    is_voice_capable = ("mix" in pkg_svc or "aqwa" in pkg_svc or "emerald" in pkg_svc or "ahlan" in pkg_svc)

    # 0. Line Type / Device compatibility (CRITICAL)
    if line_type == "mifi_router":
        if "dataline" not in pkg_svc:
            violations.append("DEVICE_INCOMPATIBLE")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"Device is MiFi / Router, candidate {pkg_type} is for mobile lines.",
            }
    elif line_type == "mobile_phone" and not package_category:
        if "dataline" in pkg_svc:
            violations.append("DEVICE_INCOMPATIBLE")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"Device is Mobile Phone, candidate {pkg_type} is for MiFi/Router only.",
            }

    # 1. Service Type Validation (CRITICAL CONSTRAINT)
    if service_type == "VOICE":
        if is_internet_only:
            if not (fallback_allowed and "INTERNET" in fallback_categories):
                violations.append("SERVICE_TYPE_MISMATCH")
                return {
                    "valid": False,
                    "violations": violations,
                    "score": 0.0,
                    "reason": f"User explicitly requested VOICE/MINUTES package, but candidate {pkg_type} is INTERNET-only.",
                }
            else:
                score -= 30.0  # Fallback penalty
    elif service_type == "INTERNET":
        if is_voice_negated and "mix" in pkg_svc:
            violations.append("VOICE_NOT_WANTED")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"User explicitly does not want voice minutes, candidate {pkg_type} is a voice/mix bundle.",
            }
        elif not is_internet_only and "mix" not in pkg_svc:
            # Previously this always rejected pure-voice candidates for an INTERNET
            # request with no fallback path (the VOICE fallback was only ever
            # honored on the symmetric VOICE branch above). Now a voice-only
            # candidate is allowed through — at a scoring penalty — when the user
            # explicitly said an internet-first request can fall back to voice.
            if not (fallback_allowed and "VOICE" in fallback_categories):
                violations.append("SERVICE_TYPE_MISMATCH")
                return {
                    "valid": False,
                    "violations": violations,
                    "score": 0.0,
                    "reason": f"User explicitly requested INTERNET package, but candidate {pkg_type} is not internet-focused.",
                }
            else:
                score -= 30.0  # Fallback penalty, mirrors the VOICE branch above
    elif service_type == "MIXED":
        if is_internet_only:
            violations.append("SERVICE_TYPE_MISMATCH")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"User requested MIXED (calls + internet) package, but candidate {pkg_type} has no voice minutes.",
            }

    # 2. Package Category Filter (if user specified e.g. Emerald or Hekaya)
    if package_category:
        cat_lower = package_category.lower()
        if cat_lower not in pkg_svc:
            violations.append("CATEGORY_MISMATCH")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"User specifically requested {package_category}, but candidate is {candidate.get('service')}.",
            }

    # 3. Budget Validation
    if budget is not None and budget > 0:
        actual_price = candidate.get("total_price_egp", candidate.get("pretax_price_egp", 0.0)) if tax_included else candidate.get("pretax_price_egp", 0.0)
        
        # Hard cap for MAX budget type
        if budget_type == "MAX" and actual_price > budget:
            violations.append("BUDGET_EXCEEDED")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"Package price ({actual_price} EGP) strictly exceeds max budget ({budget} EGP).",
            }
        elif actual_price > (budget * 1.05):  # 5% margin tolerance for standard budgets
            violations.append("BUDGET_EXCEEDED")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"Package price ({actual_price} EGP) exceeds budget ({budget} EGP).",
            }
        else:
            # Score bonus for filling the budget well without exceeding
            budget_utilization = actual_price / budget
            score += (budget_utilization * 20.0)

    # 4. Minimum Requirements Validation
    if min_minutes is not None:
        cand_minutes = candidate.get("minutes", candidate.get("mixes", 0))
        if cand_minutes < min_minutes:
            violations.append("INSUFFICIENT_MINUTES")
            return {
                "valid": False,
                "violations": violations,
                "score": 0.0,
                "reason": f"Candidate provides {cand_minutes} minutes, but user required minimum {min_minutes}.",
            }

    return {
        "valid": True,
        "violations": [],
        "score": score,
        "reason": "Candidate satisfies all explicit user constraints.",
    }


def filter_and_rank_candidates(
    constraints: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filter all registered packages against constraints and return (valid_ranked_candidates, rejected_candidates).
    Never ranks an invalid candidate above a valid candidate.
    """
    valid_candidates = []
    rejected_candidates = []

    for pkg_key, pkg in PACKAGE_REGISTRY.items():
        candidate_item = dict(pkg)
        candidate_item["key"] = pkg_key
        candidate_item["package_name"] = pkg.get("type", pkg_key)

        val_res = validate_candidate_package(candidate_item, constraints)
        candidate_item["validation"] = val_res

        if val_res["valid"]:
            candidate_item["rank_score"] = val_res["score"]
            valid_candidates.append(candidate_item)
        else:
            rejected_candidates.append(candidate_item)

    # Rank valid candidates by rank_score descending (best budget value & exact match)
    valid_candidates.sort(key=lambda x: x["rank_score"], reverse=True)
    return valid_candidates, rejected_candidates
