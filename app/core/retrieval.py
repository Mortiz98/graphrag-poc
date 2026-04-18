"""Retrieval engine abstraction layer for vector and graph search.

This module provides a unified interface for searching across vector stores
and knowledge graphs, with support for structured logging and extensibility.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.core import logger
from app.core.embeddings import get_embeddings
from app.core.graph import get_nebula_session
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client
from app.models.graph_schema import EDGE_RELATED_TO, SPACE_NAME, TAG_ENTITY, escape_ngql

TRACES_DIR = Path("traces")
TRACES_DIR.mkdir(exist_ok=True)


@dataclass
class SearchResult:
    """A single search result from vector or graph retrieval."""

    subject: str
    predicate: str
    object: str
    score: float
    source_doc: str
    chunk_id: str
    subject_id: str
    object_id: str
    subject_type: str = ""
    object_type: str = ""
    metadata: dict = field(default_factory=dict)
    retrieval_method: str = ""
    scope: dict = field(default_factory=dict)


@dataclass
class RetrievalTrace:
    """Structured trace of a retrieval operation for observability."""

    query: str
    phase: str
    candidates: list[SearchResult]
    metadata: dict = field(default_factory=dict)
    trace_id: str = ""
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "query": self.query[:200],
            "phase": self.phase,
            "candidate_count": len(self.candidates),
            "top_scores": [c.score for c in self.candidates[:5]] if self.candidates else [],
            "metadata": self.metadata,
        }


def persist_trace(trace: RetrievalTrace) -> None:
    if not trace.trace_id:
        return
    try:
        trace_file = TRACES_DIR / f"{trace.trace_id}.jsonl"
        entry = trace.to_dict()
        with open(trace_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning("trace_persist_failed", error=str(e))


class RetrievalEngine:
    """Unified retrieval engine for vector and graph search.

    This class abstracts the underlying storage backends (Qdrant, NebulaGraph)
    and provides a consistent interface for retrieval operations.
    """

    def __init__(self):
        self.settings = get_settings()
        self._vector_client = None
        self._embeddings = None

    def _get_vector_client(self):
        """Lazy initialization of Qdrant client."""
        if self._vector_client is None:
            self._vector_client = get_qdrant_client()
            ensure_collection_exists(self._vector_client, self.settings.qdrant_collection_name)
        return self._vector_client

    def _get_embeddings(self):
        """Lazy initialization of embeddings model."""
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    def _build_filter(
        self,
        filters: dict | None,
        scope: dict | None,
        active_only: bool = False,
    ) -> object | None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        conditions: list = []
        if scope:
            for key, value in scope.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        if filters:
            for key, value in filters.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        if active_only:
            conditions.append(FieldCondition(key="is_active", match=MatchValue(value=True)))
        return Filter(must=conditions) if conditions else None

    def search_dense(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        filters: dict | None = None,
        scope: dict | None = None,
        active_only: bool = False,
    ) -> list[SearchResult]:
        client = self._get_vector_client()
        embeddings = self._get_embeddings()

        query_vector = embeddings.embed_query(query)
        query_filter = self._build_filter(filters, scope, active_only=active_only)

        results = client.query_points(
            collection_name=self.settings.qdrant_collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=min_score if min_score > 0 else None,
        )

        search_results = []
        for point in results.points:
            result = SearchResult(
                subject=point.payload.get("subject", ""),
                predicate=point.payload.get("predicate", ""),
                object=point.payload.get("object", ""),
                score=point.score,
                source_doc=point.payload.get("source_doc", ""),
                chunk_id=point.payload.get("chunk_id", ""),
                subject_id=point.payload.get("subject_id", ""),
                object_id=point.payload.get("object_id", ""),
                subject_type=point.payload.get("subject_type", ""),
                object_type=point.payload.get("object_type", ""),
                metadata={
                    k: v
                    for k, v in point.payload.items()
                    if k
                    not in [
                        "subject",
                        "predicate",
                        "object",
                        "subject_id",
                        "object_id",
                        "chunk_id",
                        "source_doc",
                        "subject_type",
                        "object_type",
                    ]
                },
                retrieval_method="dense",
                scope=scope or {},
            )
            search_results.append(result)

        logger.info(
            "vector_search_completed",
            query=query[:50],
            results=len(search_results),
            min_score=min_score,
            filters=filters,
            scope=scope,
            top_scores=[r.score for r in search_results[:3]],
        )

        return search_results

    def search_sparse(
        self,
        query: str,
        top_k: int = 5,
        scope: dict | None = None,
        filters: dict | None = None,
        active_only: bool = False,
    ) -> list[SearchResult]:
        logger.info("search_sparse_fallback_to_dense", query=query[:50])
        return self.search_dense(query=query, top_k=top_k, filters=filters, scope=scope, active_only=active_only)

    def search_hybrid(
        self,
        query: str,
        top_k: int = 5,
        scope: dict | None = None,
        filters: dict | None = None,
        active_only: bool = False,
    ) -> list[SearchResult]:
        logger.info("search_hybrid_fallback_to_dense", query=query[:50])
        return self.search_dense(query=query, top_k=top_k, filters=filters, scope=scope, active_only=active_only)

    def rerank(
        self,
        candidates: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        logger.info("rerank_noop_passthrough", query=query[:50], candidates=len(candidates))
        return candidates

    def search_by_filter(
        self,
        top_k: int = 50,
        filters: dict | None = None,
        scope: dict | None = None,
        active_only: bool = False,
    ) -> list[SearchResult]:
        client = self._get_vector_client()
        query_filter = self._build_filter(filters, scope, active_only=active_only)

        results = client.scroll(
            collection_name=self.settings.qdrant_collection_name,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
            scroll_filter=query_filter,
        )

        search_results = []
        for point in results[0]:
            search_results.append(
                SearchResult(
                    subject=point.payload.get("subject", ""),
                    predicate=point.payload.get("predicate", ""),
                    object=point.payload.get("object", ""),
                    score=1.0,
                    source_doc=point.payload.get("source_doc", ""),
                    chunk_id=point.payload.get("chunk_id", ""),
                    subject_id=point.payload.get("subject_id", ""),
                    object_id=point.payload.get("object_id", ""),
                    subject_type=point.payload.get("subject_type", ""),
                    object_type=point.payload.get("object_type", ""),
                    metadata={
                        k: v
                        for k, v in point.payload.items()
                        if k
                        not in [
                            "subject",
                            "predicate",
                            "object",
                            "subject_id",
                            "object_id",
                            "chunk_id",
                            "source_doc",
                            "subject_type",
                            "object_type",
                        ]
                    },
                    retrieval_method="filter",
                    scope=scope or {},
                )
            )

        logger.info(
            "filter_search_completed",
            results=len(search_results),
            filters=filters,
            scope=scope,
            active_only=active_only,
        )
        return search_results

    def get_supporting_chunks(self, ids: list[str]) -> list[SearchResult]:
        if not ids:
            return []
        client = self._get_vector_client()

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = Filter(must=[FieldCondition(key="chunk_id", match=MatchValue(value=id_)) for id_ in ids])

        results = client.scroll(
            collection_name=self.settings.qdrant_collection_name,
            limit=len(ids) * 20,
            with_payload=True,
            with_vectors=False,
            scroll_filter=query_filter,
        )

        search_results = []
        for point in results[0]:
            search_results.append(
                SearchResult(
                    subject=point.payload.get("subject", ""),
                    predicate=point.payload.get("predicate", ""),
                    object=point.payload.get("object", ""),
                    score=1.0,
                    source_doc=point.payload.get("source_doc", ""),
                    chunk_id=point.payload.get("chunk_id", ""),
                    subject_id=point.payload.get("subject_id", ""),
                    object_id=point.payload.get("object_id", ""),
                    subject_type=point.payload.get("subject_type", ""),
                    object_type=point.payload.get("object_type", ""),
                    metadata=point.payload,
                    retrieval_method="chunk_lookup",
                )
            )

        logger.info("supporting_chunks_retrieved", requested=len(ids), found=len(search_results))
        return search_results

    def expand_from_graph(
        self,
        entity_ids: list[str],
        hops: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Expand context by traversing the knowledge graph from given entities.

        Args:
            entity_ids: List of entity IDs to start traversal from
            hops: Number of hops to traverse (currently only 1 is fully supported)
            relation_types: Optional list of relation types to filter (not yet implemented)

        Returns:
            List of SearchResult objects from graph traversal
        """
        if not entity_ids:
            return []

        graph_results = []
        seen_edges = set()

        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            for entity_id in entity_ids:
                safe_id = escape_ngql(entity_id)

                # Traverse outgoing and incoming edges
                for direction in ["out", "in"]:
                    if direction == "out":
                        query = (
                            f'GO FROM "{safe_id}" OVER {EDGE_RELATED_TO} '
                            f"YIELD {EDGE_RELATED_TO}._src AS src, "
                            f"{EDGE_RELATED_TO}._dst AS dst, "
                            f"{EDGE_RELATED_TO}.relation AS relation"
                        )
                    else:
                        query = (
                            f'GO FROM "{safe_id}" OVER {EDGE_RELATED_TO} REVERSELY '
                            f"YIELD {EDGE_RELATED_TO}._src AS src, "
                            f"{EDGE_RELATED_TO}._dst AS dst, "
                            f"{EDGE_RELATED_TO}.relation AS relation"
                        )

                    result = session.execute(query)
                    if not result.is_succeeded():
                        continue

                    for row in result.rows():
                        try:
                            src_id_bytes = row.values[0].get_sVal()
                            dst_id_bytes = row.values[1].get_sVal()
                            rel_bytes = row.values[2].get_sVal()

                            src_id = src_id_bytes.decode() if isinstance(src_id_bytes, bytes) else str(src_id_bytes)
                            dst_id = dst_id_bytes.decode() if isinstance(dst_id_bytes, bytes) else str(dst_id_bytes)
                            relation = rel_bytes.decode() if isinstance(rel_bytes, bytes) else str(rel_bytes)

                            edge_key = f"{src_id}-{relation}-{dst_id}"
                            if edge_key in seen_edges:
                                continue
                            seen_edges.add(edge_key)

                            # Get entity names from vertex properties
                            src_name = src_id.replace("_", " ")
                            dst_name = dst_id.replace("_", " ")

                            graph_results.append(
                                SearchResult(
                                    subject=src_name,
                                    predicate=relation,
                                    object=dst_name,
                                    score=1.0,  # Graph edges have uniform weight
                                    source_doc="",
                                    chunk_id="",
                                    subject_id=src_id,
                                    object_id=dst_id,
                                    metadata={"from_graph": True},
                                )
                            )
                        except Exception:
                            continue

                # Fetch entity names for better display
                entity_names_query = f'FETCH PROP ON {TAG_ENTITY} "{safe_id}" YIELD vertex AS v'
                result = session.execute(entity_names_query)
                if result.is_succeeded():
                    for row in result.rows():
                        try:
                            v = row.values[0]
                            vertex = v.get_vVal()
                            vid_bytes = vertex.vid.get_sVal()
                            vid_str = vid_bytes.decode() if isinstance(vid_bytes, bytes) else str(vid_bytes)
                            for tag in vertex.tags:
                                tag_name = tag.name.decode() if isinstance(tag.name, bytes) else tag.name
                                if tag_name == "entity":
                                    name = tag.props.get(b"name")
                                    if name and name.get_sVal():
                                        name_str = name.get_sVal().decode()
                                        for gr in graph_results:
                                            if gr.subject_id == vid_str:
                                                gr.subject = name_str
                                            if gr.object_id == vid_str:
                                                gr.object = name_str
                        except Exception:
                            continue

        logger.info(
            "graph_expansion_completed",
            entities=len(entity_ids),
            triplets=len(graph_results),
            hops=hops,
        )

        return graph_results

    def fuse_results(
        self,
        vector_results: list[SearchResult],
        graph_results: list[SearchResult],
        max_results: int = 20,
    ) -> tuple[list[SearchResult], list[SearchResult]]:
        """Fuse vector and graph results, removing duplicates.

        Args:
            vector_results: Results from vector search
            graph_results: Results from graph expansion
            max_results: Maximum total results to return

        Returns:
            Tuple of (fused_results, all_unique_results)
        """
        seen_keys = set()
        fused = []

        # Process vector results first (they have scores)
        for r in vector_results:
            key = f"{r.subject}|{r.predicate}|{r.object}".lower()
            if key not in seen_keys:
                seen_keys.add(key)
                fused.append(r)

        # Add graph results
        for r in graph_results:
            key = f"{r.subject}|{r.predicate}|{r.object}".lower()
            if key not in seen_keys:
                seen_keys.add(key)
                fused.append(r)

        # Limit results
        fused = fused[:max_results]

        logger.info(
            "context_fusion_completed",
            vector_count=len(vector_results),
            graph_count=len(graph_results),
            fused_count=len(fused),
            unique_keys=len(seen_keys),
        )

        return fused, vector_results + graph_results

    def log_trace(
        self,
        query: str,
        phase: str,
        candidates: list[SearchResult],
        metadata: dict | None = None,
        trace_id: str = "",
        session_id: str = "",
    ) -> None:
        if not trace_id:
            trace_id = str(uuid4())[:8]
        trace = RetrievalTrace(
            query=query,
            phase=phase,
            candidates=candidates,
            metadata=metadata or {},
            trace_id=trace_id,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "retrieval_trace",
            query=trace.query[:50],
            phase=trace.phase,
            candidate_count=len(trace.candidates),
            top_scores=[c.score for c in trace.candidates[:3]] if trace.candidates else [],
            metadata=trace.metadata,
            trace_id=trace.trace_id,
            session_id=trace.session_id,
        )

        persist_trace(trace)


_retrieval_engine: RetrievalEngine | None = None
_engine_lock = threading.Lock()


def get_retrieval_engine() -> RetrievalEngine:
    """Get or create the global retrieval engine instance (thread-safe)."""
    global _retrieval_engine
    if _retrieval_engine is not None:
        return _retrieval_engine
    with _engine_lock:
        if _retrieval_engine is not None:
            return _retrieval_engine
        _retrieval_engine = RetrievalEngine()
        return _retrieval_engine


def reset_retrieval_engine() -> None:
    """Reset the global retrieval engine instance (for testing)."""
    global _retrieval_engine
    with _engine_lock:
        _retrieval_engine = None
