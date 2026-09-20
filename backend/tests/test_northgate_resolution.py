import pandas as pd

from supply_graph.block import block
from supply_graph.match import match
from supply_graph.normalize import explode_mentions, normalize_country, normalize_tax_id
from supply_graph.resolve import resolve


def _raw_row(row_id, tax_id, country):
    return {
        "row_id": str(row_id),
        "_file_line": row_id + 1,
        "source_system": "test",
        "reported_by": "NorthGate Textiles S.A.",
        "reported_by_tax_id": tax_id,
        "reported_by_country": country,
        "declared_supplier": f"Supplier {row_id}",
        "declared_supplier_tax_id": f"SUP{row_id}",
        "declared_supplier_country": "FR",
    }


def test_country_and_vat_prefix_variants_normalize_consistently():
    assert normalize_country("Espagne") == "ES"
    assert normalize_tax_id("ES60227680G") == normalize_tax_id("60227680G") == "60227680G"


def _resolve_customers(rows):
    mentions = explode_mentions(pd.DataFrame(rows))
    mentions = mentions[mentions["role"] == "customer"].reset_index(drop=True)
    return resolve(mentions, match(block(mentions)))


def test_northgate_variants_resolve_to_one_entity():
    raw = pd.DataFrame(
        [
            _raw_row(1, "ES60227680G", "Espagne"),
            _raw_row(2, "60227680G", "ES"),
            _raw_row(3, "60227680G", None),
            _raw_row(4, None, "Espagne"),
        ]
    )
    entities, _, resolved_mentions = _resolve_customers(raw.to_dict(orient="records"))

    northgate_ids = resolved_mentions["entity_id"].unique()
    assert len(northgate_ids) == 1
    assert entities.loc[entities["entity_id"] == northgate_ids[0], "mention_count"].iloc[0] == 4


def test_exact_names_with_conflicting_tax_ids_and_countries_stay_distinct():
    _, _, resolved_mentions = _resolve_customers(
        [
            _raw_row(1, "ES60227680G", "ES"),
            _raw_row(2, "DIFFERENT1", "FR"),
        ]
    )

    assert resolved_mentions["entity_id"].nunique() == 2
