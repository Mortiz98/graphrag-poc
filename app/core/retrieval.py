"""Retrieval engine: dense, sparse (BM25-like), and hybrid search over Qdrant."""

import re
from collections import Counter

from qdrant_client.models import QueryResponse, SparseVector

from app.config import get_settings
from app.core import logger
from app.core.embeddings import get_embeddings
from app.core.vectorstore import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, ensure_collection_exists, get_qdrant_client


def _tokenize(text: str) -> list[str]:
    """Tokenize text into words for BM25-like sparse vector generation."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if t]


def text_to_sparse_vector(text: str) -> SparseVector:
    """Convert text to a BM25-like sparse vector using term frequencies.

    Tokens are mapped to integer indices via a consistent hash function.
    Values are term frequencies (TF). Qdrant's IDF modifier handles the
    inverse document frequency component at query time.
    """
    tokens = _tokenize(text)
    if not tokens:
        return SparseVector(indices=[], values=[])

    tf = Counter(tokens)
    indices = []
    values = []
    for token, count in tf.items():
        indices.append(abs(hash(token)) % (10**9))
        values.append(float(count))

    sorted_pairs = sorted(zip(indices, values))
    indices = [p[0] for p in sorted_pairs]
    values = [p[1] for p in sorted_pairs]

    return SparseVector(indices=indices, values=values)


def search_sparse(query: str, top_k: int = 5) -> list[dict]:
    """Search using BM25-like sparse vectors in Qdrant.

    Finds documents containing exact keywords from the query,
    scored by BM25-like weighting (TF * IDF).
    """
    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)

    sparse_query = text_to_sparse_vector(query)
    if not sparse_query.indices:
        logger.warning("sparse_search_empty_query", query=query[:50])
        return []

    results: QueryResponse = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=sparse_query,
        using=SPARSE_VECTOR_NAME,
        limit=top_k,
        with_payload=True,
    )

    triplets = []
    for point in results.points:
        triplets.append(
            {
                "subject": point.payload.get("subject", ""),
                "predicate": point.payload.get("predicate", ""),
                "object": point.payload.get("object", ""),
                "subject_id": point.payload.get("subject_id", ""),
                "object_id": point.payload.get("object_id", ""),
                "chunk_id": point.payload.get("chunk_id", ""),
                "source_doc": point.payload.get("source_doc", ""),
                "score": point.score,
            }
        )

    logger.info("sparse_search_completed", query=query[:50], results=len(triplets))
    return triplets


def search_dense(query: str, top_k: int = 5) -> list[dict]:
    """Search using dense vector embeddings in Qdrant."""
    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    embeddings = get_embeddings()

    query_vector = embeddings.embed_query(query)

    results: QueryResponse = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        using=DENSE_VECTOR_NAME,
        limit=top_k,
        with_payload=True,
    )

    triplets = []
    for point in results.points:
        triplets.append(
            {
                "subject": point.payload.get("subject", ""),
                "predicate": point.payload.get("predicate", ""),
                "object": point.payload.get("object", ""),
                "subject_id": point.payload.get("subject_id", ""),
                "object_id": point.payload.get("object_id", ""),
                "chunk_id": point.payload.get("chunk_id", ""),
                "source_doc": point.payload.get("source_doc", ""),
                "score": point.score,
            }
        )

    logger.info("dense_search_completed", query=query[:50], results=len(triplets))
    return triplets


def search_hybrid(query: str, top_k: int = 5) -> list[dict]:
    """Hybrid search combining dense and sparse retrieval using Qdrant RRF fusion."""
    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    embeddings = get_embeddings()

    dense_vector = embeddings.embed_query(query)
    sparse_vector = text_to_sparse_vector(query)

    if not sparse_vector.indices:
        return search_dense(query, top_k)

    from qdrant_client.models import FusionQuery, Prefetch

    results: QueryResponse = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=FusionQuery(fusion="rrf"),
        prefetch=[
            Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=top_k,
            ),
            Prefetch(
                query=sparse_vector,
                using=SPARSE_VECTOR_NAME,
                limit=top_k,
            ),
        ],
        limit=top_k,
        with_payload=True,
    )

    triplets = []
    for point in results.points:
        triplets.append(
            {
                "subject": point.payload.get("subject", ""),
                "predicate": point.payload.get("predicate", ""),
                "object": point.payload.get("object", ""),
                "subject_id": point.payload.get("subject_id", ""),
                "object_id": point.payload.get("object_id", ""),
                "chunk_id": point.payload.get("chunk_id", ""),
                "source_doc": point.payload.get("source_doc", ""),
                "score": point.score,
            }
        )

    logger.info("hybrid_search_completed", query=query[:50], results=len(triplets))
    return triplets
