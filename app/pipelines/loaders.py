"""Document loaders for PDF, TXT, and Markdown files."""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.core import logger

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def load_document(file_path: Path) -> list[Document]:
    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    if ext == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif ext in {".txt", ".md"}:
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        raise ValueError(f"No loader for extension: {ext}")

    docs = loader.load()
    for doc in docs:
        doc.metadata["source_file"] = file_path.name

    logger.info("document_loaded", file=str(file_path), chunks=len(docs))
    return docs
