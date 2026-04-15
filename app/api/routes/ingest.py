import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.exceptions import UnsupportedFileTypeError
from app.models.schemas import IngestResponse
from app.pipelines.ingestion import ingest_document

router = APIRouter(prefix="/api/v1", tags=["ingest"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Upload and process a document",
    description="Upload a PDF, TXT, or Markdown file. The document will be chunked, "
    "triplets extracted via LLM, and stored in both NebulaGraph and Qdrant.",
    responses={
        200: {"description": "Document processed successfully"},
        400: {"description": "Unsupported file type"},
        503: {"description": "Backend service unavailable"},
    },
)
async def ingest_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(suffix)

    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / file.filename
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = ingest_document(tmp_path)

        return IngestResponse(
            filename=result["filename"],
            chunks_count=result["chunks_count"],
            triplets_count=result["triplets_count"],
            status=result["status"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error processing document: {str(e)}",
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        Path(tmp_dir).rmdir()
