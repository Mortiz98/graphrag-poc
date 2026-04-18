"""Recursive character text splitter — replaces langchain_text_splitters."""

from __future__ import annotations

from app.models.documents import Document

DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_text(text: str, separators: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    separator = separators[0] if separators else ""
    remaining_separators = separators[1:] if len(separators) > 1 else []

    if separator == "":
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]

    splits = text.split(separator)
    splits = [s for s in splits if s]

    if not splits:
        if remaining_separators:
            return _split_text(text, remaining_separators, chunk_size, chunk_overlap)
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]

    chunks: list[str] = []
    current = ""

    for split in splits:
        candidate = current + separator + split if current else split
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(split) > chunk_size:
                if remaining_separators:
                    sub_chunks = _split_text(split, remaining_separators, chunk_size, chunk_overlap)
                    chunks.extend(sub_chunks[:-1])
                    current = sub_chunks[-1] if sub_chunks else ""
                else:
                    chunks.append(split[:chunk_size])
                    current = split[chunk_size:]
            else:
                current = split

    if current:
        chunks.append(current)

    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) + len(separator) + len(chunk) <= chunk_size:
            merged[-1] += separator + chunk
        else:
            merged.append(chunk)

    return merged


def split_documents(
    documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    separators: list[str] | None = None,
) -> list[Document]:
    sep_list = separators or DEFAULT_SEPARATORS
    chunks: list[Document] = []
    for doc in documents:
        text_chunks = _split_text(doc.page_content, sep_list, chunk_size, chunk_overlap)
        for text_chunk in text_chunks:
            chunks.append(Document(page_content=text_chunk, metadata=dict(doc.metadata)))
    return chunks
