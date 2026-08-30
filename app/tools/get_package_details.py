"""
app/tools/get_package_details.py
----------------------------------
Tool: get_package_details
Returns structured package information for a named e& Egypt package.
Single source of truth for exact specifications, USSD codes, and prices.
"""
import re
from typing import Any, Dict, List, Optional

PACKAGE_REGISTRY = {
    # ── 1. Aqwa Card Recharges (Simple Prepaid) ─────────────────────────────
    "aqwa card 5": {
        "pretax_price_egp": 5,
        "total_price_egp": 5.0,
        "pretax_price": 5,
        "total_egp": 5.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 5",
        "category": "prepaid",
        "quota": "80 Mixes",
        "mixes": 80,
        "video_minutes": 0,
        "hekaya_mini_included": False,
        "has_hekaya_mini": "No (does not include Hekaya Mini)",
        "validity_days": 2,
        "description": "80 Mixes for calls, megabytes, or SMS with 2 days validity. Does NOT include Hekaya Mini recharge.",
        "perks": "Flexible unit allocation to calls or internet",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 10": {
        "pretax_price_egp": 10,
        "total_price_egp": 10.0,
        "pretax_price": 10,
        "total_egp": 10.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 10",
        "category": "prepaid",
        "quota": "175 Mixes / MB / minutes",
        "mixes": 175,
        "video_minutes": 100,
        "hekaya_mini_included": False,
        "has_hekaya_mini": "No",
        "validity_days": 3,
        "description": "175 Mixes for calls and megabytes with 3 days validity via *811#.",
        "perks": "100 video/social minutes",
        "source": "e& Egypt Prepaid Systems",
    },
    "aqwa card 15": {
        "pretax_price_egp": 15,
        "total_price_egp": 15.0,
        "pretax_price": 15,
        "total_egp": 15.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 15",
        "category": "prepaid",
        "quota": "300 Mixes / MB / minutes",
        "mixes": 300,
        "video_minutes": 210,
        "hekaya_mini_included": False,
        "has_hekaya_mini": "No (does not include Hekaya Mini)",
        "validity_days": 2,
        "description": "300 Mixes/MB/minutes + 210 video & streaming minutes, valid for 2 days. Does NOT include Hekaya Mini.",
        "perks": "210 dedicated video/social minutes",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 19": {
        "pretax_price_egp": 19,
        "total_price_egp": 19.0,
        "pretax_price": 19,
        "total_egp": 19.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 19",
        "category": "prepaid",
        "quota": "425 Mixes / MB / minutes",
        "mixes": 425,
        "video_minutes": 300,
        "hekaya_mini_included": True,
        "has_hekaya_mini": "Yes (includes embedded Hekaya Mini recharge worth 400 Mixes + Facebook & WhatsApp)",
        "validity_days": 6,
        "description": "425 Mixes/MB/minutes + 300 video/social minutes + embedded Hekaya Mini recharge (400 Mixes + Facebook & WhatsApp), valid for 6 days.",
        "perks": "Embedded Hekaya Mini (400 Mixes + FB & WA) + 300 Video Min",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 22.5": {
        "pretax_price_egp": 22.5,
        "total_price_egp": 22.5,
        "pretax_price": 22.5,
        "total_egp": 22.5,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 22.5",
        "category": "prepaid",
        "quota": "550 Mixes / MB / minutes",
        "mixes": 550,
        "video_minutes": 320,
        "hekaya_mini_included": True,
        "has_hekaya_mini": "Yes (includes embedded Hekaya Mini recharge worth 525 Mixes + Facebook & WhatsApp)",
        "validity_days": 7,
        "description": "550 Mixes/MB/minutes + 320 video/social minutes + embedded Hekaya Mini (525 Mixes + FB & WA), valid for 7 days.",
        "perks": "Embedded Hekaya Mini (525 Mixes) + 320 Video Min",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 30": {
        "pretax_price_egp": 30,
        "total_price_egp": 30.0,
        "pretax_price": 30,
        "total_egp": 30.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 30",
        "category": "prepaid",
        "quota": "750 Mixes / MB / minutes",
        "mixes": 750,
        "video_minutes": 400,
        "hekaya_mini_included": True,
        "has_hekaya_mini": "Yes (includes embedded Hekaya Mini recharge worth 700 Mixes + Facebook & WhatsApp)",
        "validity_days": 10,
        "description": "750 Mixes/MB/minutes + 400 video minutes + embedded Hekaya Mini (700 Mixes + FB & WA), valid for 10 days.",
        "perks": "Embedded Hekaya Mini (700 Mixes) + 400 Video Min",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 44": {
        "pretax_price_egp": 44,
        "total_price_egp": 44.0,
        "pretax_price": 44,
        "total_egp": 44.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 44",
        "category": "prepaid",
        "quota": "1,100 Mixes / MB / minutes",
        "mixes": 1100,
        "video_minutes": 0,
        "hekaya_mini_included": False,
        "has_hekaya_mini": "No (does not include Hekaya Mini)",
        "validity_days": 14,
        "description": "1,100 Mixes/MB/minutes valid for 14 days. Does NOT include Hekaya Mini.",
        "perks": "1,100 Mixes for calls/net",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 45": {
        "pretax_price_egp": 45,
        "total_price_egp": 45.0,
        "pretax_price": 45,
        "total_egp": 45.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 45",
        "category": "prepaid",
        "quota": "700 Mixes / MB / minutes",
        "mixes": 700,
        "video_minutes": 0,
        "hekaya_mini_included": False,
        "has_hekaya_mini": "No (does not include Hekaya Mini)",
        "validity_days": 28,
        "description": "700 Mixes/MB/minutes valid for 28 days. Does NOT include Hekaya Mini.",
        "perks": "28 days monthly validity",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 50": {
        "pretax_price_egp": 50,
        "total_price_egp": 50.0,
        "pretax_price": 50,
        "total_egp": 50.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 50",
        "category": "prepaid",
        "quota": "1,400 Mixes / MB / minutes",
        "mixes": 1400,
        "video_minutes": 750,
        "hekaya_mini_included": True,
        "has_hekaya_mini": "Yes (includes embedded Hekaya Mini recharge)",
        "validity_days": 14,
        "description": "1,400 Mixes + 750 video minutes + embedded Hekaya Mini, valid for 14 days.",
        "perks": "Embedded Hekaya Mini + 750 Video Min",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },
    "aqwa card 75": {
        "pretax_price_egp": 75,
        "total_price_egp": 75.0,
        "pretax_price": 75,
        "total_egp": 75.0,
        "ussd": "*811#",
        "activation_code": "*811#",
        "service": "Aqwa Card",
        "type": "Aqwa Card 75",
        "category": "prepaid",
        "quota": "2,400 Mixes / MB / minutes",
        "mixes": 2400,
        "video_minutes": 1200,
        "hekaya_mini_included": True,
        "has_hekaya_mini": "Yes (includes embedded Hekaya Mini recharge)",
        "validity_days": 28,
        "description": "2,400 Mixes + 1,200 video minutes + embedded Hekaya Mini, valid for 28 days.",
        "perks": "Embedded Hekaya Mini + 1,200 Video Min",
        "source": "e& Egypt Prepaid Systems (PrepaidSystems.pdf)",
    },

    # ── 2. Hekaya Mixat (Prepaid Mix Bundles) ────────────────────────────────
    "hekaya mixat 52": {
        "pretax_price_egp": 52,
        "total_price_egp": 74.29,
        "pretax_price": 52,
        "total_egp": 74.29,
        "ussd": "*319*45#",
        "activation_code": "*319*45#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 52",
        "category": "mobile",
        "quota": "1,900 Mix units",
        "mixes": 1900,
        "coins_on_renewal": 104,
        "validity_days": 30,
        "family_lines": "0",
        "description": "1,900 Mix units for calls and mobile internet, 104 Coins on renewal via *319*45#",
        "perks": "Rollover of unused units on renewal + 104 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },
    "hekaya mixat 69": {
        "pretax_price_egp": 69,
        "total_price_egp": 98.58,
        "pretax_price": 69,
        "total_egp": 98.58,
        "ussd": "*319*69#",
        "activation_code": "*319*69#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 69",
        "category": "mobile",
        "quota": "2,750 Mix units",
        "mixes": 2750,
        "coins_on_renewal": 138,
        "validity_days": 30,
        "family_lines": "0",
        "description": "2,750 Mix units for calls and data, 138 Coins on renewal via *319*69#",
        "perks": "Rollover of unused units + 138 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },
    "hekaya mixat 92": {
        "pretax_price_egp": 92,
        "total_price_egp": 131.43,
        "pretax_price": 92,
        "total_egp": 131.43,
        "ussd": "*319*80#",
        "activation_code": "*319*80#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 92",
        "category": "mobile",
        "quota": "3,750 Mix units",
        "mixes": 3750,
        "coins_on_renewal": 184,
        "validity_days": 30,
        "family_lines": "1 family line (Mix percentage allocation: 10%, 25%, or 50% of primary bundle; no minute-based allocation)",
        "description": "3,750 Mix units + 1 Family Line (allocated as a percentage of primary Mixes: 10%, 25%, or 50%), 184 Coins on renewal via *319*80#",
        "perks": "1 Family Line + Rollover + 184 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },
    "hekaya mixat 120": {
        "pretax_price_egp": 120,
        "total_price_egp": 171.44,
        "pretax_price": 120,
        "total_egp": 171.44,
        "ussd": "*319*105#",
        "activation_code": "*319*105#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 120",
        "category": "mobile",
        "quota": "5,375 Mix units",
        "mixes": 5375,
        "coins_on_renewal": 240,
        "validity_days": 30,
        "family_lines": "1 family line (Mix percentage allocation: 10%, 25%, or 50% of primary bundle; no minute-based allocation)",
        "description": "5,375 Mix units + 1 Family Line (allocated as a percentage of primary Mixes: 10%, 25%, or 50%), 240 Coins on renewal via *319*105#",
        "perks": "1 Family Line + Rollover + 240 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },
    "hekaya mixat 180": {
        "pretax_price_egp": 180,
        "total_price_egp": 257.15,
        "pretax_price": 180,
        "total_egp": 257.15,
        "ussd": "*319*155#",
        "activation_code": "*319*155#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 180",
        "category": "mobile",
        "quota": "9,350 Mix units",
        "mixes": 9350,
        "coins_on_renewal": 360,
        "validity_days": 30,
        "family_lines": "2 family lines (Mix percentage allocation: 10%, 25%, or 50% of primary bundle; no minute-based allocation)",
        "description": "9,350 Mix units + 2 Family Lines (allocated as a percentage of primary Mixes: 10%, 25%, or 50%), Home Internet redemption eligible (100 GB for 5,800 Mixes), 360 Coins on renewal via *319*155#",
        "perks": "2 Family Lines + Home Internet Redemption + Rollover + 360 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },
    "hekaya mixat 270": {
        "pretax_price_egp": 270,
        "total_price_egp": 385.72,
        "pretax_price": 270,
        "total_egp": 385.72,
        "ussd": "*319*235#",
        "activation_code": "*319*235#",
        "service": "Hekaya Mixat",
        "type": "Hekaya Mixat 270",
        "category": "mobile",
        "quota": "15,400 Mix units",
        "mixes": 15400,
        "coins_on_renewal": 540,
        "validity_days": 30,
        "family_lines": "3 family lines (Mix percentage allocation: 10%, 25%, or 50% of primary bundle; no minute-based allocation)",
        "description": "15,400 Mix units + 3 Family Lines (allocated as a percentage of primary Mixes: 10%, 25%, or 50%), Home Internet redemption eligible (100 GB for 5,800 Mixes or 150 GB for 7,000 Mixes), 540 Coins on renewal via *319*235#",
        "perks": "3 Family Lines + Home Internet Redemption (up to 150 GB) + Rollover + 540 Coins",
        "source": "e& Egypt Hekaya Mixat Portfolio",
    },

    # ── 3. Hekaya Internet (Data-focused Bundles) ────────────────────────────
    "hekaya internet 46":  {"pretax_price_egp": 46,  "total_price_egp": 65.72,  "pretax_price": 46,  "total_egp": 65.72,  "ussd": "*319*46#",  "activation_code": "*319*46#",  "service": "Hekaya Internet", "type": "Hekaya Internet 46", "quota": "1,250 MB",  "validity_days": 30, "description": "1,250 MB high-speed mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 58":  {"pretax_price_egp": 58,  "total_price_egp": 82.86,  "pretax_price": 58,  "total_egp": 82.86,  "ussd": "*319*58#",  "activation_code": "*319*58#",  "service": "Hekaya Internet", "type": "Hekaya Internet 58", "quota": "1,750 MB",  "validity_days": 30, "description": "1,750 MB high-speed mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 80":  {"pretax_price_egp": 80,  "total_price_egp": 114.29, "pretax_price": 80,  "total_egp": 114.29, "ussd": "*319*80#",  "activation_code": "*319*80#",  "service": "Hekaya Internet", "type": "Hekaya Internet 80", "quota": "3,250 MB",  "validity_days": 30, "description": "3,250 MB high-speed mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 105": {"pretax_price_egp": 105, "total_price_egp": 150.00, "pretax_price": 105, "total_egp": 150.00, "ussd": "*319#",  "activation_code": "*319#",  "service": "Hekaya Internet", "type": "Hekaya Internet 105", "quota": "4,750 MB",  "validity_days": 30, "description": "4,750 MB mobile internet + 300 call/SMS units + 2 apps", "perks": "Rollover + 2 Selected Apps + Shahid Mobile + VIU", "source": "e& Egypt Hekaya Internet (HekayaInternet.pdf)"},
    "hekaya internet 132": {"pretax_price_egp": 132, "total_price_egp": 188.57, "pretax_price": 132, "total_egp": 188.57, "ussd": "*319*132#", "activation_code": "*319*132#", "service": "Hekaya Internet", "type": "Hekaya Internet 132", "quota": "6,750 MB",  "validity_days": 30, "description": "6,750 MB mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 165": {"pretax_price_egp": 165, "total_price_egp": 235.71, "pretax_price": 165, "total_egp": 235.71, "ussd": "*319*165#", "activation_code": "*319*165#", "service": "Hekaya Internet", "type": "Hekaya Internet 165", "quota": "8,750 MB",  "validity_days": 30, "description": "8,750 MB mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 205": {"pretax_price_egp": 205, "total_price_egp": 292.86, "pretax_price": 205, "total_egp": 292.86, "ussd": "*319*205#", "activation_code": "*319*205#", "service": "Hekaya Internet", "type": "Hekaya Internet 205", "quota": "11,500 MB", "validity_days": 30, "description": "11,500 MB (11.5 GB) mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 270": {"pretax_price_egp": 270, "total_price_egp": 385.71, "pretax_price": 270, "total_egp": 385.71, "ussd": "*319*270#", "activation_code": "*319*270#", "service": "Hekaya Internet", "type": "Hekaya Internet 270", "quota": "15,000 MB", "validity_days": 30, "description": "15,000 MB (15 GB) mobile internet bundle", "perks": "Rollover", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 345": {"pretax_price_egp": 345, "total_price_egp": 492.86, "pretax_price": 345, "total_egp": 492.86, "ussd": "*319*345#", "activation_code": "*319*345#", "service": "Hekaya Internet", "type": "Hekaya Internet 345", "quota": "20,000 MB", "validity_days": 30, "description": "20,000 MB (20 GB) mobile internet + Shahid VIP subscription", "perks": "Free Shahid VIP", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 415": {"pretax_price_egp": 415, "total_price_egp": 592.86, "pretax_price": 415, "total_egp": 592.86, "ussd": "*319*415#", "activation_code": "*319*415#", "service": "Hekaya Internet", "type": "Hekaya Internet 415", "quota": "25,000 MB", "validity_days": 30, "description": "25,000 MB (25 GB) mobile internet + Shahid VIP subscription", "perks": "Free Shahid VIP", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 480": {"pretax_price_egp": 480, "total_price_egp": 685.71, "pretax_price": 480, "total_egp": 685.71, "ussd": "*319*480#", "activation_code": "*319*480#", "service": "Hekaya Internet", "type": "Hekaya Internet 480", "quota": "30,000 MB", "validity_days": 30, "description": "30,000 MB (30 GB) mobile internet + TOD + Shahid VIP", "perks": "Free TOD + Shahid VIP", "source": "e& Egypt Hekaya Internet"},
    "hekaya internet 600": {"pretax_price_egp": 600, "total_price_egp": 857.14, "pretax_price": 600, "total_egp": 857.14, "ussd": "*319*600#", "activation_code": "*319*600#", "service": "Hekaya Internet", "type": "Hekaya Internet 600", "quota": "50,000 MB", "validity_days": 30, "description": "50,000 MB (50 GB) mobile internet + TOD + Shahid VIP", "perks": "Free TOD + Shahid VIP", "source": "e& Egypt Hekaya Internet"},

    # ── 4. Emerald Postpaid Plans ───────────────────────────────────────────
    # Corrected against the source PDF (Emerald (2).pdf) — every entry here
    # previously had wrong data_gb/minutes (e.g. two tiers claimed "unlimited"
    # minutes; the PDF gives a finite figure for every tier) AND total_price_egp
    # computed with the prepaid 1.42857x multiplier instead of Emerald's actual
    # documented tax structure (Section 9: 8% schedule tax + 14% VAT, additive,
    # + a flat 10 EGP monthly state fee — see app/tools/calculate_price.py).
    # total_price_egp below = pretax * 1.22 + 10, matching that formula exactly.
    "emerald 430":  {"pretax_price_egp": 430,  "total_price_egp": 534.60,  "pretax_price": 430,  "total_egp": 534.60,  "minutes": 2500,  "data_gb": 12,  "ussd": "Call 111", "activation_code": "Call 111", "service": "Emerald Postpaid", "type": "Emerald 430", "quota": "12 GB mobile internet + 2,500 local minutes", "validity_days": 30, "description": "Postpaid plan with 12 GB, 2,500 minutes, 500 SMS, and 1 extra family line", "perks": "Roaming + Entertainment E-Coins + eHome discount", "source": "e& Egypt Emerald"},
    "emerald 780":  {"pretax_price_egp": 780,  "total_price_egp": 961.60,  "pretax_price": 780,  "total_egp": 961.60,  "minutes": 4500,  "data_gb": 25, "ussd": "Call 111", "activation_code": "Call 111", "service": "Emerald Postpaid", "type": "Emerald 780", "quota": "25 GB mobile internet + 4,500 local minutes", "validity_days": 30, "description": "Postpaid plan with 25 GB, 4,500 minutes, 2,000 SMS, and 2 extra family lines", "perks": "Roaming + Entertainment E-Coins + eHome discount", "source": "e& Egypt Emerald"},
    "emerald 1120": {"pretax_price_egp": 1120, "total_price_egp": 1376.40, "pretax_price": 1120, "total_egp": 1376.40, "minutes": 6500,  "data_gb": 40, "ussd": "Call 111", "activation_code": "Call 111", "service": "Emerald Postpaid", "type": "Emerald 1120", "quota": "40 GB mobile internet + 6,500 local minutes", "validity_days": 30, "description": "Postpaid plan with 40 GB, 6,500 minutes, 2,000 SMS, and 4 extra family lines", "perks": "Roaming + Entertainment E-Coins + eHome discount", "source": "e& Egypt Emerald"},
    "emerald 1725": {"pretax_price_egp": 1725, "total_price_egp": 2114.50, "pretax_price": 1725, "total_egp": 2114.50, "minutes": 10000, "data_gb": 70, "ussd": "Call 111", "activation_code": "Call 111", "service": "Emerald Postpaid", "type": "Emerald 1725", "quota": "70 GB mobile internet + 10,000 local minutes", "validity_days": 30, "description": "Premium postpaid plan with 70 GB, 10,000 minutes, 2,000 SMS, and 5 extra family lines", "perks": "Concierge + VIP lounge access + Entertainment", "source": "e& Egypt Emerald"},
    "emerald 3450": {"pretax_price_egp": 3450, "total_price_egp": 4219.00, "pretax_price": 3450, "total_egp": 4219.00, "minutes": 12000, "data_gb": 200, "ussd": "Call 111", "activation_code": "Call 111", "service": "Emerald Postpaid", "type": "Emerald 3450", "quota": "200 GB mobile internet + 12,000 local minutes", "validity_days": 30, "description": "Ultra VIP postpaid plan with 200 GB, 12,000 minutes, 2,000 SMS, and 7 extra family lines", "perks": "24/7 personal account manager + Full entertainment suite + Global roaming", "source": "e& Egypt Emerald"},

    # ── 5. DataLine (MiFi & Dedicated Data SIMs) ────────────────────────────
    "dataline 1.8gb": {"pretax_price_egp": 46, "total_price_egp": 65.72, "pretax_price": 46, "total_egp": 65.72, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 1.8GB", "quota": "1.8 GB", "validity_days": 30, "description": "1.8 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 2.5gb": {"pretax_price_egp": 60, "total_price_egp": 85.71, "pretax_price": 60, "total_egp": 85.71, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 2.5GB", "quota": "2.5 GB", "validity_days": 30, "description": "2.5 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 3.5gb": {"pretax_price_egp": 69, "total_price_egp": 98.58, "pretax_price": 69, "total_egp": 98.58, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 3.5GB", "quota": "3.5 GB", "validity_days": 30, "description": "3.5 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 7gb": {"pretax_price_egp": 115, "total_price_egp": 164.29, "pretax_price": 115, "total_egp": 164.29, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 7GB", "quota": "7 GB", "validity_days": 30, "description": "7 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 8gb": {"pretax_price_egp": 75, "total_price_egp": 107.14, "pretax_price": 75, "total_egp": 107.14, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 8GB", "quota": "8 GB", "validity_days": 30, "description": "8 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 14gb": {"pretax_price_egp": 172.5, "total_price_egp": 246.43, "pretax_price": 172.5, "total_egp": 246.43, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 14GB", "quota": "14 GB", "validity_days": 30, "description": "14 GB dedicated MiFi/USB internet SIM", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 25gb": {"pretax_price_egp": 200, "total_price_egp": 285.71, "pretax_price": 200, "total_egp": 285.71, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 25GB", "quota": "25 GB", "validity_days": 30, "description": "25 GB dedicated MiFi/USB internet SIM (or 375 EGP for 3 months)", "perks": "Double package on 1st recharge", "source": "e& Egypt DataLine"},
    "dataline 45gb": {"pretax_price_egp": 600, "total_price_egp": 857.14, "pretax_price": 600, "total_egp": 857.14, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 45GB", "quota": "45 GB", "validity_days": 90, "description": "45 GB 3-month package for 600 EGP", "perks": "3-Month Validity", "source": "e& Egypt DataLine"},
    "dataline 50gb": {"pretax_price_egp": 150, "total_price_egp": 214.29, "pretax_price": 150, "total_egp": 214.29, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 50GB", "quota": "50 GB", "validity_days": 30, "description": "50 GB data-only package for MiFi and 4G routers", "perks": "High-speed 4G data only", "source": "e& Egypt DataLine"},
    "dataline 72gb": {"pretax_price_egp": 900, "total_price_egp": 1285.71, "pretax_price": 900, "total_egp": 1285.71, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 72GB (6 Months)", "quota": "72 GB (144 GB double offer)", "validity_days": 180, "description": "72 GB dedicated MiFi internet SIM for 6 months (900 EGP before tax) with 144 GB double offer on 1st recharge", "perks": "6-Month Validity + Double Offer", "source": "e& Egypt DataLine"},
    "dataline 100gb": {"pretax_price_egp": 250, "total_price_egp": 357.14, "pretax_price": 250, "total_egp": 357.14, "ussd": "*130#", "activation_code": "*130#", "service": "DataLine", "type": "DataLine 100GB", "quota": "100 GB", "validity_days": 30, "description": "100 GB data-only package for MiFi and 4G routers", "perks": "High-speed 4G data only", "source": "e& Egypt DataLine"},

    # ── 6. Super Connect Add-on Bundles ──────────────────────────────────────
    "super connect 9":   {"pretax_price_egp": 9,   "total_price_egp": 12.86,  "pretax_price": 9,   "total_egp": 12.86,  "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 9",   "quota": "600 MB",   "validity_days": 30, "description": "600 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 20":  {"pretax_price_egp": 20,  "total_price_egp": 28.57,  "pretax_price": 20,  "total_egp": 28.57,  "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 20",  "quota": "1,500 MB", "validity_days": 30, "description": "1,500 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 32":  {"pretax_price_egp": 32,  "total_price_egp": 45.71,  "pretax_price": 32,  "total_egp": 45.71,  "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 32",  "quota": "2,500 MB", "validity_days": 30, "description": "2,500 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 50":  {"pretax_price_egp": 50,  "total_price_egp": 71.43,  "pretax_price": 50,  "total_egp": 71.43,  "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 50",  "quota": "4,500 MB", "validity_days": 30, "description": "4,500 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 80":  {"pretax_price_egp": 80,  "total_price_egp": 114.29, "pretax_price": 80,  "total_egp": 114.29, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 80",  "quota": "8,000 MB", "validity_days": 30, "description": "8,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 105": {"pretax_price_egp": 105, "total_price_egp": 150.00, "pretax_price": 105, "total_egp": 150.00, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 105", "quota": "12,000 MB", "validity_days": 30, "description": "12,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 165": {"pretax_price_egp": 165, "total_price_egp": 235.71, "pretax_price": 165, "total_egp": 235.71, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 165", "quota": "20,000 MB", "validity_days": 30, "description": "20,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 260": {"pretax_price_egp": 260, "total_price_egp": 371.43, "pretax_price": 260, "total_egp": 371.43, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 260", "quota": "32,000 MB", "validity_days": 30, "description": "32,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 390": {"pretax_price_egp": 390, "total_price_egp": 557.14, "pretax_price": 390, "total_egp": 557.14, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 390", "quota": "50,000 MB", "validity_days": 30, "description": "50,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},
    "super connect 520": {"pretax_price_egp": 520, "total_price_egp": 742.86, "pretax_price": 520, "total_egp": 742.86, "ussd": "*566#", "activation_code": "*566#", "service": "Super Connect", "type": "Super Connect 520", "quota": "70,000 MB", "validity_days": 30, "description": "70,000 MB mobile internet bundle via *566#", "perks": "Exclusive add-on", "source": "e& Egypt Super Connect"},

    # ── 7. Daily Bundles & Add-ons ──────────────────────────────────────────
    "daily 55":  {"pretax_price_egp": 3, "total_price_egp": 4.29, "pretax_price": 3, "total_egp": 4.29, "ussd": "*972#", "activation_code": "*972#", "service": "Daily Plans", "type": "Daily Bundle 55 Mixes", "quota": "55 Mixes", "validity_days": 1, "description": "55 Mixes for calls and net with 24 hours validity via *972#", "perks": "Daily flexibility", "source": "e& Egypt Prepaid Systems"},
    "daily 120": {"pretax_price_egp": 6, "total_price_egp": 8.57, "pretax_price": 6, "total_egp": 8.57, "ussd": "*973#", "activation_code": "*973#", "service": "Daily Plans", "type": "Daily Bundle 120 Mixes", "quota": "120 Mixes", "validity_days": 1, "description": "120 Mixes for calls and net with 24 hours validity via *973#", "perks": "Daily flexibility", "source": "e& Egypt Prepaid Systems"},
    "extra 4.5": {"pretax_price_egp": 4.5, "total_price_egp": 6.43, "pretax_price": 4.5, "total_egp": 6.43, "ussd": "*626#", "activation_code": "*626#", "service": "Hekaya Extra", "type": "Hekaya Extra 4.5", "quota": "60 Mixes", "validity_days": 30, "description": "60 Mixes extra add-on via *626#", "perks": "Add-on for Hekaya Mixat", "source": "e& Egypt Hekaya Mixat"},
    "extra 7.5": {"pretax_price_egp": 7.5, "total_price_egp": 10.71, "pretax_price": 7.5, "total_egp": 10.71, "ussd": "*626#", "activation_code": "*626#", "service": "Hekaya Extra", "type": "Hekaya Extra 7.5", "quota": "120 Mixes", "validity_days": 30, "description": "120 Mixes extra add-on via *626#", "perks": "Add-on for Hekaya Mixat", "source": "e& Egypt Hekaya Mixat"},
    "extra 15":  {"pretax_price_egp": 15, "total_price_egp": 21.43, "pretax_price": 15, "total_egp": 21.43, "ussd": "*626#", "activation_code": "*626#", "service": "Hekaya Extra", "type": "Hekaya Extra 15", "quota": "300 Mixes", "validity_days": 30, "description": "300 Mixes extra add-on via *626#", "perks": "Add-on for Hekaya Mixat", "source": "e& Egypt Hekaya Mixat"},
    "ahlan":     {"pretax_price_egp": 0, "total_price_egp": 0.0, "pretax_price": 0, "total_egp": 0.0, "ussd": "*339#", "activation_code": "*339#", "service": "Ahlan", "type": "Ahlan Pay As You Go", "quota": "Per-minute billing (19 piasters/min)", "validity_days": 365, "description": "Ahlan Pay As You Go prepaid plan via *339#", "perks": "Standard per-minute rates", "source": "e& Egypt Prepaid Systems"},
}


def normalize_package_query(raw_name: str) -> str:
    """Normalize user package string to canonical registry key."""
    k = str(raw_name or "").strip().lower()

    # Digits normalization
    arabic_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    k = k.translate(arabic_digits)

    # Arabic translations & aliases
    k = re.sub(r"أقوى\s*كارت|اقوى\s*كارت|اقوي\s*كارت|كارت\s*أقوى|كروت\s*أقوى|كارت", "aqwa card", k)
    k = re.sub(r"حكاية\s*مكسات|حكاية\s*ميكسات|باقة\s*مكسات|مكسات", "hekaya mixat", k)
    k = re.sub(r"حكاية\s*إنترنت|حكاية\s*انترنت|باقة\s*نت|نت\s*حكاية", "hekaya internet", k)
    k = re.sub(r"سوبر\s*كونكت|سوبركونكت", "super connect", k)
    k = re.sub(r"إمرالد|امرالد|اميرالد", "emerald", k)
    k = re.sub(r"داتا\s*لاين|داتالاين|data\s+line", "dataline", k)
    k = re.sub(r"(\d+)\s*(?:gb|جيجا)", r"\1gb", k)

    # Clean punctuation
    k = re.sub(r"[^\w\s\.]", " ", k)
    k = " ".join(k.split())
    return k


def get_package_details_tool(package_name: str) -> Dict[str, Any]:
    """
    Return structured details for a named e& Egypt package.

    Args:
        package_name: Package name, e.g. "Aqwa Card 19", "Hekaya Mixat 52", "Emerald 430".

    Returns:
        Dict with structured package details, or error if not found in registry.
    """
    raw_name = str(package_name or "").strip()
    key = normalize_package_query(raw_name)

    # 1. Direct key match
    if key in PACKAGE_REGISTRY:
        details = dict(PACKAGE_REGISTRY[key])
        details["package_name"] = details.get("type") or raw_name
        return {"found": True, **details}

    # 2. Match with extracted numbers and category
    numbers = re.findall(r"\d+(?:\.\d+)?", key)
    if numbers:
        num = numbers[0]
        # Check Aqwa card
        if "aqwa" in key or "card" in key:
            candidate = f"aqwa card {num}"
            if candidate in PACKAGE_REGISTRY:
                details = dict(PACKAGE_REGISTRY[candidate])
                details["package_name"] = f"Aqwa Card {num}"
                return {"found": True, **details}
        # Check Hekaya mixat
        if "mix" in key or "hekaya" in key or "مكس" in key:
            candidate = f"hekaya mixat {num}"
            if candidate in PACKAGE_REGISTRY:
                details = dict(PACKAGE_REGISTRY[candidate])
                details["package_name"] = f"Hekaya Mixat {num}"
                return {"found": True, **details}
        # Check Hekaya internet
        if "net" in key or "internet" in key:
            candidate = f"hekaya internet {num}"
            if candidate in PACKAGE_REGISTRY:
                details = dict(PACKAGE_REGISTRY[candidate])
                details["package_name"] = f"Hekaya Internet {num}"
                return {"found": True, **details}
        # Check Emerald
        if "emerald" in key or "postpaid" in key:
            candidate = f"emerald {num}"
            if candidate in PACKAGE_REGISTRY:
                details = dict(PACKAGE_REGISTRY[candidate])
                details["package_name"] = f"Emerald {num}"
                return {"found": True, **details}
        # Check DataLine
        if "dataline" in key or "mifi" in key:
            candidate = f"dataline {num}gb"
            if candidate in PACKAGE_REGISTRY:
                details = dict(PACKAGE_REGISTRY[candidate])
                details["package_name"] = f"DataLine {num}GB"
                return {"found": True, **details}

    # 3. Substring search in registry keys
    for reg_key, reg_val in PACKAGE_REGISTRY.items():
        if reg_key in key or key in reg_key:
            details = dict(reg_val)
            details["package_name"] = details.get("type") or raw_name
            details["matched_key"] = reg_key
            return {"found": True, **details}

    # 4. Find closest known package if numbers are close
    closest_match = None
    if numbers:
        try:
            target_num = float(numbers[0])
            best_diff = float("inf")
            target_family = None
            if "mix" in key or "مكس" in key:
                target_family = "hekaya mixat"
            elif "net" in key or "internet" in key or "نت" in key:
                target_family = "hekaya internet"
            elif "emerald" in key or "إمرالد" in key:
                target_family = "emerald"
            elif "aqwa" in key or "كارت" in key:
                target_family = "aqwa card"

            for reg_key, reg_val in PACKAGE_REGISTRY.items():
                if target_family and not reg_key.startswith(target_family):
                    continue
                reg_nums = re.findall(r"\d+(?:\.\d+)?", reg_key)
                if reg_nums:
                    diff = abs(float(reg_nums[0]) - target_num)
                    if diff < best_diff and diff <= 15:
                        best_diff = diff
                        closest_match = reg_val.get("type") or reg_key
        except Exception:
            pass

    return {
        "found": False,
        "package_name": raw_name,
        "closest_match": closest_match,
        "message": f"Package '{raw_name}' not found in local registry. Try search_knowledge_base for broader query.",
    }

