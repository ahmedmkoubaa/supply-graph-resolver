"""normalize(): canonicalize names, IDs, countries, dates, categories.

A missing tax ID is missing data, not evidence that two companies are different,
and not evidence that a relationship does not exist.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import pandas as pd
import pycountry

# Longest-first so "pvt ltd" is not reduced to leftover "pvt" + suffix "ltd".
LEGAL_SUFFIXES = [
    "sp z oo",
    "sp z o o",
    "sp zoo",
    "sp z o.o",
    "pvt ltd",
    "private limited",
    "co ltd",
    "s a",
    "s l",
    "sarl",
    "gmbh",
    "ltd",
    "inc",
    "corp",
    "llc",
    "plc",
    "ag",
    "nv",
    "bv",
    "oy",
    "ab",
    "as",  # A.Ş. after accent stripping if kept as one token
    "a s",  # A.Ş. after punctuation-to-space ("a.ş." -> "a s")
    "sa",
    "sl",
]

# Aliases seen in this file (Maroc, Türkiye, VN) plus common English/ISO forms.
COUNTRY_ALIASES = {
    "france": "FR",
    "fr": "FR",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "vietnam": "VN",
    "vn": "VN",
    "poland": "PL",
    "pl": "PL",
    "india": "IN",
    "in": "IN",
    "morocco": "MA",
    "maroc": "MA",
    "ma": "MA",
    "turkey": "TR",
    "turkiye": "TR",
    "tr": "TR",
    "spain": "ES",
    "espana": "ES",
    "es": "ES",
}


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def blank_to_none(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = collapse_ws(str(value))
    if text == "" or text.lower() in {"nan", "none", "null", "n/a", "na"}:
        return None
    return text


def normalize_name(raw: str | None) -> dict:
    """Lowercase, strip accents/punct, peel legal suffixes into metadata."""
    original = blank_to_none(raw)
    if original is None:
        return {"raw_name": None, "core_name": None, "legal_suffix": None, "norm_name": None}

    lowered = collapse_ws(strip_accents(original).lower())
    # Keep letters/digits as tokens; punctuation becomes spaces ("A.Ş." -> "a s", "Sp. z .oo." -> "sp z oo").
    alnum = collapse_ws(re.sub(r"[^a-z0-9]+", " ", lowered))
    tokens = alnum.split()
    suffixes: list[str] = []
    changed = True
    while tokens and changed:
        changed = False
        for n in range(min(4, len(tokens)), 0, -1):
            candidate = " ".join(tokens[-n:])
            if candidate in LEGAL_SUFFIXES:
                suffixes.insert(0, candidate)
                tokens = tokens[:-n]
                changed = True
                break
    core = " ".join(tokens) or alnum
    suffix = " ".join(suffixes) or None
    return {
        "raw_name": original,
        "core_name": core,
        "legal_suffix": suffix,
        "norm_name": core,  # matching key: suffix is metadata, not identity
    }


def normalize_tax_id(raw: str | None) -> str | None:
    text = blank_to_none(raw)
    if text is None:
        return None
    # Strip spaces, dashes, dots, slashes — keep A-Z0-9 only.
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    return cleaned or None


def normalize_country(raw: str | None) -> str | None:
    text = blank_to_none(raw)
    if text is None:
        return None
    key = collapse_ws(strip_accents(text).lower())
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if len(key) == 2:
        hit = pycountry.countries.get(alpha_2=key.upper())
        if hit:
            return hit.alpha_2
    if len(key) == 3:
        hit = pycountry.countries.get(alpha_3=key.upper())
        if hit:
            return hit.alpha_2
    try:
        hit = pycountry.countries.lookup(text)
        return hit.alpha_2
    except LookupError:
        return None  # unmapped country is missing data, not a drop reason


def parse_mixed_date(raw: str | None) -> str | None:
    """ISO date string, or None.

    The file mixes YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, and at least one US
    MM-DD-YYYY (03-16-2022). When both numbers are <= 12 we prefer day-first
    because the rest of the file is European-sourced.
    """
    text = blank_to_none(raw)
    if text is None:
        return None
    text = text.replace(".", "-").strip()

    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        y, m, d = map(int, iso.groups())
        return _iso(y, m, d)

    mdy_or_dmy = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", text)
    if mdy_or_dmy:
        a, b, y = map(int, mdy_or_dmy.groups())
        if a > 12 and b <= 12:  # 28/03/2023
            d, m = a, b
        elif b > 12 and a <= 12:  # 03-16-2022
            m, d = a, b
        else:
            d, m = a, b  # ambiguous: day-first
        return _iso(y, m, d)

    try:
        dt = pd.to_datetime(text, format="mixed", dayfirst=True)
        if pd.isna(dt):
            return None
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_category(raw: str | None) -> str | None:
    text = blank_to_none(raw)
    if text is None:
        return None
    lowered = collapse_ws(strip_accents(text).lower())
    snake = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return snake or None


def explode_mentions(df: pd.DataFrame) -> pd.DataFrame:
    """Two entity mentions per relationship row: reporter (customer) and supplier."""
    rows = []
    for rec in df.to_dict(orient="records"):
        for role, name_col, id_col, country_col in (
            ("customer", "reported_by", "reported_by_tax_id", "reported_by_country"),
            ("supplier", "declared_supplier", "declared_supplier_tax_id", "declared_supplier_country"),
        ):
            name_bits = normalize_name(rec.get(name_col))
            rows.append(
                {
                    "row_id": rec.get("row_id"),
                    "file_line": rec.get("_file_line"),
                    "source_system": rec.get("source_system"),
                    "role": role,
                    "raw_name": name_bits["raw_name"],
                    "core_name": name_bits["core_name"],
                    "legal_suffix": name_bits["legal_suffix"],
                    "norm_name": name_bits["norm_name"],
                    "tax_id": normalize_tax_id(rec.get(id_col)),
                    "country": normalize_country(rec.get(country_col)),
                    "raw_tax_id": blank_to_none(rec.get(id_col)),
                    "raw_country": blank_to_none(rec.get(country_col)),
                }
            )
    return pd.DataFrame(rows)


def normalize_relationships(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for side, name_col, id_col, country_col in (
        ("customer", "reported_by", "reported_by_tax_id", "reported_by_country"),
        ("supplier", "declared_supplier", "declared_supplier_tax_id", "declared_supplier_country"),
    ):
        names = out[name_col].map(normalize_name)
        out[f"{side}_raw_name"] = names.map(lambda d: d["raw_name"])
        out[f"{side}_core_name"] = names.map(lambda d: d["core_name"])
        out[f"{side}_suffix"] = names.map(lambda d: d["legal_suffix"])
        out[f"{side}_tax_id"] = out[id_col].map(normalize_tax_id)
        out[f"{side}_country"] = out[country_col].map(normalize_country)
    out["relationship_type_norm"] = out["relationship_type"].map(normalize_category)
    out["last_updated_iso"] = out["last_updated"].map(parse_mixed_date)
    return out
