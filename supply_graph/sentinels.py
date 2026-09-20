"""Sentinel checks for each pipeline layer. Run before trusting a full export."""

from __future__ import annotations

from .match import confidence_score
from .normalize import normalize_country, normalize_name, normalize_tax_id, parse_mixed_date, normalize_category


SENTINELS = {
    "same_company_casing": {
        "why": "Global Alloys appears in UPPER, Mixed, and lower case; should be one entity.",
        "left": {"core_name": "global alloys", "tax_id": "FR02653954607", "country": "FR", "raw_name": "GLOBAL ALLOYS SARL"},
        "right": {"core_name": "global alloys", "tax_id": None, "country": "FR", "raw_name": "Global  Alloys  SARL"},
        "expect": "merge",
    },
    "typo_same_id": {
        "why": "Pacific Metals vs Pacific Meatls share EIN 11-7347262; typo, not a new company.",
        "left": {"core_name": "pacific metals", "tax_id": "117347262", "country": "US", "raw_name": "Pacific  Metals  Inc."},
        "right": {"core_name": "pacific meatls", "tax_id": "117347262", "country": "US", "raw_name": "Pacific Meatls Inc."},
        "expect": "merge",
    },
    "transposition_same_id": {
        "why": "Meridian vs Meirdian Foundry share tax ID 6936664761.",
        "left": {"core_name": "meridian foundry", "tax_id": "6936664761", "country": "VN", "raw_name": "Meridian Foundry Co., Ltd."},
        "right": {"core_name": "meirdian foundry", "tax_id": "6936664761", "country": "VN", "raw_name": "Meirdian Foundry Co., Ltd."},
        "expect": "merge",
    },
    "false_positive_risk": {
        "why": "Horizon Alloys vs Global Alloys both '* Alloys SARL' but different VAT + country.",
        "left": {"core_name": "horizon alloys", "tax_id": "381866192115924", "country": "MA", "raw_name": "Horizon Alloys SARL"},
        "right": {"core_name": "global alloys", "tax_id": "FR02653954607", "country": "FR", "raw_name": "GLOBAL ALLOYS SARL"},
        "expect": "distinct",
    },
}


def print_sentinels() -> None:
    print("=== sentinel normalization ===")
    print("  Maroc ->", normalize_country("Maroc"), "| Türkiye ->", normalize_country("Türkiye"), "| Espagne ->", normalize_country("Espagne"))
    print("  tax FR02653954607 ->", normalize_tax_id("FR02653954607"), "| 11-7347262 ->", normalize_tax_id("11-7347262"))
    print("  name GLOBAL ALLOYS SARL ->", normalize_name("GLOBAL ALLOYS SARL"))
    print("  name Pacific  Metals  Inc.  ->", normalize_name("Pacific  Metals  Inc. "))
    print("  name Highland Steel Sp. z .oo. ->", normalize_name("Highland Steel Sp. z .oo."))
    print("  dates:", parse_mixed_date("12-03-2023"), parse_mixed_date("28/03/2023"), parse_mixed_date("2024-02-04"), parse_mixed_date("03-16-2022"))
    print("  rel types:", normalize_category("raw material"), normalize_category("RAW_MATERIAL"), normalize_category("Raw Material"))
    print()
    print("=== sentinel match scores ===")
    for key, spec in SENTINELS.items():
        result = confidence_score(spec["left"], spec["right"])
        ok = result["decision"] == spec["expect"]
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {key}: confidence={result['confidence']} decision={result['decision']} (expect {spec['expect']})")
        print(f"        {spec['why']}")
        if not ok:
            print(f"        details={result}")
