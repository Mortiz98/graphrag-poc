"""Unit tests for document loaders."""

import pytest

from app.pipelines.loaders import SUPPORTED_EXTENSIONS, load_document


class TestLoadDocument:
    def test_load_txt_file(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world. This is a test document.", encoding="utf-8")
        docs = load_document(txt_file)
        assert len(docs) == 1
        assert "Hello world" in docs[0].page_content
        assert docs[0].metadata["source_file"] == "test.txt"

    def test_load_md_file(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\nSome **markdown** content.", encoding="utf-8")
        docs = load_document(md_file)
        assert len(docs) == 1
        assert "Title" in docs[0].page_content
        assert docs[0].metadata["source_file"] == "test.md"

    def test_unsupported_file_type(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b,c", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_document(csv_file)

    def test_supported_extensions_constant(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS
