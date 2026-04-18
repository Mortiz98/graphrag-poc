"""Document loaders for PDF, TXT, and Markdown files."""

from pathlib import Path

from pypdf import PdfReader

from app.core import logger
from app.models.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def load_document(file_path: Path) -> list[Document]:
    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    docs: list[Document] = []

    if ext == ".pdf":
        reader = PdfReader(str(file_path))
        for page in reader.pages:
            text = page.extract_text()
            if text:
                docs.append(Document(page_content=text, metadata={"page": page.page_number}))
    elif ext in {".txt", ".md"}:
        text = file_path.read_text(encoding="utf-8")
        docs.append(Document(page_content=text, metadata={}))
    else:
        raise ValueError(f"No loader for extension: {ext}")

    for doc in docs:
        doc.metadata["source_file"] = file_path.name

    logger.info("document_loaded", file=str(file_path), chunks=len(docs))
    return docs
