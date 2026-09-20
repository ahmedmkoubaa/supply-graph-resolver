"""parse(): sniff encoding/delimiter, then load the relationship CSV as-is."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = [
    "row_id",
    "source_system",
    "reported_by",
    "reported_by_tax_id",
    "reported_by_country",
    "declared_supplier",
    "declared_supplier_tax_id",
    "declared_supplier_country",
    "relationship_type",
    "last_updated",
    "notes",
]


def sniff_csv(path: Path) -> dict:
    """Do not assume UTF-8/comma until we have checked the file."""
    raw = path.read_bytes()
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    sample = raw[:4096].decode(encoding, errors="replace")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return {"encoding": encoding, "delimiter": delimiter, "nbytes": len(raw)}


def parse(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    meta = sniff_csv(path)
    df = pd.read_csv(
        path,
        encoding=meta["encoding"],
        delimiter=meta["delimiter"],
        dtype=str,
        keep_default_na=True,
    )
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing expected columns {missing}. Found: {list(df.columns)}")
    df["_source_file"] = str(path)
    df["_parse_encoding"] = meta["encoding"]
    df["_parse_delimiter"] = meta["delimiter"]
    # Drop trailing empty lines that pandas still materializes as NaN rows.
    name_cols = [c for c in ("reported_by", "declared_supplier") if c in df.columns]
    if name_cols:
        df = df.dropna(how="all", subset=name_cols)
        df = df[df[name_cols].apply(lambda r: any(str(v).strip() not in ("", "nan") for v in r), axis=1)]
    df = df.reset_index(drop=True)
    # Keep original row position so we can point at sentinel cases later.
    df["_file_line"] = range(2, len(df) + 2)
    return df


def profile(df: pd.DataFrame) -> str:
    lines = [
        f"rows: {len(df)}",
        f"columns: {list(df.columns)}",
        "nulls per column:",
    ]
    for col in df.columns:
        if col.startswith("_"):
            continue
        n = df[col].isna().sum() + (df[col].astype(str).str.strip() == "").sum()
        lines.append(f"  {col}: {int(n)}")
    lines.append("sample:")
    lines.append(df.drop(columns=[c for c in df.columns if c.startswith("_")]).head(10).to_string(index=False))
    return "\n".join(lines)
