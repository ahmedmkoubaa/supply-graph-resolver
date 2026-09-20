"""FastAPI application. The CLI in app.py remains an independent entry point."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .service import LazySupplyGraphService, SupplyGraphRepository

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "ecovadis_practice_supplier_data.csv"


def create_app(repository: SupplyGraphRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="Supply Graph API",
        version="1.0.0",
        description="Read-only API over the resolved EcoVadis supplier dataset.",
    )
    csv_path = Path(os.getenv("SUPPLY_GRAPH_CSV", str(DEFAULT_CSV)))
    app.state.repository = repository or LazySupplyGraphService(csv_path)
    origins = [
        value.strip()
        for value in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
        if value.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def repo(request: Request) -> SupplyGraphRepository:
        return request.app.state.repository

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/summary")
    def summary(request: Request) -> dict:
        return repo(request).summary()

    @app.get("/api/rows")
    def rows(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=200),
        query: str | None = None,
    ) -> dict:
        return repo(request).rows(offset, limit, query)

    @app.get("/api/entities")
    def entities(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=200),
        query: str | None = None,
    ) -> dict:
        return repo(request).resolved_entities(offset, limit, query)

    @app.get("/api/relationships/clean")
    def relationships(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=200),
        query: str | None = None,
    ) -> dict:
        return repo(request).clean_relationships(offset, limit, query)

    @app.get("/api/entities/{entity_id}/graph")
    def graph(entity_id: str, request: Request) -> dict:
        try:
            return repo(request).entity_graph(entity_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown entity: {entity_id}") from exc

    return app


app = create_app()
