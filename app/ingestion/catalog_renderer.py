"""
Hierarchical & Semantic RAG Chunking for e& Egypt Telecom Knowledge Base.

Generates multi-level semantic chunks from the validated catalog:
1. Family Portfolio Overview Chunks: Focused bilingual summary tables (split by
   sub-type for large families like Hekaya Internet) — max ~2,000 chars each.
2. Sub-Category / Tier Group Chunks: Logical groupings for targeted sub-category
   queries (monthly vs mini vs extra-units, short vs monthly, MiFi vs add-ons).
3. Contextualized Tier Chunks: Detailed individual package facts enriched with
   parent context.
4. Domain Policy & Feature Chunks: Terms & conditions, shared benefits, roaming,
   out-of-bundle rates, tax formulas, and USSD directory.

Chunking principles applied:
- Each chunk targets 400-2,000 chars to stay within embedding sweet spot.
- Large families (hekaya_internet: 25 tiers) are split into focused sub-overviews
  by tier sub-type (monthly_main / mini / extra_units).
- terms_overview chunks (index-only, no real content) are removed; the actual
  term group chunks carry the searchable content.
- Every family with >4 tiers gets at least one tier_group_chunk for sub-category
  queries (aqwa_card, dataline now covered).
"""
from typing import Any, Dict, List, Tuple

from app.data.catalog import get_catalog, get_tax_rules
from app.ingestion.semantic_chunker import semantic_group

Chunk = Tuple[str, Dict[str, Any]]

_TERMS_SIMILARITY_THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# Tax helper
# ---------------------------------------------------------------------------

def _calc_after_tax(base_price: float, tax_type: str) -> Dict[str, Any]:
    if tax_type in ("postpaid", "emerald"):
        tax_amount = round(base_price * 0.22, 2)
        flat_fee = 10.0
        total = round(base_price + tax_amount + flat_fee, 2)
        desc_en = f"{total} EGP (Base: {base_price} + 22% tax: {tax_amount} + flat fee: 10 EGP)"
        desc_ar = f"{total} جنيه (الأساسي: {base_price} + ضريبة 22%: {tax_amount} + رسوم ثابتة: 10 جنيه)"
    else:
        tax_amount = round(base_price * 0.42857142857, 2)
        total = round(base_price + tax_amount, 2)
        desc_en = f"{total} EGP required recharge ({base_price} listed price + 42.857% recharge tax)"
        desc_ar = f"{total} جنيه شحن مطلوب ({base_price} سعر معلن + 42.857% ضريبة شحن)"
    return {"total_egp": total, "tax_amount_egp": tax_amount, "desc_en": desc_en, "desc_ar": desc_ar}


# ---------------------------------------------------------------------------
# Level 1 — Family Overview Chunk(s)
# ---------------------------------------------------------------------------

def _overview_table_rows(tiers: List[Dict], default_ussd: str = "") -> List[str]:
    """Build compact markdown table rows for a list of tiers (no perks column)."""
    rows = []
    for tier in tiers:
        name = f"{tier['name_en']} ({tier['name_ar']})"
        price = f"{tier['price_egp']} EGP"
        quota = (
            tier.get("quota_label_en")
            or (f"{tier.get('internet_gb', 0)} GB" if "internet_gb" in tier else "Standard")
        )
        validity_days = tier.get("validity_days")
        validity = f"{validity_days}d" if validity_days else "One-time"
        ussd = tier.get("ussd_code") or default_ussd or "N/A"
        rows.append(f"| {name} | {price} | {quota} | {validity} | {ussd} |")
    return rows


