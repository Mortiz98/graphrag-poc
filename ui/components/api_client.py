from __future__ import annotations

from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


@dataclass
class HealthStatus:
    status: str
    qdrant: str
    nebulagraph: str
    llm: str


@dataclass
class IngestResult:
    filename: str
    chunks_count: int
    triplets_count: int
    status: str


@dataclass
class QueryResult:
    answer: str
    sources: list[dict]
    entities_found: list[str]
    confidence: float


@dataclass
class DocumentInfo:
    id: str
    filename: str
    chunks_count: int
    triplets_count: int


@dataclass
class GraphStats:
    entity_count: int
    edge_count: int
    space: str


@dataclass
class GraphData:
    nodes: list[dict]
    edges: list[dict]


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def health(self) -> HealthStatus:
        with self._client() as c:
            resp = c.get("/health")
            resp.raise_for_status()
            data = resp.json()
            return HealthStatus(
                status=data["status"],
                qdrant=data["services"]["qdrant"],
                nebulagraph=data["services"]["nebulagraph"],
                llm=data["services"]["llm"],
            )

    def ingest(self, filename: str, content: bytes, content_type: str = "application/octet-stream") -> IngestResult:
        with self._client() as c:
            resp = c.post(
                "/ingest",
                files={"file": (filename, content, content_type)},
            )
            resp.raise_for_status()
            data = resp.json()
            return IngestResult(
                filename=data["filename"],
                chunks_count=data["chunks_count"],
                triplets_count=data["triplets_count"],
                status=data["status"],
            )

    def seed(self) -> IngestResult:
        with self._client() as c:
            resp = c.post("/seed")
            resp.raise_for_status()
            data = resp.json()
            return IngestResult(
                filename=data["filename"],
                chunks_count=data["chunks_count"],
                triplets_count=data["triplets_count"],
                status=data["status"],
            )
            return IngestResult(
                filename=data["filename"],
                chunks_count=data["chunks_count"],
                triplets_count=data["triplets_count"],
                status=data["status"],
            )

    def query(self, question: str, top_k: int = 5) -> QueryResult:
        with self._client() as c:
            resp = c.post("/query", json={"question": question, "top_k": top_k})
            resp.raise_for_status()
            data = resp.json()
            return QueryResult(
                answer=data["answer"],
                sources=data["sources"],
                entities_found=data["entities_found"],
                confidence=data["confidence"],
            )

    def list_documents(self) -> list[DocumentInfo]:
        with self._client() as c:
            resp = c.get("/documents")
            resp.raise_for_status()
            return [
                DocumentInfo(
                    id=d["id"],
                    filename=d["filename"],
                    chunks_count=d["chunks_count"],
                    triplets_count=d["triplets_count"],
                )
                for d in resp.json()
            ]

    def delete_document(self, filename: str) -> dict:
        with self._client() as c:
            resp = c.delete(f"/documents/{filename}")
            resp.raise_for_status()
            return resp.json()

    def graph_stats(self) -> GraphStats:
        with self._client() as c:
            resp = c.get("/graph/stats")
            resp.raise_for_status()
            data = resp.json()
            return GraphStats(
                entity_count=data["entity_count"],
                edge_count=data["edge_count"],
                space=data["space"],
            )

    def graph_edges(self) -> GraphData:
        with self._client() as c:
            resp = c.get("/graph/edges")
            resp.raise_for_status()
            data = resp.json()
            return GraphData(nodes=data["nodes"], edges=data["edges"])

    def graph_entities(self) -> list[dict]:
        with self._client() as c:
            resp = c.get("/graph/entities")
            resp.raise_for_status()
            return resp.json()

    def graph_subgraph(self, entity_id: str, hops: int = 1) -> GraphData:
        with self._client() as c:
            resp = c.get("/graph/subgraph", params={"entity": entity_id, "hops": hops})
            resp.raise_for_status()
            data = resp.json()
            return GraphData(nodes=data["nodes"], edges=data["edges"])

    def graph_filters(self) -> dict:
        with self._client() as c:
            resp = c.get("/graph/filters")
            resp.raise_for_status()
            return resp.json()
