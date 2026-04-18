"""Unit tests for ingestion pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.models.documents import Document
from app.models.schemas import Triplet
from app.pipelines.ingestion import (
    _sanitize_vertex_id,
    chunk_documents,
    extract_triplets,
    extract_triplets_from_chunk,
    ingest_document,
    store_in_graph,
    store_in_vectorstore,
)


class TestSanitizeVertexId:
    def test_simple_string(self):
        assert _sanitize_vertex_id("Python") == "Python"

    def test_spaces_replaced(self):
        assert _sanitize_vertex_id("Guido van Rossum") == "Guido_van_Rossum"

    def test_special_chars_replaced(self):
        assert _sanitize_vertex_id("Qdrant, Inc.") == "Qdrant__Inc"

    def test_empty_string_returns_entity_prefix(self):
        result = _sanitize_vertex_id("")
        assert result.startswith("entity_")

    def test_long_string_truncated(self):
        result = _sanitize_vertex_id("A" * 300)
        assert len(result) <= 256

    def test_unicode_converted(self):
        result = _sanitize_vertex_id("café")
        assert "caf" in result

    def test_only_underscores_returns_entity_prefix(self):
        result = _sanitize_vertex_id("___")
        assert result.startswith("entity_")

    def test_hyphen_replaced(self):
        assert _sanitize_vertex_id("my-entity") == "my_entity"


class TestChunkDocuments:
    def test_splits_document(self):
        doc = Document(page_content="A" * 2000, metadata={})
        chunks = chunk_documents([doc], "test.txt")
        assert len(chunks) > 1
        assert all("chunk_id" in c.metadata for c in chunks)
        assert all(c.metadata["source_file"] == "test.txt" for c in chunks)
        assert chunks[0].metadata["chunk_index"] == 0

    def test_small_document_single_chunk(self):
        doc = Document(page_content="Short text.", metadata={})
        chunks = chunk_documents([doc], "small.txt")
        assert len(chunks) == 1

    def test_metadata_preserved(self):
        doc = Document(page_content="Hello world", metadata={"existing": "value"})
        chunks = chunk_documents([doc], "test.txt")
        assert chunks[0].metadata["existing"] == "value"


class TestExtractTripletsFromChunk:
    @patch("app.pipelines.ingestion.generate")
    def test_valid_json_response(self, mock_generate):
        mock_generate.return_value = (
            '[{"subject":"Python","subject_type":"Technology",'
            '"predicate":"is_a","object":"Language","object_type":"Concept"}]'
        )

        chunk = Document(page_content="Python is a language", metadata={"chunk_id": "test"})
        triplets = extract_triplets_from_chunk(chunk)

        assert len(triplets) == 1
        assert triplets[0].subject == "Python"
        assert triplets[0].predicate == "is_a"

    @patch("app.pipelines.ingestion.generate")
    def test_no_json_in_response(self, mock_generate):
        mock_generate.return_value = "No entities found here"

        chunk = Document(page_content="Random text", metadata={"chunk_id": "test"})
        triplets = extract_triplets_from_chunk(chunk)
        assert triplets == []

    @patch("app.pipelines.ingestion.generate")
    def test_invalid_triplet_skipped(self, mock_generate):
        mock_generate.return_value = '[{"subject":"Python"},{"subject":"A","predicate":"b","object":"C"}]'

        chunk = Document(page_content="Text", metadata={"chunk_id": "test"})
        triplets = extract_triplets_from_chunk(chunk)
        assert len(triplets) == 1

    @patch("app.pipelines.ingestion.generate")
    def test_json_with_markdown_wrapper(self, mock_generate):
        mock_generate.return_value = '```json\n[{"subject":"X","predicate":"y","object":"Z"}]\n```'

        chunk = Document(page_content="Text", metadata={"chunk_id": "test"})
        triplets = extract_triplets_from_chunk(chunk)
        assert len(triplets) == 1

    @patch("app.pipelines.ingestion.generate")
    def test_empty_json_array(self, mock_generate):
        mock_generate.return_value = "[]"

        chunk = Document(page_content="Text", metadata={"chunk_id": "test"})
        triplets = extract_triplets_from_chunk(chunk)
        assert triplets == []


class TestExtractTriplets:
    @patch("app.pipelines.ingestion.extract_triplets_from_chunk")
    def test_processes_all_chunks(self, mock_extract):
        mock_extract.return_value = [Triplet(subject="A", predicate="b", object="C")]
        chunks = [
            Document(page_content="text1", metadata={"chunk_id": "c1"}),
            Document(page_content="text2", metadata={"chunk_id": "c2"}),
        ]
        results = extract_triplets(chunks)
        assert len(results) == 2
        assert len(results[0][1]) == 1

    @patch("app.pipelines.ingestion.extract_triplets_from_chunk")
    def test_empty_chunks(self, mock_extract):
        mock_extract.return_value = []
        results = extract_triplets([])
        assert results == []


class TestStoreInGraph:
    @patch("app.pipelines.ingestion.get_nebula_session")
    def test_stores_vertices_and_edges(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        triplets_by_chunk = [
            (
                Document(page_content="text", metadata={"chunk_id": "c1"}),
                [
                    Triplet(
                        subject="Python",
                        subject_type="Tech",
                        predicate="is_a",
                        object="Language",
                        object_type="Concept",
                    )
                ],
            )
        ]

        vertex_map = store_in_graph(triplets_by_chunk, "test.txt")

        assert "Python" in vertex_map
        assert "Language" in vertex_map
        assert mock_session.execute.call_count >= 3

    @patch("app.pipelines.ingestion.get_nebula_session")
    def test_empty_triplets(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = store_in_graph([], "test.txt")
        assert result == {}


class TestStoreInVectorstore:
    @patch("app.pipelines.ingestion.get_qdrant_client")
    @patch("app.pipelines.ingestion.ensure_collection_exists")
    @patch("app.pipelines.ingestion.get_embeddings")
    def test_stores_vectors(self, mock_embeddings, mock_ensure, mock_client):
        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [[0.1] * 768]
        mock_embeddings.return_value = mock_emb

        mock_qdrant = MagicMock()
        mock_client.return_value = mock_qdrant

        triplets_by_chunk = [
            (
                Document(page_content="text", metadata={"chunk_id": "c1"}),
                [Triplet(subject="A", predicate="b", object="C")],
            )
        ]
        vertex_map = {"A": "A", "C": "C"}

        count = store_in_vectorstore(triplets_by_chunk, vertex_map, "test.txt")
        assert count == 1
        mock_qdrant.upsert.assert_called_once()

    @patch("app.pipelines.ingestion.get_qdrant_client")
    @patch("app.pipelines.ingestion.ensure_collection_exists")
    @patch("app.pipelines.ingestion.get_embeddings")
    def test_no_triplets_returns_zero(self, mock_embeddings, mock_ensure, mock_client):
        count = store_in_vectorstore([], {}, "test.txt")
        assert count == 0


class TestIngestDocument:
    @patch("app.pipelines.ingestion.store_in_vectorstore", return_value=5)
    @patch("app.pipelines.ingestion.store_in_graph", return_value={"A": "A"})
    @patch("app.pipelines.ingestion.run_consolidation_pipeline", side_effect=lambda x, **kw: x)
    @patch("app.pipelines.ingestion.extract_triplets")
    @patch("app.pipelines.ingestion.chunk_documents")
    @patch("app.pipelines.ingestion.load_document")
    def test_full_pipeline(self, mock_load, mock_chunk, mock_extract, mock_consolidate, mock_graph, mock_vector):
        mock_load.return_value = [Document(page_content="text")]
        mock_chunk.return_value = [Document(page_content="text", metadata={"chunk_id": "c1"})]
        mock_extract.return_value = [
            (
                Document(page_content="text", metadata={"chunk_id": "c1"}),
                [Triplet(subject="A", predicate="b", object="C")],
            )
        ]

        result = ingest_document(Path("test.txt"))
        assert result["filename"] == "test.txt"
        assert result["status"] == "processed"
        assert result["triplets_count"] == 1

    @patch("app.pipelines.ingestion.extract_triplets")
    @patch("app.pipelines.ingestion.chunk_documents")
    @patch("app.pipelines.ingestion.load_document")
    def test_no_triplets_extracted(self, mock_load, mock_chunk, mock_extract):
        mock_load.return_value = [Document(page_content="text")]
        mock_chunk.return_value = [Document(page_content="text", metadata={"chunk_id": "c1"})]
        mock_extract.return_value = [(Document(page_content="text", metadata={"chunk_id": "c1"}), [])]

        result = ingest_document(Path("empty.txt"))
        assert result["status"] == "no_triplets"
        assert result["triplets_count"] == 0