def _family_overview_chunk(family: Dict[str, Any]) -> List[Chunk]:
    """Level 1: Family Portfolio Overview -- returns a list because large families
    (hekaya_internet) are split into multiple focused sub-overviews instead of
    one enormous table.
    """
    family_id = family["family"]
    family_en = family["family_name_en"]
    family_ar = family["family_name_ar"]
    source = family.get("source") or family["tiers"][0].get("source", f"{family_en}.pdf")
    tax_type = family.get("tax_type", "prepaid")
    default_ussd = family.get("default_ussd", "")

    header = [
        "| Package (EN / AR) | Price (Pre-tax) | Quota / Content | Validity | Activation USSD |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    tax_note = (
        "Prepaid: recharge requires 42.857% tax."
        if tax_type == "prepaid"
        else "Postpaid: billing adds 22% tax + 10 EGP state fee."
    )

    # -- hekaya_internet: split into 3 focused sub-overviews ------------------
    if family_id == "hekaya_internet":
        monthly_main = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_") and not t["id"].startswith("hekaya_internet_mini") and not t["id"].startswith("hekaya_internet_extra")]
        mini_tiers = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_mini")]
        extra_tiers = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_extra")]

        chunks: List[Chunk] = []

        # Sub-overview A: monthly main plans
        lines_a = [
            f"=== Hekaya Internet -- Monthly Plans Overview ({len(monthly_main)} plans) | نظرة عامة على الباقات الشهرية لحكاية إنترنت ===",
            f"Category: mobile | Tax Type: prepaid | Management: My e& Egypt app or *319#",
            f"Overview: {family.get('family_description_en', '')[:300]}...",
            "",
            "--- MONTHLY PLANS TABLE | جدول الباقات الشهرية ---",
        ] + header + _overview_table_rows(monthly_main, default_ussd) + [
            "",
            "--- KEY RULES ---",
            "- Unused MB converts to e& money cashback (not data rollover).",
            "- On-time renewal earns growing cashback (more consecutive = more cashback).",
            "- Each plan includes 300 call/SMS units + free app selection (1 app on 46/58, 2 on 80-165, 3 on 205-600).",
            "- Starzplay added from 132 EGP; Shahid Mobile on 46-270, Shahid VIP on 345-600.",
            f"- {tax_note}",
        ]
        chunks.append(("\n".join(lines_a), {
            "source": source, "category": family_en,
            "product": "Hekaya Internet Monthly Plans Overview",
            "chunk_type": "family_overview", "family": family_id,
            "chunk_id": f"{family_id}::overview_monthly_main",
            "snippet": f"Overview of all {len(monthly_main)} Hekaya Internet monthly plans (46 to 600 EGP).",
        }))

        # Sub-overview B: mini plans
        lines_b = [
            f"=== Hekaya Internet -- Mini Plans Overview ({len(mini_tiers)} plans) | نظرة عامة على باقات ميني حكاية إنترنت ===",
            "Short-term prepaid data bundles: 1-week, 2-week, and 3-week validity. Activated via *200# or the My e& Egypt app.",
            "",
            "--- MINI PLANS TABLE ---",
        ] + header + _overview_table_rows(mini_tiers) + [
            "",
            "--- KEY RULES ---",
            "- All mini plans activated/renewed via *200# or My e& Egypt app.",
            "- Auto-renews if balance is sufficient.",
            "- Mini plans can be subscribed even with an active Salfa (loan).",
            f"- {tax_note}",
        ]
        chunks.append(("\n".join(lines_b), {
            "source": source, "category": family_en,
            "product": "Hekaya Internet Mini Plans Overview",
            "chunk_type": "family_overview", "family": family_id,
            "chunk_id": f"{family_id}::overview_mini",
            "snippet": f"Overview of {len(mini_tiers)} Hekaya Internet Mini short-term plans (1-week, 2-week, 3-week).",
        }))

        # Sub-overview C: extra unit top-ups
        lines_c = [
            f"=== Hekaya Internet -- Extra Units Top-Ups ({len(extra_tiers)} add-ons) | اضافات وحدات حكاية إنترنت الإضافية ===",
            "Call/SMS-only add-ons -- NO internet included. Activated via *200#.",
            "",
            "--- EXTRA UNITS TABLE ---",
        ] + header + _overview_table_rows(extra_tiers) + [
            "",
            "--- KEY RULES ---",
            "- All extra unit add-ons activated via *200#.",
            "- No internet data included -- call/SMS units only.",
            "- One-time or auto-renewing based on customer choice.",
            f"- {tax_note}",
        ]
        chunks.append(("\n".join(lines_c), {
            "source": source, "category": family_en,
            "product": "Hekaya Internet Extra Units Add-ons Overview",
            "chunk_type": "family_overview", "family": family_id,
            "chunk_id": f"{family_id}::overview_extra_units",
            "snippet": f"Overview of {len(extra_tiers)} Hekaya Internet Extra Units call/SMS-only top-ups (7.5 to 75 EGP).",
        }))

        return chunks

    # -- All other families: single compact overview --------------------------
    lines = [
        f"=== {family_en} Portfolio Overview | نظرة عامة على باقات {family_ar} ===",
        f"Category: {family.get('category', 'telecom')} | Tax Type: {tax_type}",
        f"Default Activation / Management: {default_ussd}",
        f"Overview (EN): {family.get('family_description_en', '')}",
        f"Overview (AR): {family.get('family_description_ar', '')}",
        "",
        "--- COMPLETE TIERS TABLE | جدول جميع الباقات المتاحة ---",
    ] + header + _overview_table_rows(family["tiers"], default_ussd) + [
        "",
        "--- SUMMARY & BUSINESS RULES ---",
    ]

    if family_id == "hekaya_mixat":
        lines.extend([
            "- Units Rollover: Unused Mix units roll over automatically upon on-time renewal.",
            "- Renewal Coins: Each tier awards Coins on renewal (e.g. 104 to 540 Coins).",
            "- Family Lines: Tiers 92 (1 line), 120 (1 line), 180 (2 lines), 270 (3 lines). Allocated as 10%, 25%, or 50% of the primary bundle.",
            "- Home Internet Exchange: Tiers 180 and 270 can exchange Mixes for Home Internet (100 GB for 5,800 mixes; 150 GB for 7,000 mixes).",
        ])
    elif family_id == "aqwa_card":
        lines.extend([
            "- Flexible Unit Allocation: Units can be split between minutes and mobile internet.",
            "- Video & Streaming Minutes: Available on select recharge tiers (10, 15, etc.).",
            "- Short Validity options (2 days, 3 days, 7 days, up to monthly).",
        ])
    elif family_id == "dataline":
        lines.extend([
            "- Data-only SIM for MiFi routers, portable modems, and USB dongles.",
            "- Managed via *130#.",
            "- Double package promotion available on first recharge for selected tiers.",
        ])
    elif family_id == "emerald":
        lines.extend([
            "- Premium Postpaid Program: Subscribed via customer service 111 or e& Egypt retail stores.",
            "- Includes Free Family Lines with 10,000 free intra-family minutes.",
            "- Entertainment E-Coins, Roaming minutes/internet, and Home DSL discounts included.",
        ])
    elif family_id == "super_connect":
        lines.extend([
            "- Mobile add-on bundle for additional high-speed data.",
            "- Activated via *566#.",
        ])
    elif family_id == "daily_addons":
        lines.extend([
            "- Short-term daily/weekly bundles for mix units, internet, or minutes.",
            "- Activated via *972#, *973#, *101#, or *626#.",
        ])

    lines.append(f"- Tax Note: {tax_note}")

    metadata = {
        "source": source,
        "category": family_en,
        "product": f"{family_en} Portfolio Overview",
        "chunk_type": "family_overview",
        "family": family_id,
        "chunk_id": f"{family_id}::overview",
        "snippet": f"Complete table and rules for all {len(family['tiers'])} {family_en} packages.",
    }
    return [("\n".join(lines), metadata)]


# ---------------------------------------------------------------------------
# Level 2 -- Tier Group Chunks
# ---------------------------------------------------------------------------

