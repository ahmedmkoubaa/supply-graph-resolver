"""Lazy, read-only application service built from the existing pipeline layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable

import pandas as pd

from supply_graph.block import block
from supply_graph.export import clean_entities_frame, clean_relationships_frame, json_safe, to_payload
from supply_graph.graph import assign_tiers, build_graph, chain_subgraph, detect_cycles
from supply_graph.match import match
from supply_graph.normalize import explode_mentions, normalize_relationships
from supply_graph.parse import parse
from supply_graph.resolve import resolve


@dataclass
class Page:
    items: list[dict]
    total: int
    offset: int
    limit: int

    def as_dict(self) -> dict:
        return json_safe(
            {"items": self.items, "total": self.total, "offset": self.offset, "limit": self.limit}
        )


class SupplyGraphRepository:
    """Resolved dataset used only after a request needs resolved data."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        raw = parse(self.csv_path)
        relationships = normalize_relationships(raw)
        mentions = explode_mentions(raw)
        mentions = mentions[mentions["core_name"].notna()].reset_index(drop=True)
        scored = match(block(mentions))
        entities, flagged, mentions = resolve(mentions, scored)

        self.raw = raw.drop(columns=[c for c in raw.columns if c.startswith("_")])
        self.relationships = clean_relationships_frame(relationships, mentions, entities)
        self.entities = entities
        self.entities_clean = clean_entities_frame(entities)
        self.flagged = flagged
        self.graph = build_graph(relationships, mentions, entities)
        self.cycles = detect_cycles(self.graph)

    def summary(self) -> dict:
        return {
            "source_file": self.csv_path.name,
            "rows": len(self.raw),
            "entities": len(self.entities),
            "relationships": self.graph.number_of_edges(),
            "flagged_for_review": len(self.flagged),
            "cycles": len(self.cycles),
        }

    def rows(self, offset: int, limit: int, query: str | None = None) -> dict:
        return self._page(self.raw, offset, limit, query).as_dict()

    def clean_relationships(self, offset: int, limit: int, query: str | None = None) -> dict:
        return self._page(self.relationships, offset, limit, query).as_dict()

    def resolved_entities(self, offset: int, limit: int, query: str | None = None) -> dict:
        return self._page(self.entities_clean, offset, limit, query).as_dict()

    def entity_graph(self, entity_id: str) -> dict:
        if entity_id not in self.graph:
            raise KeyError(entity_id)
        tiers = assign_tiers(self.graph, entity_id)
        graph = chain_subgraph(self.graph, entity_id, tiers)
        relevant_cycles = [cycle for cycle in self.cycles if set(cycle).issubset(graph.nodes)]
        # Review candidates are dataset-level diagnostics and can be large. They are counted in
        # /summary rather than repeated in every graph response.
        return to_payload(
            graph,
            self.entities,
            [],
            tiers,
            entity_id,
            relevant_cycles,
            n_raw_rows=len(self.raw),
        )

    @staticmethod
    def _page(
        frame: pd.DataFrame, offset: int, limit: int, query: str | None = None
    ) -> Page:
        filtered = frame
        if query and query.strip():
            needle = query.strip()
            searchable = frame.fillna("").astype(str)
            mask = searchable.apply(
                lambda column: column.str.contains(needle, case=False, regex=False)
            ).any(axis=1)
            filtered = frame.loc[mask]
            if "mention_count" in filtered.columns:
                filtered = filtered.sort_values("mention_count", ascending=False)
        items = filtered.iloc[offset : offset + limit].to_dict(orient="records")
        return Page(items=items, total=len(filtered), offset=offset, limit=limit)


class LazySupplyGraphService:
    """Build on request, retain response payloads, and release heavy working state."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self._response_cache: dict[tuple, dict] = {}
        self._cache_lock = Lock()

    def summary(self) -> dict:
        def load() -> dict:
            # The initial page only needs a row count. Parsing this small source is cheap and the
            # frame is discarded after the response; matching and graph construction still wait.
            raw = parse(self.csv_path)
            return {
                "source_file": self.csv_path.name,
                "rows": len(raw),
                "entities": None,
                "relationships": None,
                "flagged_for_review": None,
                "cycles": None,
            }

        return self._cached(("summary",), load)

    def rows(self, offset: int, limit: int, query: str | None = None) -> dict:
        def load() -> dict:
            raw = parse(self.csv_path)
            raw = raw.drop(columns=[c for c in raw.columns if c.startswith("_")])
            return SupplyGraphRepository._page(raw, offset, limit, query).as_dict()

        return self._cached(("rows", offset, limit, query), load)

    def clean_relationships(self, offset: int, limit: int, query: str | None = None) -> dict:
        return self._cached(
            ("clean", offset, limit, query),
            lambda: SupplyGraphRepository(self.csv_path).clean_relationships(offset, limit, query),
        )

    def resolved_entities(self, offset: int, limit: int, query: str | None = None) -> dict:
        return self._cached(
            ("entities", offset, limit, query),
            lambda: SupplyGraphRepository(self.csv_path).resolved_entities(offset, limit, query),
        )

    def entity_graph(self, entity_id: str) -> dict:
        return self._cached(
            ("graph", entity_id),
            lambda: SupplyGraphRepository(self.csv_path).entity_graph(entity_id),
        )

    def _cached(self, key: tuple, load: Callable[[], dict]) -> dict:
        # Include source freshness so replacing the CSV naturally bypasses old responses.
        cache_key = (self.csv_path.stat().st_mtime_ns, *key)
        cached = self._response_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._cache_lock:
            cached = self._response_cache.get(cache_key)
            if cached is None:
                cached = load()
                self._response_cache[cache_key] = cached
        return cached
