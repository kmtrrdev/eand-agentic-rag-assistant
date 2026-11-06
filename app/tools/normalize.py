"""Shared Arabic/English package-name normalization used by every tool below."""
import re
from typing import Optional

_ARABIC_ALIASES = [
    (r"[أا]قو[ىي]\s*كارت|كارت\s*[أا]قو[ىي]|كروت\s*[أا]قو[ىي]", "aqwa card"),
    (r"حكاي[ةه]\s*م[ي]?كسات|باق[ةه]\s*م[ي]?كسات|م[ي]?كسات", "hekaya mixat"),
    (r"حكاي[ةه]\s*[إا]نترنت|حكاي[ةه]\s*نت|باق[ةه]\s*نت", "hekaya internet"),
    (r"سوبر\s*كونكت|سوبركونكت", "super connect"),
    (r"[إا]يميرالد|[إا]مرالد|[إا]ميرالد|[إا]يمرالد|زمرد", "emerald"),
    (r"داتا\s*لاين|داتالاين|data\s*line", "dataline"),
]

# Quota units: package tier names embed the quota with no space ("DataLine
# 50GB"), but customers write it with a space and/or in Arabic ("50 جيجا",
# "50 GB"). Without this, "داتا لاين 50 جيجا" never normalizes into a string
# containing "50gb" and every match pass below misses the exact tier.
_UNIT_ALIASES = [
    (r"جيجا\s*بايت|جيجابايت|جيجا", "gb"),
    (r"ميجا\s*بايت|ميجابايت|ميجا", "mb"),
]

FAMILY_ALIASES = {
    "aqwa card": "aqwa_card",
    "aqwa": "aqwa_card",
    "hekaya mixat": "hekaya_mixat",
    "mixat": "hekaya_mixat",
    "hekaya internet": "hekaya_internet",
    "hekaya": "hekaya",
    "dataline": "dataline",
    "super connect": "super_connect",
    "emerald": "emerald",
}


def normalize(raw: str) -> str:
    text = str(raw or "").strip().lower()
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    # Internal family ids are snake_case ("hekaya_internet", "super_connect");
    # treat the underscore as a word separator so those ids normalize the same
    # way as their space-separated aliases below.
    text = text.replace("_", " ")
    for pattern, repl in _ARABIC_ALIASES:
        text = re.sub(pattern, repl, text)
    for pattern, repl in _UNIT_ALIASES:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"[^\w\s\.]", " ", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s+(gb|mb)\b", r"\1\2", text)
    return " ".join(text.split())


def guess_family(normalized_text: str) -> Optional[str]:
    for alias, family_id in FAMILY_ALIASES.items():
        if alias in normalized_text:
            return family_id
    return None