def _tier_group_chunks(family: Dict[str, Any]) -> List[Chunk]:
    """Level 2: Sub-category group chunks for families with distinct subsets."""
    family_id = family["family"]
    family_en = family["family_name_en"]
    source = family.get("source") or family["tiers"][0].get("source", f"{family_en}.pdf")
    chunks: List[Chunk] = []

    # -- hekaya_mixat ----------------------------------------------------------
    if family_id == "hekaya_mixat":
        entry_tiers = [t for t in family["tiers"] if t["price_egp"] in (52, 69)]
        family_tiers = [t for t in family["tiers"] if t["price_egp"] in (92, 120, 180, 270)]

        lines_a = [
            "=== Hekaya Mixat Single-User Entry Bundles (52 & 69 EGP) | باقات حكاية مكسات الفردية ===",
            "Suitable for individual users without family lines.",
        ]
        for t in entry_tiers:
            lines_a.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en', '')}, Code: {t.get('ussd_code', '')}, Coins: {t.get('coins_on_renewal', '')}. {t.get('description_ar', '')}")
        chunks.append(("\n".join(lines_a), {
            "source": source, "category": family_en, "product": "Hekaya Mixat Entry Tiers (52, 69)",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_entry",
            "snippet": "Hekaya Mixat 52 and 69 single-user individual monthly packages.",
        }))

        lines_b = [
            "=== Hekaya Mixat Family Sharing & Home Internet Bundles (92, 120, 180, 270 EGP) | باقات حكاية مكسات للعائلة ===",
            "Includes extra family lines (1 to 3 lines) and Home Internet exchange eligibility for higher tiers.",
        ]
        for t in family_tiers:
            lines_b.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en', '')}, Family Lines: {t.get('family_lines', 0)}, Code: {t.get('ussd_code', '')}. {t.get('description_ar', '')}")
        chunks.append(("\n".join(lines_b), {
            "source": source, "category": family_en, "product": "Hekaya Mixat Family & Heavy Tiers (92-270)",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_family",
            "snippet": "Hekaya Mixat 92, 120, 180, 270 with family sharing lines and home internet exchange.",
        }))

    # -- hekaya_internet -------------------------------------------------------
    elif family_id == "hekaya_internet":
        monthly_main = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_") and not t["id"].startswith("hekaya_internet_mini") and not t["id"].startswith("hekaya_internet_extra")]
        mini_tiers = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_mini")]
        extra_tiers = [t for t in family["tiers"] if t["id"].startswith("hekaya_internet_extra")]

        # Group A: monthly main — split budget vs premium
        budget = [t for t in monthly_main if t["price_egp"] < 100]
        high = [t for t in monthly_main if t["price_egp"] >= 100]

        lines_budget = [
            "=== Hekaya Internet Budget Monthly Plans (46-80 EGP) | باقات حكاية إنترنت الشهرية الاقتصادية ===",
            "Low-cost monthly mobile internet plans: 1,250 MB to 3,250 MB, 30-day validity.",
            "All include 300 call/SMS units + 1-2 selected apps + Twist Sport/Music/TV + Shahid Mobile.",
        ]
        for t in budget:
            lines_budget.append(f"- {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}, Code: {t.get('ussd_code','')}")
        chunks.append(("\n".join(lines_budget), {
            "source": source, "category": family_en, "product": "Hekaya Internet Budget Monthly (46-80 EGP)",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_budget_monthly",
            "snippet": "Hekaya Internet budget monthly plans: 46, 58, 80 EGP. 1,250 MB to 3,250 MB.",
        }))

        lines_high = [
            "=== Hekaya Internet Premium Monthly Plans (105-600 EGP) | باقات حكاية إنترنت الشهرية الكبيرة ===",
            "High-quota monthly mobile internet plans: 4,750 MB (4.75 GB) to 50,000 MB (50 GB).",
            "All include 300 call/SMS units + 2-3 selected apps + Twist + Starzplay (from 132 EGP) + Shahid.",
        ]
        for t in high:
            lines_high.append(f"- {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}, Code: {t.get('ussd_code','')}")
        chunks.append(("\n".join(lines_high), {
            "source": source, "category": family_en, "product": "Hekaya Internet Premium Monthly (105-600 EGP)",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_premium_monthly",
            "snippet": "Hekaya Internet premium monthly plans: 105 to 600 EGP. 4.75 GB to 50 GB with Shahid VIP.",
        }))

        # Group B: mini plans by validity window
        one_week = [t for t in mini_tiers if t.get("validity_days") == 7]
        two_week = [t for t in mini_tiers if t.get("validity_days") == 14]
        three_week = [t for t in mini_tiers if t.get("validity_days") == 21]

        lines_mini = [
            "=== Hekaya Internet Mini Plans (Short-term: 1-week / 2-week / 3-week) | باقات ميني حكاية إنترنت ===",
            "Short-term prepaid data bundles. Activated via *200# or the My e& Egypt app. Auto-renews if balance sufficient.",
            "",
            "[ 1-WEEK PLANS ]",
        ]
        for t in one_week:
            lines_mini.append(f"  - {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}")
        lines_mini.append("[ 2-WEEK PLANS ]")
        for t in two_week:
            lines_mini.append(f"  - {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}")
        lines_mini.append("[ 3-WEEK PLANS ]")
        for t in three_week:
            lines_mini.append(f"  - {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}")
        chunks.append(("\n".join(lines_mini), {
            "source": source, "category": family_en, "product": "Hekaya Internet Mini Plans (1w/2w/3w)",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_mini",
            "snippet": f"Hekaya Internet {len(mini_tiers)} mini short-term plans (1-week, 2-week, 3-week). Activated via *200#.",
        }))

        # Group C: extra unit top-ups
        lines_extra = [
            "=== Hekaya Internet Extra Units Top-Ups (Call/SMS add-ons) | اضافات وحدات حكاية إنترنت ===",
            "Call/SMS-only add-ons -- NO internet data included. Activated via *200#.",
        ]
        for t in extra_tiers:
            lines_extra.append(f"- {t['name_en']}: {t['price_egp']} EGP, {t.get('quota_label_en','')}")
        chunks.append(("\n".join(lines_extra), {
            "source": source, "category": family_en, "product": "Hekaya Internet Extra Units Top-Ups",
            "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_extra_units",
            "snippet": "Hekaya Internet Extra Units call/SMS-only top-ups: 200, 650, 1400, 3000 units. No internet data.",
        }))

    # -- aqwa_card -------------------------------------------------------------
    elif family_id == "aqwa_card":
        short_tiers = [t for t in family["tiers"] if t.get("validity_days") and t["validity_days"] <= 7]
        monthly_tiers = [t for t in family["tiers"] if t.get("validity_days") and t["validity_days"] == 30]
        other_tiers = [t for t in family["tiers"] if t not in short_tiers and t not in monthly_tiers]

        if short_tiers:
            lines_short = [
                "=== Aqwa Card Short-Validity Recharge Plans (2-day, 3-day, 7-day) | اقوى كارت -- الباقات قصيرة الصلاحية ===",
                "Flexible short-term recharge options. Units split between calls and internet. Activated via *811#.",
            ]
            for t in short_tiers:
                validity = t.get("validity_days", "?")
                lines_short.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en','')}, {validity}d validity, Code: {t.get('ussd_code','*811#')}")
            chunks.append(("\n".join(lines_short), {
                "source": source, "category": family_en, "product": "Aqwa Card Short-Validity Plans",
                "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_short",
                "snippet": "Aqwa Card short-validity recharge plans: 2-day, 3-day, and 7-day options.",
            }))

        if monthly_tiers:
            lines_monthly = [
                "=== Aqwa Card Monthly Recharge Plans (30-day) | اقوى كارت -- الباقات الشهرية ===",
                "Monthly recharge bundles with call/internet units. Activated via *811#.",
            ]
            for t in monthly_tiers:
                lines_monthly.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en','')}, Code: {t.get('ussd_code','*811#')}")
            chunks.append(("\n".join(lines_monthly), {
                "source": source, "category": family_en, "product": "Aqwa Card Monthly Plans",
                "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_monthly",
                "snippet": "Aqwa Card monthly 30-day recharge plans.",
            }))

        if other_tiers:
            lines_other = [
                "=== Aqwa Card Other / Special Plans | اقوى كارت -- الباقات الاخرى ===",
            ]
            for t in other_tiers:
                lines_other.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en','')}, Code: {t.get('ussd_code','*811#')}")
            chunks.append(("\n".join(lines_other), {
                "source": source, "category": family_en, "product": "Aqwa Card Special Plans",
                "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_other",
                "snippet": "Aqwa Card special or variable-validity plans.",
            }))

    # -- dataline --------------------------------------------------------------
    elif family_id == "dataline":
        addon_tiers = [t for t in family["tiers"] if "addon" in t["id"].lower() or "add_on" in t["id"].lower()]
        device_tiers = [t for t in family["tiers"] if t not in addon_tiers]

        if device_tiers:
            lines_device = [
                "=== DataLine MiFi / Router / USB Modem Plans | داتا لاين -- باقات راوتر وUSB ===",
                "Data-only SIM plans for MiFi routers, portable modems, and USB dongles. Managed via *130#.",
            ]
            for t in device_tiers:
                lines_device.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en','')}, Validity: {t.get('validity_days','?')}d, Code: {t.get('ussd_code','*130#')}")
            chunks.append(("\n".join(lines_device), {
                "source": source, "category": family_en, "product": "DataLine Device Plans (MiFi/USB)",
                "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_device",
                "snippet": "DataLine MiFi, router, and USB modem data-only SIM plans. Managed via *130#.",
            }))

        if addon_tiers:
            lines_addon = [
                "=== DataLine Add-on Bundles | داتا لاين -- الباقات الإضافية ===",
                "SMS-ordered add-on data bundles for DataLine SIMs. Added via SMS to 138.",
            ]
            for t in addon_tiers:
                lines_addon.append(f"- {t['name_en']} ({t['name_ar']}): {t['price_egp']} EGP, {t.get('quota_label_en','')}")
            chunks.append(("\n".join(lines_addon), {
                "source": source, "category": family_en, "product": "DataLine Add-on Bundles",
                "chunk_type": "tier_group", "family": family_id, "chunk_id": f"{family_id}::group_addons",
                "snippet": "DataLine SMS add-on data bundles for existing DataLine SIM customers.",
            }))

    return chunks


