from __future__ import annotations

import json
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
class AgentQueryResult:
    answer: str
    session_id: str


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


@dataclass
class GraphFilters:
    entity_types: list[str]
    relation_types: list[str]
    source_docs: list[str]


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

    def ingest_with_metadata(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        system: str = "support",
        tenant_id: str | None = None,
        account_id: str | None = None,
        product: str | None = None,
        version: str | None = None,
        severity: str | None = None,
        channel: str | None = None,
    ) -> IngestResult:
        with self._client() as c:
            data: dict = {"system": system}
            if tenant_id:
                data["tenant_id"] = tenant_id
            if account_id:
                data["account_id"] = account_id
            if product:
                data["product"] = product
            if version:
                data["version"] = version
            if severity:
                data["severity"] = severity
            if channel:
                data["channel"] = channel
            resp = c.post(
                "/ingest",
                data=data,
                files={"file": (filename, content, content_type)},
            )
            resp.raise_for_status()
            resp_data = resp.json()
            return IngestResult(
                filename=resp_data["filename"],
                chunks_count=resp_data["chunks_count"],
                triplets_count=resp_data["triplets_count"],
                status=resp_data["status"],
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

    def agent_query(
        self,
        question: str,
        agent: str = "support",
        session_id: str | None = None,
        account_id: str | None = None,
    ) -> AgentQueryResult:
        with self._client() as c:
            if agent == "am":
                payload = {"question": question, "user_id": "streamlit_user"}
                if account_id:
                    payload["account_id"] = account_id
                if session_id:
                    payload["session_id"] = session_id
                resp = c.post("/agents/am/query", params=payload)
            else:
                payload = {"question": question, "user_id": "streamlit_user"}
                if session_id:
                    payload["session_id"] = session_id
                resp = c.post("/agents/support/query", params=payload)
            resp.raise_for_status()
            data = resp.json()
            return AgentQueryResult(
                answer=data.get("answer", ""),
                session_id=data.get("session_id", ""),
            )

    def agent_query_stream(
        self,
        question: str,
        agent: str = "support",
        session_id: str | None = None,
        account_id: str | None = None,
    ):
        with self._client() as c:
            if agent == "am":
                params = {"question": question, "user_id": "streamlit_user"}
                if account_id:
                    params["account_id"] = account_id
                if session_id:
                    params["session_id"] = session_id
                url = "/agents/am/query/stream"
            else:
                params = {"question": question, "user_id": "streamlit_user"}
                if session_id:
                    params["session_id"] = session_id
                url = "/agents/support/query/stream"

            with c.stream("POST", url, params=params) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line and line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                            yield event
                            if event.get("type") == "done":
                                break
                        except json.JSONDecodeError:
                            if data_str == "[DONE]":
                                break
                            yield {"type": "token", "content": data_str}

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

    def graph_filters(self) -> GraphFilters:
        with self._client() as c:
            resp = c.get("/graph/filters")
            resp.raise_for_status()
            data = resp.json()
            return GraphFilters(
                entity_types=data["entity_types"],
                relation_types=data["relation_types"],
                source_docs=data["source_docs"],
            )
