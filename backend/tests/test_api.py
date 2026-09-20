from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.service import SupplyGraphRepository


@pytest.fixture(scope="module")
def repository() -> SupplyGraphRepository:
    csv_path = Path(__file__).resolve().parents[2] / "sentinel-supply-chain.csv"
    return SupplyGraphRepository(csv_path)


@pytest.fixture(scope="module")
def client(repository: SupplyGraphRepository):
    with TestClient(create_app(repository)) as value:
        yield value


def test_tables_are_paginated_and_searchable(client: TestClient):
    response = client.get("/api/rows", params={"limit": 2, "query": "Pacific"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_entity_graph_returns_every_upstream_tier(client: TestClient):
    entities = client.get("/api/entities", params={"query": "Global Alloys"}).json()["items"]
    root = entities[0]

    response = client.get(f"/api/entities/{root['entity_id']}/graph")
    assert response.status_code == 200
    graph = response.json()
    assert graph["root_entity_id"] == root["entity_id"]
    assert any(node["tier"] == 1 for node in graph["nodes"])
    assert all(node["tier"] is not None for node in graph["nodes"])
    assert all(edge["target"] in {node["entity_id"] for node in graph["nodes"]} for edge in graph["edges"])


def test_unknown_entity_is_404(client: TestClient):
    response = client.get("/api/entities/DOES_NOT_EXIST/graph")
    assert response.status_code == 404