# ---------------------------------------------------------------------------
# Level 3 -- Individual Tier Chunks
# ---------------------------------------------------------------------------

def _tier_chunk(family: Dict[str, Any], tier: Dict[str, Any]) -> Chunk:
    """Level 3: Comprehensive, self-contained single tier chunk with dynamic
    plan type tagging, usage classification, and search keyword enrichment."""
    tax_type = tier.get("tax_type") or family.get("tax_type", "prepaid")
    tax_info = _calc_after_tax(tier["price_egp"], tax_type)

    tier_id = str(tier.get("id", "")).lower()
    family_id = family["family"]
    is_addon = (
        family_id == "daily_addons"
        or "extra" in tier_id
        or "addon" in tier_id
        or "extra" in str(tier.get("name_en", "")).lower()
    )

    if is_addon:
        plan_type_en = "Add-on Top-up (Requires active main package)"
        plan_type_ar = "باقة إضافية / شحنة إضافية (تتطلب وجود باقة أساسية مسبقاً وليست باقة مستقلة)"
        chunk_type = "addon_tier"
    elif tier.get("validity_days") and tier["validity_days"] <= 7:
        plan_type_en = "Short-term Flexible Bundle"
        plan_type_ar = "باقة قصيرة المدة (شحنة مرنة)"
        chunk_type = "package_tier"
    else:
        plan_type_en = "Primary Monthly Package"
        plan_type_ar = "باقة شهرية أساسية"
        chunk_type = "package_tier"

    # Usage focus
    if family_id == "hekaya_mixat":
        usage_en = "Voice Calls & Minutes Heavy (Flexible Mix units for calls and data)"
        usage_ar = "تركيز مكالمات ودقائق (وحدات مكس مرنة للمكالمات والنت)"
    elif family_id == "aqwa_card":
        usage_en = "Calls and Internet Flexible Recharge"
        usage_ar = "شحن رصيد مرن للمكالمات والإنترنت"
    elif family_id == "hekaya_internet":
        if is_addon:
            usage_en = "Voice & SMS Top-up Add-on Only (NO internet data included)"
            usage_ar = "إضافة وحدات مكالمات ورسائل فقط (بدون إنترنت)"
        else:
            usage_en = "High-Speed Mobile Internet Heavy (Data priority, 300 call units)"
            usage_ar = "تركيز إنترنت وميجابايت عالي السرعة (مع 300 وحدة مكالمات)"
    elif family_id == "emerald":
        usage_en = "Premium Postpaid All-Inclusive (Calls, high data, roaming, family lines)"
        usage_ar = "باقة خط فاتورة مميزة شاملة (مكالمات وإنترنت ورومنج وعائلة)"
    elif family_id == "dataline":
        usage_en = "Data-Only SIM for MiFi Routers & Modems (NO voice calls)"
        usage_ar = "شريحة بيانات فقط لأجهزة الراوتر والـ MiFi (بدون مكالمات صوتية)"
    else:
        usage_en = "General Telecom"
        usage_ar = "خدمات اتصالات عامة"

    lines = [
        f"=== [{plan_type_en}] {tier['name_en']} | {tier['name_ar']} ===",
        f"Package Classification: {plan_type_en} | {plan_type_ar}",
        f"Target Usage Focus: {usage_en} | {usage_ar}",
        f"Product Line: {family['family_name_en']} ({family['family_name_ar']})",
        f"Listed Price (Pre-tax): {tier['price_egp']} EGP",
        f"After-Tax Estimated Total: {tax_info['desc_en']} | {tax_info['desc_ar']}",
    ]

    if is_addon:
        lines.append("⚠️ تنبيه هام: هذه باقة إضافية لتزويد الرصيد لعملاء الباقات الحاليين وليست باقة شهرية أساسية!")

    if tier.get("ussd_code"):
        lines.append(f"Activation / Renewal USSD Code: {tier['ussd_code']}")

    if tier.get("quota_label_en"):
        lines.append(f"Quota: {tier['quota_label_en']} | {tier.get('quota_label_ar', '')}")
    elif "internet_gb" in tier:
        lines.append(f"Internet Quota: {tier['internet_gb']} GB | {tier['internet_gb']} جيجابايت")

    if tier.get("validity_days"):
        lines.append(f"Validity: {tier['validity_days']} days | صلاحية {tier['validity_days']} يوم")

    if tier.get("family_lines") is not None:
        lines.append(f"Family Lines: {tier['family_lines']} extra line(s) ({tier.get('family_lines_note_en', '')} | {tier.get('family_lines_note_ar', '')})")

    if tier.get("coins_on_renewal"):
        lines.append(f"Renewal Coins: {tier['coins_on_renewal']} Coins")

    lines.append(f"Description (EN): {tier.get('description_en', '')}")
    lines.append(f"Description (AR): {tier.get('description_ar', '')}")

    if tier.get("perks_en"):
        lines.append(f"Perks & Special Features: {tier['perks_en']} | {tier.get('perks_ar', '')}")

    search_keywords = [
        tier['name_en'],
        tier['name_ar'],
        f"{tier['price_egp']} EGP",
        f"{tier['price_egp']} جنيه",
        f"باقة بـ {tier['price_egp']}",
        f"باقة ب {tier['price_egp']}",
        f"ميزانية {round(tax_info['total_egp'])}",
        f"شحن {round(tax_info['total_egp'])} جنيه",
    ]
    if family_id == "hekaya_mixat":
        search_keywords.extend(["مكالمات", "دقايق", "دقائق", "مكسات", "باقة مكالمات", "calls", "minutes", "voice"])
    elif family_id == "hekaya_internet":
        if is_addon:
            search_keywords.extend(["إضافة مكالمات", "شحنة إضافية", "تزويد رصيد", "extra units", "add-on top-up"])
        else:
            search_keywords.extend(["إنترنت", "نت", "ميجابايت", "جيجابايت", "باقة نت", "internet", "data", "MB"])

    lines.append("Search Synonyms & Matching Terms: " + ", ".join(search_keywords))

    source = tier.get("source") or family.get("source", f"{family['family_name_en']}.pdf")
    lines.append(f"Official Source Document: {source}")

    metadata = {
        "source": source,
        "category": family["family_name_en"],
        "product": tier["name_en"],
        "chunk_type": chunk_type,
        "is_addon": is_addon,
        "family": family["family"],
        "tier_id": tier["id"],
        "chunk_id": f"{family['family']}::{tier['id']}",
        "snippet": f"[{plan_type_en}] {tier['name_en']} ({tier['name_ar']}) -- {tier['price_egp']} EGP, {tier.get('quota_label_en') or tier.get('description_en', '')[:100]}",
    }
    return "\n".join(lines), metadata


