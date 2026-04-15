"""Custom HTTP exceptions for the GraphRAG API."""

from fastapi import HTTPException


class ServiceUnavailableError(HTTPException):
    def __init__(self, service: str, detail: str = ""):
        super().__init__(
            status_code=503,
            detail=detail or f"Service unavailable: {service}",
        )


class DocumentProcessingError(HTTPException):
    def __init__(self, detail: str = "Failed to process document"):
        super().__init__(status_code=422, detail=detail)


class UnsupportedFileTypeError(HTTPException):
    def __init__(self, file_type: str):
        super().__init__(
            status_code=400,
            detail=f"Unsupported file type: {file_type}. Supported: .pdf, .txt, .md",
        )


class NoTripletsError(HTTPException):
    def __init__(self, filename: str):
        super().__init__(
            status_code=200,
            detail=f"No triplets could be extracted from '{filename}'",
        )
