"""Document type — replaces langchain_core.documents.Document."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    page_content: str
    metadata: dict = field(default_factory=dict)