# ---------------------------------------------------------------------------
# Level 4 -- Terms & Glossary Chunks (terms_overview REMOVED)
# ---------------------------------------------------------------------------

def _terms_chunks(family: Dict[str, Any]) -> List[Chunk]:
    """Family-wide rules/terms -- semantically grouped into searchable chunks.

    NOTE: The redundant 'terms_overview' chunk (which only listed topic headings
    without actual content) has been removed. The grouped term chunks below carry
    all the real searchable content.
    """
    family_id = family["family"]
    family_en = family["family_name_en"]
    source = family.get("source") or family["tiers"][0].get("source", f"{family_en}.pdf")
    terms = family.get("terms_and_conditions") or []
    if not terms:
        return []

    chunks: List[Chunk] = []
    term_groups = semantic_group(terms, text_fn=lambda t: t["en"], similarity_threshold=_TERMS_SIMILARITY_THRESHOLD)
    for idx, group in enumerate(term_groups, 1):
        text = (
            f"=== {family_en} Terms & Conditions | شروط وأحكام {family['family_name_ar']} ===\n"
            + "\n".join(f"- EN: {t['en']}\n  AR: {t['ar']}" for t in group)
        )
        chunks.append((text, {
            "source": source, "category": family_en, "product": f"Terms & Conditions Part {idx}",
            "chunk_type": f"{family_id}_terms", "family": family_id,
            "chunk_id": f"{family_id}_terms_{idx}",
            "snippet": group[0]["en"][:220],
        }))

    return chunks


