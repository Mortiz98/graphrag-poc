import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.models.schemas import IngestResponse
from app.pipelines.ingestion import ingest_document

router = APIRouter(prefix="/api/v1", tags=["ingest"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        return IngestResponse(
            filename=file.filename,
            chunks_count=0,
            triplets_count=0,
            status=f"unsupported_file_type: {suffix}",
        )

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
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        Path(tmp_dir).rmdir()
