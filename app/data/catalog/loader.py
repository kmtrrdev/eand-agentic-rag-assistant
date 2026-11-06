"""
Single source of truth for e& Egypt package data.

Loads every app/data/catalog/*.yaml family file into one validated, in-memory
catalog shared by app/tools (exact lookups), app/ingestion (RAG chunk
rendering) and app/retrieval — so a tool answer and a retrieved chunk can
never disagree on a price, quota, or USSD code.
"""
import functools
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CATALOG_DIR = Path(__file__).resolve().parent
FAMILY_FILES = [
    "aqwa_card.yaml",
    "hekaya_mixat.yaml",
    "hekaya_internet.yaml",
    "dataline.yaml",
    "super_connect.yaml",
    "daily_addons.yaml",
    "emerald.yaml",
]
REQUIRED_TIER_FIELDS = ("id", "name_en", "name_ar", "price_egp")


class CatalogError(ValueError):
    pass


class Catalog:
    def __init__(self, families: Dict[str, Dict[str, Any]]):
        self.families = families
        self._tiers_by_id: Dict[str, Dict[str, Any]] = {}
        for family in families.values():
            for tier in family["tiers"]:
                if tier["id"] in self._tiers_by_id:
                    raise CatalogError(f"Duplicate tier id '{tier['id']}' across catalog files")
                self._tiers_by_id[tier["id"]] = tier

    def family(self, family_id: str) -> Optional[Dict[str, Any]]:
        return self.families.get(family_id)

    def families_list(self) -> List[Dict[str, Any]]:
        return list(self.families.values())

    def tier(self, tier_id: str) -> Optional[Dict[str, Any]]:
        return self._tiers_by_id.get(tier_id)

    def all_tiers(self) -> List[Dict[str, Any]]:
        return list(self._tiers_by_id.values())

    def tiers_for_family(self, family_id: str) -> List[Dict[str, Any]]:
        family = self.families.get(family_id)
        return list(family["tiers"]) if family else []


def _validate_tier(family_id: str, tier: Dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_TIER_FIELDS if tier.get(f) in (None, "")]
    if missing:
        raise CatalogError(f"{family_id}: tier '{tier.get('id', '?')}' missing required field(s): {missing}")
    price = tier["price_egp"]
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
        raise CatalogError(f"{family_id}: tier '{tier['id']}' has invalid price_egp={price!r}")


def _load_family(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    family_id = data.get("family")
    if not family_id:
        raise CatalogError(f"{path.name}: missing top-level 'family' key")
    tiers = data.get("tiers") or []
    if not tiers:
        raise CatalogError(f"{path.name}: no tiers defined")
    for tier in tiers:
        _validate_tier(family_id, tier)
        tier["family"] = family_id
        tier.setdefault("ussd_code", data.get("default_ussd"))
        tier.setdefault("tax_type", data.get("tax_type", "prepaid"))
    data["tiers"] = tiers
    return data


@functools.lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    families: Dict[str, Dict[str, Any]] = {}
    for filename in FAMILY_FILES:
        path = CATALOG_DIR / filename
        if not path.exists():
            raise CatalogError(f"Missing catalog file: {path}")
        family = _load_family(path)
        families[family["family"]] = family
    return Catalog(families)


@functools.lru_cache(maxsize=1)
def get_tax_rules() -> Dict[str, Any]:
    path = CATALOG_DIR / "tax_rules.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "prepaid" not in rules:
        raise CatalogError("tax_rules.yaml missing required 'prepaid' entry")
    return rules


@functools.lru_cache(maxsize=1)
def get_ussd_services() -> List[Dict[str, Any]]:
    path = CATALOG_DIR / "ussd_codes.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("services", [])