def _glossary_chunks(family: Dict[str, Any]) -> List[Chunk]:
    """Glossary term definitions for any family that defines a 'glossary' list."""
    family_id = family["family"]
    family_en = family["family_name_en"]
    source = family.get("source") or family["tiers"][0].get("source", f"{family_en}.pdf")
    chunks: List[Chunk] = []
    for term in family.get("glossary") or []:
        text = (
            f"=== {family_en} Glossary: {term['term_en']} | {term['term_ar']} ===\n"
            f"EN: {term.get('definition_en', '')}\n"
            f"AR: {term.get('definition_ar', '')}"
        )
        chunks.append((text, {
            "source": source, "category": family_en, "product": term["term_en"],
            "chunk_type": f"{family_id}_glossary", "family": family_id,
            "chunk_id": f"{family_id}_glossary_{term['term_en']}",
            "snippet": (term.get("definition_en") or "")[:220],
        }))
    return chunks


# ---------------------------------------------------------------------------
# Emerald-specific extra chunks
# ---------------------------------------------------------------------------

def _emerald_extra_chunks(family: Dict[str, Any]) -> List[Chunk]:
    """Emerald-specific content: shared benefits, out-of-bundle rates, roaming."""
    chunks: List[Chunk] = []
    source = "Emerald (2).pdf"

    for key, benefit in (family.get("shared_benefits") or {}).items():
        text = (
            f"=== Emerald Shared Benefit: {benefit['name_en']} | {benefit['name_ar']} ===\n"
            f"Applies across all Emerald tiers.\n"
            f"EN: {benefit.get('description_en', '')}\n"
            f"AR: {benefit.get('description_ar', '')}"
        )
        chunks.append((text, {
            "source": source, "category": "Emerald", "product": benefit["name_en"],
            "chunk_type": "emerald_benefit", "family": "emerald",
            "chunk_id": f"emerald_benefit_{key}",
            "snippet": (benefit.get("description_en") or "")[:220],
        }))

    out_of_bundle = family.get("out_of_bundle_rates") or {}
    if out_of_bundle:
        text = (
            "=== Emerald Out-of-Bundle Usage Rates | اسعار تجاوز باقة إمرالد ===\n"
            f"EN: {out_of_bundle.get('description_en', '')}\n"
            f"AR: {out_of_bundle.get('description_ar', '')}"
        )
        chunks.append((text, {
            "source": source, "category": "Emerald", "product": "Out-of-Bundle Rates",
            "chunk_type": "emerald_rates", "family": "emerald",
            "chunk_id": "emerald_rates",
            "snippet": (out_of_bundle.get("description_en") or "")[:220],
        }))

    countries = family.get("roaming_countries_70") or []
    if countries:
        text = (
            "=== Emerald Approved Roaming Countries (70 Countries) | دول الرومنج المعتمدة لإمرالد ===\n"
            "Approved destination countries for Emerald roaming minutes and internet abroad:\n"
            "EN: " + ", ".join(countries) + "\n"
            "AR: هذه هي الدول المعتمدة كوجهات يمكن لعملاء إمرالد استخدام دقائق وإنترنت الرومنج فيها اثناء السفر."
        )
        chunks.append((text, {
            "source": source, "category": "Emerald", "product": "Approved Roaming Countries",
            "chunk_type": "emerald_roaming", "family": "emerald",
            "chunk_id": "emerald_roaming",
            "snippet": f"70 approved roaming countries for Emerald packages: {', '.join(countries[:10])}...",
        }))

    return chunks


# ---------------------------------------------------------------------------
# Domain Policy Chunks
# ---------------------------------------------------------------------------

def _policy_chunks() -> List[Chunk]:
    """Domain-level policy chunks: Tax calculation formulas and USSD directory."""
    tax_rules = get_tax_rules()
    tax_text = (
        "=== e& Egypt Telecom Tax & Fee Calculation Guide | دليل حساب الضرائب والرسوم ===\n"
        "1. Prepaid Recharge Tax (باقات الدفع المسبق):\n"
        f"   - Rate: {tax_rules.get('prepaid', {}).get('description_en', '42.857% recharge tax')}\n"
        f"   - Arabic: {tax_rules.get('prepaid', {}).get('description_ar', '')}\n"
        "   - Formula: Total Recharge Needed = Base Package Price * 1.42857\n"
        "   - Applies to: Hekaya Mixat, Hekaya Internet, Aqwa Card, Super Connect, DataLine, Daily Bundles.\n\n"
        "2. Postpaid & Emerald Tax (باقات الفاتورة وإمرالد):\n"
        f"   - Rate: {tax_rules.get('postpaid', {}).get('description_en', '22% tax + 10 EGP fee')}\n"
        f"   - Arabic: {tax_rules.get('postpaid', {}).get('description_ar', '')}\n"
        "   - Formula: Total Bill = Base Price + (Base Price * 0.22) + 10 EGP flat fee.\n"
        "   - Breakdown: 8% Schedule Tax + 14% VAT + 10 EGP State Resource Development Fee."
    )
    tax_chunk = (tax_text, {
        "source": "Emerald (2).pdf", "category": "Tax & Fees", "product": "Tax Calculation Guide",
        "chunk_type": "tax_rules", "family": "tax_rules", "chunk_id": "tax_calculation_guide",
        "snippet": "Official tax math for e& Egypt: Prepaid (42.857%) vs Postpaid/Emerald (22% + 10 EGP fee).",
    })

    ussd_text = (
        "=== e& Egypt Universal USSD Activation & Management Directory | دليل اكواد اتصالات مصر ===\n"
        "- Hekaya Mixat (حكاية مكسات): *319# (Tier specific: *319*45# for 52, *319*60# for 69, *319*80# for 92, *319*105# for 120, *319*155# for 180, *319*235# for 235).\n"
        "- Hekaya Mini Recharge, standalone (شحنة حكاية ميني مستقلة): *556*9*RechargeCode# to recharge, *319# to renew -- distinct from the Aqwa Card-embedded Hekaya Mini, which uses *811#.\n"
        "- Hekaya Internet monthly plans (حكاية إنترنت): managed via the My e& Egypt app per the current source PDF; the *319*<code># per-tier codes listed on each tier are existing catalog entries not corroborated by that PDF. Hekaya Internet Mini plans and Extra Unit top-ups: *200#.\n"
        "- Aqwa Card (اقوى كارت): *811#.\n"
        "- DataLine MiFi / USB (داتا لاين): *130# (or send 1 in an SMS to 130, or the My e& Egypt app); add-ons via SMS to 138.\n"
        "- Super Connect Mobile Add-on (سوبر كونكت): *566#.\n"
        "- Daily Bundles (الباقات اليومية): *972# (55 mixes for 1.5 EGP), *973# (120 mixes for 2.5 EGP).\n"
        "- Menu El Geneh micro-bundles (منيو الجنيه): *101#.\n"
        "- Ahlan Pay As You Go plans (اهلاً): *339# to migrate/manage, *3333# for promotions/balance/migration, voice service 5250.\n"
        "- Hekaya Extra Top-up Add-ons: *626#.\n"
        "- Emerald Postpaid (إمرالد): Call 111 or visit an e& Egypt retail store (no USSD self-activation); *800# to manage an existing Emerald account.\n"
        "- Hekaya Mixat general codes: *807# (early renewal), *809# (weekly renewal), *011# (best-plan discovery), *304# (international calling), *3333# (promotions/balance/migration), *808# (check internet usage), *806# (minute cap management).\n"
        "- Customer Support: 111."
    )
    ussd_chunk = (ussd_text, {
        "source": "PrepaidSystems.pdf", "category": "USSD Directory", "product": "USSD Codes Directory",
        "chunk_type": "ussd_directory", "family": "ussd_directory", "chunk_id": "ussd_directory",
        "snippet": "Complete directory of e& Egypt activation and renewal USSD codes.",
    })

    return [tax_chunk, ussd_chunk]


