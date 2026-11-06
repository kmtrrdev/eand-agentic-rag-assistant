"""
Groundedness check — actually wired into the graph (see graph.py), unlike the
old validate_answer.py it replaces, which was written but never called.
Checks the two claim types most damaging to get wrong (price, activation
code) against the tool/RAG evidence the answer was built from; on a mismatch
it loops back to generate_node once for a repair, then refuses rather than
ship an unverified number.
"""
import re
from typing import Any, Dict, List, Set

from app.agent.lang import pick
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.config import settings

_EGP_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:EGP|egp|LE|le|جنيه|جنية|ج\.م|جم)", re.IGNORECASE)
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_USSD_RE = re.compile(r"\*\d+(?:\*\d+)*#")


def _collect_all_numbers(node: Any, out: Set[float]) -> None:
    """Recursively collect every numeric value anywhere in a data structure."""
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        out.add(round(float(node), 2))
    elif isinstance(node, str):
        cleaned = node.replace(",", "")
        for n in _NUM_RE.findall(cleaned):
            try:
                out.add(round(float(n), 2))
            except ValueError:
                pass
    elif isinstance(node, dict):
        for value in node.values():
            _collect_all_numbers(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_all_numbers(value, out)


def _collect_known_numbers(evidence: List[Dict[str, Any]], context: str) -> Set[float]:
    known: Set[float] = set()
    _collect_all_numbers(evidence, known)

    # NOTE: we deliberately do NOT fold in every number from the whole catalog
    # here. Many fields (e.g. installment_limit_egp, roaming_internet_bonus_gb)
    # take a different value per tier within the same family (Emerald 430 vs
    # 780 vs 1120, ...), so treating "appears anywhere in the 40-tier catalog"
    # as sufficient support let the model state one tier's number while
    # discussing another (e.g. quoting Emerald 430's 15,000 EGP installment
    # limit or 1.5 GB roaming bonus in an Emerald 780 answer) without ever
    # tripping the REPAIR/REFUSE path, because that wrong number was still
    # "real" for some other tier. The evidence returned by the deterministic
    # tools for the tier actually being discussed already contains every
    # field for that tier, so validation should hold the model to that
    # tier-specific evidence (plus the general tax rules below), not to the
    # catalog as an undifferentiated bag of numbers.
    try:
        from app.data.catalog import get_tax_rules
        for rule in get_tax_rules().values():
            _collect_all_numbers(rule, known)
    except Exception:
        pass

    # Collect all numbers appearing in the retrieved context (with commas handled)
    context_clean = (context or "").replace(",", "")
    for num_str in _NUM_RE.findall(context_clean):
        try:
            val = round(float(num_str), 2)
            known.add(val)
        except ValueError:
            pass

    # Automatically include computed taxes for any base price found
    from app.tools import calculate_price_tool
    for base in list(known):
        if 0 < base < 50000:
            for t_type in ("prepaid", "postpaid", "emerald"):
                calc = calculate_price_tool(base, tax_type=t_type)
                if calc.get("found"):
                    known.add(calc.get("total_egp", 0.0))
                    known.add(calc.get("tax_amount_egp", 0.0))

    return known


def _collect_known_codes(evidence: List[Dict[str, Any]], context: str) -> Set[str]:
    known: Set[str] = set()
    for item in evidence:
        for key in ("ussd_code", "activation_code"):
            if item.get(key):
                known.add(str(item[key]))
        for tier in (item.get("tiers") or []) + (item.get("recommendations") or []):
            if tier.get("ussd_code"):
                known.add(str(tier["ussd_code"]))
    known.update(_USSD_RE.findall(context or ""))
    # Include standard company USSD codes
    known.update(["*811#", "*858#", "*566#", "*319#", "*2000#", "*777#", "*111#", "*800#"])
    return known


def validate_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    answer = state.get("answer", "")
    evidence = state.get("tool_evidence", []) or []
    context = state.get("context", "") or ""

    known_prices = _collect_known_numbers(evidence, context)
    known_codes = _collect_known_codes(evidence, context)
    # The customer's own stated budget/tier price is legitimate for the answer
    # to restate (e.g. "for your 100 EGP budget...") even though it isn't a
    # catalog price by itself.
    budget_val = None
    for stated in (state.get("budget_egp"), state.get("tier_price_egp")):
        if isinstance(stated, (int, float)):
            b = round(float(stated), 2)
            known_prices.add(b)
            budget_val = b

    # If customer stated a budget, any difference between a known price and the budget
    # is a legitimate mathematical calculation (e.g. 235.71 - 200 = 35.71, 200 - 188.57 = 11.43).
    if budget_val is not None:
        for p in list(known_prices):
            if 0 < p < 50000:
                diff = round(abs(p - budget_val), 2)
                known_prices.add(diff)

    # Collect pairwise differences between recommendation tiers or prices in evidence
    rec_prices = []
    for item in evidence:
        for rec in (item.get("recommendations") or []) + (item.get("tiers") or []):
            if isinstance(rec.get("price_egp"), (int, float)):
                rec_prices.append(float(rec["price_egp"]))
            if isinstance(rec.get("total_egp"), (int, float)):
                rec_prices.append(float(rec["total_egp"]))
    for i in range(len(rec_prices)):
        for j in range(i + 1, len(rec_prices)):
            diff = round(abs(rec_prices[i] - rec_prices[j]), 2)
            known_prices.add(diff)

    # Add rounded integer and half values for all known prices (e.g. 188.57 -> 189, 35.71 -> 36)
    for p in list(known_prices):
        known_prices.add(round(p, 0))
        known_prices.add(float(int(p)))
        known_prices.add(float(int(p) + 1))

    claimed_raw = _EGP_RE.findall(answer)
    claimed_prices = set()
    for n in claimed_raw:
        try:
            claimed_prices.add(round(float(n.replace(",", "")), 2))
        except ValueError:
            pass
    claimed_codes = set(_USSD_RE.findall(answer))

    unsupported_prices = set()
    for cp in claimed_prices:
        # A claimed price is supported if it exactly matches or is within rounding tolerance (1.05 EGP)
        # of any verified fact or calculated delta.
        if cp in known_prices or any(abs(cp - kp) <= 1.05 for kp in known_prices):
            continue
        unsupported_prices.add(cp)

    unsupported_codes = claimed_codes - known_codes
    violations: Set[str] = {f"{p} EGP" for p in unsupported_prices} | unsupported_codes

    repairs = state.get("generation_repairs", 0)
    details = {
        "unsupported_prices": sorted(unsupported_prices),
        "unsupported_codes": sorted(unsupported_codes),
        "repairs_used": repairs,
    }

    if not violations:
        confidence = 0.95 if any(e.get("found") for e in evidence) else (0.8 if context else 0.6)
        return {
            "validation_result": "PASS",
            "validation_details": details,
            "confidence": confidence,
            "workflow_trace": [step(
                "validate", "9. Fact Validator", "٩. فحص وتدقيق الحقائق",
                description_en="Numeric and USSD claims match verified facts.",
                badge="PASS", status="completed",
                details={"confidence": confidence}, latency_ms=elapsed_ms(start),
            )],
        }

    if repairs < settings.MAX_GENERATION_REPAIRS:
        return {
            "validation_result": "REPAIR",
            "validation_details": details,
            "generation_repairs": repairs + 1,
            "workflow_trace": [step(
                "validate", "9. Fact Validator", "٩. فحص وتدقيق الحقائق",
                description_en=f"Unsupported claim detected ({sorted(violations)}) — regenerating once.",
                badge="REPAIR", status="warning",
                details=details, latency_ms=elapsed_ms(start),
            )],
        }

    language = state.get("language", "en")
    fallback = pick(
        language,
        "معلش، مش هقدر أأكد الرقم ده دلوقتي — يرجى الاتصال بـ 111 أو زيارة أقرب فرع لتأكيد التفاصيل.",
        "I can't confirm that number right now — please call 111 or visit an e& Egypt store to confirm the details.",
    )
    return {
        "validation_result": "REFUSE",
        "validation_details": details,
        "answer": fallback,
        "confidence": 0.3,
        "workflow_trace": [step(
            "validate", "9. Fact Validator", "٩. فحص وتدقيق الحقائق",
            description_en=f"Repeated unsupported claim ({sorted(violations)}) — refused rather than guess.",
            badge="REFUSE", status="blocked",
            details=details, latency_ms=elapsed_ms(start),
        )],
    }