# ---------------------------------------------------------------------------
# Dynamic Cross-Family Budget Bracket Chunks
# ---------------------------------------------------------------------------

def _dynamic_budget_chunks() -> List[Chunk]:
    """Dynamic cross-family recommendation chunks grouped by customer budget brackets."""
    chunks: List[Chunk] = []

    # Bracket 1: 100 to 200 EGP (Medium Budget / High Popularity)
    text_100_200 = (
        "=== Cross-Family Plan Comparison: 100 to 200 EGP Budget | باقات اتصالات مصر لميزانية 100 إلى 200 جنيه ===\n"
        "Comparison of primary monthly packages for customers with a budget around 100 to 200 EGP:\n\n"
        "1. FOR USERS WHO USE MINUTES / CALLS MORE (بستخدم مكالمات ودقائق ومكسات أكتر):\n"
        "   - Hekaya Mixat 120 (حكاية مكسات 120) [RECOMMENDED CHOICE FOR ~200 EGP BUDGET]:\n"
        "     * Listed Price: 120 EGP (Required recharge with 42.857% tax: 171.43 EGP — strictly fits inside 200 EGP budget!).\n"
        "     * Quota: 5,375 Mix units for calls to all networks and internet.\n"
        "     * Perks: 1 extra family line, 2 favorite numbers (0.5 mix/min), unlimited Facebook & WhatsApp throughout validity, VIU + Twist + Starzplay + Shahid Mobile.\n"
        "     * Activation Code: *319*105#.\n"
        "     * Note: This is a standalone primary monthly plan, NOT an add-on.\n\n"
        "   - Hekaya Mixat 92 (حكاية مكسات 92):\n"
        "     * Listed Price: 92 EGP (Required recharge: 131.43 EGP).\n"
        "     * Quota: 3,750 Mix units, 1 family line, 2 favorite numbers. USSD: *319*80#.\n\n"
        "   - Hekaya Mixat 180 (حكاية مكسات 180):\n"
        "     * Listed Price: 180 EGP (Required recharge: 257.14 EGP).\n"
        "     * Quota: 9,350 Mix units, 2 family lines, 3 favorite numbers. USSD: *319*155#.\n\n"
        "2. FOR USERS WHO USE INTERNET / DATA MORE (بستخدم إنترنت وبيانات وميجابايت أكتر):\n"
        "   - Hekaya Internet 105 (حكاية إنترنت 105): 105 EGP pre-tax (150 EGP recharge), 4,750 MB + 300 call units. USSD: *319#.\n"
        "   - Hekaya Internet 132 (حكاية إنترنت 132): 132 EGP pre-tax (188.57 EGP recharge), 6,750 MB + 300 call units. USSD: *319*132#.\n\n"
        "3. IMPORTANT DISTINCTION: Primary Plans vs Add-ons (الباقات الأساسية مقابل الإضافات):\n"
        "   - Hekaya Extra (حكاية إكسترا) and Extra Units are ADD-ON TOP-UPS only for existing subscribers who need temporary units.\n"
        "   - Customers asking for a 200 EGP plan should NEVER be recommended an add-on like Extra 200 Units or Extra 15.\n\n"
        "Matching Keywords: باقة ب 200, باقة بـ 200, باقة في حدود 200, ميزانية 200, ريكومند لباقة ب 200, دقايق اكتر, مكالمات اكتر, حكاية مكسات 120, Hekaya Mixat 120, plan for 200 EGP, calls recommendation"
    )
    chunks.append((text_100_200, {
        "source": "PrepaidSystems.pdf", "category": "Plan Recommendations",
        "product": "Budget Guide (100-200 EGP)",
        "chunk_type": "budget_bracket_guide", "family": "cross_family",
        "chunk_id": "budget_guide_100_to_200",
        "snippet": "Cross-family comparison for 100-200 EGP budget: Hekaya Mixat 120 (calls) vs Hekaya Internet 105/132 (data).",
    }))

    # Bracket 2: Under 100 EGP (Budget / Entry)
    text_under_100 = (
        "=== Cross-Family Plan Comparison: Under 100 EGP Budget | باقات اتصالات مصر الاقتصادية أقل من 100 جنيه ===\n"
        "For customers looking for budget monthly packages under 100 EGP:\n"
        "1. Calls / Mix priority: Hekaya Mixat 52 (52 EGP, 74.29 EGP recharge, 1,900 mixes, *319*45#) and Hekaya Mixat 69 (69 EGP, 98.57 EGP recharge, 2,800 mixes, *319*60#).\n"
        "2. Internet priority: Hekaya Internet 46 (46 EGP, 65.71 EGP recharge, 1,250 MB + 300 call units) and Hekaya Internet 58 (58 EGP, 82.86 EGP recharge, 2,100 MB + 300 call units) and Hekaya Internet 80 (80 EGP, 114.29 EGP recharge, 3,250 MB + 300 call units).\n"
        "3. Short validity recharge: Aqwa Card 10, 15, 19, 29, 35 (2-day to 10-day flexible units via *811#).\n"
        "Matching Keywords: باقة رخيصة, باقة اقتصادية, أقل من 100 جنيه, باقة بـ 50, باقة بـ 70, budget plans under 100"
    )
    chunks.append((text_under_100, {
        "source": "PrepaidSystems.pdf", "category": "Plan Recommendations",
        "product": "Budget Guide (Under 100 EGP)",
        "chunk_type": "budget_bracket_guide", "family": "cross_family",
        "chunk_id": "budget_guide_under_100",
        "snippet": "Cross-family comparison for under 100 EGP budget: Hekaya Mixat 52/69 vs Hekaya Internet 46/58/80.",
    }))

    # Bracket 3: Hekaya Brand Overview (Mixat vs Internet)
    text_hekaya_overview = (
        "=== e& Egypt Hekaya Portfolio Overview: Hekaya Mixat vs Hekaya Internet | باقات عائلة حكاية بالكامل ===\n"
        "Hekaya (باقات حكاية) is e& Egypt's flagship prepaid mobile bundle brand, divided into TWO distinct product lines:\n\n"
        "1. 📱 HEKAYA MIXAT (حكاية مكسات) - Flexible Voice, SMS & Data Units:\n"
        "   - Core Concept: Unified 'Mix' units flexible for all usages (1 Mix = 1 min to e&, 5 Mix = 1 min to other networks, 1 Mix = 2 MB social, 1 Mix = 1 MB other sites).\n"
        "   - Key Benefits: Family lines sharing (share 10%, 25%, or 50% with family lines), favorite numbers at 0.5 Mix/min, unlimited FB/WhatsApp, VIU, Twist TV, Shahid Mobile, rollover on on-time renewal.\n"
        "   - Main Monthly Tiers: 52 EGP (1,900 Mix), 69 EGP (2,800 Mix), 92 EGP (3,750 Mix), 120 EGP (5,375 Mix), 180 EGP (9,350 Mix), 270 EGP (15,400 Mix), 350 EGP (21,500 Mix).\n"
        "   - Best Suited For: Customers who make frequent calls and want a balanced, flexible bundle for minutes, internet, and family sharing.\n\n"
        "2. 🌐 HEKAYA INTERNET (حكاية إنترنت) - Dedicated Mobile Internet & Data:\n"
        "   - Core Concept: High-allowance mobile internet megabytes with generous streaming and app bundles.\n"
        "   - Key Benefits: Includes 300 call/SMS units on every monthly plan, choice of free-use apps (1 to 3 apps depending on tier), Twist Sport/Music/TV, Shahid Mobile/VIP, Starzplay, and unused MB converts to e& money cashback.\n"
        "   - Main Monthly Tiers: 46 EGP (1,250 MB), 58 EGP (2,100 MB), 80 EGP (3,250 MB), 105 EGP (4,750 MB), 132 EGP (6,750 MB), 165 EGP (9,500 MB), 205 EGP (13,000 MB), 270 EGP (18,000 MB), up to 600 EGP (70,000 MB).\n"
        "   - Best Suited For: Heavy data users, video streaming, and social media browsing who prioritize internet quotas over voice minutes.\n\n"
        "Matching Keywords: what is hekaya, hekaya, باقات حكاية, ايه هي حكاية, الفرق بين حكاية مكسات وحكاية انترنت, عائلة حكاية, تفاصيل حكاية, حكاية اتصالات مصر, hekaya overview, hekaya plans"
    )
    chunks.append((text_hekaya_overview, {
        "source": "PrepaidSystems.pdf", "category": "Brand Overview",
        "product": "Hekaya Brand Portfolio (Mixat & Internet)",
        "chunk_type": "brand_portfolio_guide", "family": "cross_family",
        "chunk_id": "hekaya_brand_overview",
        "snippet": "e& Egypt Hekaya brand overview: Hekaya Mixat (calls/mixes) vs Hekaya Internet (high-data/cashback).",
    }))

    return chunks


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def render_all_chunks() -> List[Chunk]:
    """Constructs all hierarchical semantic chunks from the catalog."""
    catalog = get_catalog()
    chunks: List[Chunk] = []

    for family in catalog.families_list():
        # 1. Family Overview -- returns list (hekaya_internet = multiple sub-overviews)
        chunks.extend(_family_overview_chunk(family))

        # 2. Sub-Category / Group Chunks
        chunks.extend(_tier_group_chunks(family))

        # 3. Context-Rich Individual Tier Chunks
        for tier in family["tiers"]:
            chunks.append(_tier_chunk(family, tier))

        # 4. Family-wide Terms & Glossary
        chunks.extend(_terms_chunks(family))
        chunks.extend(_glossary_chunks(family))

        # 5. Emerald Special Topic Chunks
        if family["family"] == "emerald":
            chunks.extend(_emerald_extra_chunks(family))

    # 6. Global Domain Policy Chunks (Tax math & USSD Directory)
    chunks.extend(_policy_chunks())

    # 7. Dynamic Cross-Family Budget Bracket Chunks
    chunks.extend(_dynamic_budget_chunks())

    return chunks
